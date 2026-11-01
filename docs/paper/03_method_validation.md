# 3 Method: the Validation Agent

> Draft, written from the code. **Implementation status on `main` (2026-11-02):** the graph-consistency, evidence and semantic checks and the RQ1 harness are merged. The necessity test (§3.4) is on branch `validation/necessity-test`, the semantic prompt v2 on `validation/semantic-v2`, and the impact-ranked review queue (§3.7) on `validation/review-queue`; none of the three is merged yet. The decision rule (§3.6) and the agent CLI are **not implemented**: `python -m cdlp.validation` still writes example output. Update this section when they land.

## 3.1 Input and output

The agent receives the discovery output: a list of proposed edges *A → B* (*A* is the prerequisite). Each edge carries a strength (hard or soft), a discovery confidence and the chunk ids discovery cited. The agent also gets the course's canonical concepts (name, aliases, description) and its text chunks (document, page, heading).

For **every** proposed edge it writes one record to `validated_graph.json` with: a decision ∈ {ACCEPT, REJECT, HUMAN_REVIEW}; a confidence; the four check results (evidence, semantic and necessity each graded strong / medium / weak / none; graph ∈ {ok, cycle, contradiction, duplicate, redundant, self_loop}); the necessity gap; verified evidence quotes (chunk, document, page); and a short reason. REJECT and HUMAN_REVIEW edges are kept for analysis. Downstream stages use ACCEPT edges only.

## 3.2 Independence from discovery

Discovery uses `qwen2.5:7b-instruct`. Every LLM check in the validator uses a different model (`llama3.1:8b`) and its own versioned prompt file. Using the same model and prompt that proposed an edge to judge it invites correlated errors: a model that finds an edge plausible will tend to find it plausible again. All LLM calls run at temperature 0 with a fixed seed (42). The model id, prompt version and temperature are recorded with every output.

## 3.3 Checks that fail independently

The checks are designed to use different information, so that one check's blind spot is not shared by the others.

**Graph-consistency check (no LLM).** Built on the full set of proposed edges, independent of discovery confidence. Each edge gets the first label that applies:
`self_loop` (A → A); `duplicate` (a repeated (A, B) pair; the first copy is checked normally); `contradiction` (A → B and B → A both proposed; both edges are labelled); `cycle` (the edge lies in a strongly connected component, i.e. on a directed cycle of length ≥ 3); `redundant` (A → C while a path A → … → C exists through other edges); otherwise `ok`.
Redundancy is computed by transitive reduction on the acyclic part only (edges still `ok`), because a transitive reduction is unique only for a DAG. Cycle and contradiction edges are never used as paths for redundancy, but they do count when finding cycles. The check never decides on its own. It enforces the design rule that **an edge that would create a cycle is never auto-accepted**.

**Evidence check (course text).** For edge A → B we collect the chunks discovery cited plus the top-*k* (default 3) chunks retrieved by embedding similarity (sentence-transformers `all-MiniLM-L6-v2`, exact cosine search, which is enough at course scale). The query is built from both concepts' names and descriptions. The validator model then grades whether *the excerpts* support learning A before B, judging only from the excerpts and not from its own knowledge. Co-occurrence or a loose relation does not count as support. It must quote the text it relied on. **Every quote is verified:** it is kept only if it occurs verbatim (ignoring case and whitespace) in the chunk it cites. A strong or medium grade with no verifiable quote is capped at weak. So every quote shown to a user is traceable to a document and page, and an evidence grade can't rest on invented text.

**Semantic check (no course text).** The validator model grades whether teaching A before B makes pedagogical sense, from the concepts' names, aliases and descriptions only. It never sees the chunks, so it fails independently of the evidence check. The prompt states that being related, being in the same course or being taught nearby is not enough, and that a dependency running backwards or only through an intermediate topic is weak or none. A few worked examples from an unrelated domain (music) show the grading without leaking course content. [Prompt version used in the paper: semantic_v1 on `main`; semantic_v2, which grades specialization (B is a kind of A) as strong, is pending; state which one is final.]
On its own, this call is also our **single LLM-judge baseline**: ACCEPT if graded strong or medium, else REJECT.

## 3.4 Necessity test (simulated learner)

The semantic and evidence checks ask whether an edge is *plausible* or *supported*. The necessity test asks whether *A* is actually *needed* for *B*. For edge A → B:

1. **Questions.** The model writes *n* short questions on B (default *n* = 3), with reference answers, from B's own chunks.
2. **Without A.** A simulated learner who knows the concepts taught before B but has *never learned A* answers the questions.
3. **Control.** The same learner, now knowing A by name only, with an unrelated concept C forbidden instead, using the same prompt. C is neither an ancestor nor a descendant of B among the proposed edges, and is neither A nor B. If no such concept exists, a fixed neutral placeholder topic is used. The control absorbs the role-play penalty of being told "you never learned X". In an early run this penalty lowered scores on its own, whatever X was.
4. **Diagnostic, with A.** The learner also answers knowing A, with A's description. This is reported but not used in the gap, because it adds context.
5. **Grading.** A separate grader prompt scores each run against the reference answers (correct 1, partial 0.5, incorrect 0) and is blind to which run it grades.
6. **Gap.** *necessity_gap = control score − score without A*. It maps to strong / medium / weak / none with thresholds 0.5 / 0.3 / 0.15; a gap ≤ 0 is none. With three questions in half-point steps every gap is a multiple of 1/6, and these thresholds separate one, two, and three or more half-steps. **The thresholds are a first, uncalibrated choice**, to be calibrated on a held-out split and never on evaluation gold.

**Leakage check.** If a "without A" answer still uses A's name, an alias or a stemmed form of them, it is flagged. B's own name is masked first, so "binary search tree" does not count as using "binary tree". Leakage shrinks the gap, so a high leakage rate means the grade *understates* necessity. We report the rate per edge and overall: [RESULT: leakage rate].

Each role (question writer, learner without A, learner with A, grader) has its own versioned prompt. Calls per edge: [RESULT/STAT: LLM calls per edge for the necessity test].

## 3.5 Why necessity is not the same as a judge

A single judge answers "is A a prerequisite of B?" from the same associations that made the edge plausible in the first place. The necessity test changes the question to a counterfactual about a learner's performance. Its answer is a measured difference between two runs, not a self-reported opinion. *Graphs → AVL Trees* is plausible (both are data structures, often taught near each other), but a learner who has never seen graphs can still answer questions on AVL rotations, so the gap should be near zero. [RESULT: example edge table with gaps, from the examples run, if kept]

## 3.6 Decision rule

> **Not implemented yet.** Planned design, to be replaced by the implemented rule.

The four check results and the discovery confidence combine into ACCEPT / REJECT / HUMAN_REVIEW:

- An edge with graph label `cycle`, `contradiction` or `self_loop` is never auto-accepted. It goes to HUMAN_REVIEW or is rejected. `duplicate` copies take their first copy's decision. `redundant` edges are kept in the full graph but left out of the transitive reduction used for paths and visualization.
- ACCEPT when the checks agree that the edge is supported and needed; REJECT when they agree it is not; HUMAN_REVIEW when they disagree. [TODO: exact rule and thresholds.]
- Thresholds are tuned on a small dev split of gold pairs, which is then excluded from every reported score (`exclude_pairs` in the RQ1 configs).

The HUMAN_REVIEW rate is reported next to precision and recall, because a validator can raise precision by deferring hard cases to people.

## 3.7 Impact-ranked review queue

Human review time is limited, so the HUMAN_REVIEW edges are ranked by how much they matter to students. For each such edge we compare every simulated student's personalized path on the ACCEPT-only graph with the path on ACCEPT plus that edge. A path is (ancestors of target + target) − mastered concepts, in topological order with ties broken by concept id; a concept is mastered when the student's true mastery is > 0.8. `paths_affected` counts the (student, target) paths whose concept set or order changes, and `impact_score` = paths_affected / paths checked ∈ [0, 1]. The queue is sorted by impact. An edge that would close a cycle with the ACCEPT edges cannot be accepted as it is, so it gets impact 0 and a reason. The computation needs no LLM call. The review queue reimplements the path rule instead of importing the learning-path module, because modules communicate only through files.

## 3.8 Graph output

The validated graph keeps every decision. The graph used downstream is built from ACCEPT edges only, stays a DAG, and is stored both in full and as its transitive reduction. Paths and visualizations use the reduced graph.
