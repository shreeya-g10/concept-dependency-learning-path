# Validation · maintainer: Shreeya

The validation agent (novelty 1).

**Question you answer:** *Can we trust this relationship?*

**Files:** `cdlp/validation/`, `website/pages/3_Validation_Agent.py`.

| | File | Notes |
|---|---|---|
| Input | `relationships.json`, `concepts.json`, `chunks.jsonl` | Until Day 6 use `cdlp/shared/examples/` (it already includes a bad edge: graphs → avl_tree) |
| Output | `validated_graph.json` | Every edge kept with ACCEPT / REJECT / HUMAN_REVIEW, the four checks, necessity gap, reason |
| Output (planned) | `review_queue.json` | With `--review-queue <path>`: HUMAN_REVIEW edges ranked by impact (contract 1.1) |

Use a **different model** from discovery (`LLM_VALIDATOR_MODEL` in `.env`) so the two models' errors don't line up.

## Tasks, in order
- [ ] **Day 1:** push the repo, share the link, fill in `CODEOWNERS` usernames, label your share of gold edges
- [x] Graph check (NetworkX): cycles, self-loops, duplicates, contradictions, redundant (transitive) edges
- [x] Evidence check: retrieve chunks for A and B; does the text support A before B?
- [x] Semantic check: does the edge make teaching sense?
- [x] **Necessity test (simulated learner):** an LLM plays a student who doesn't know A and answers questions on B, then does it again knowing A. `necessity_gap` = score with A − score without A. Done in `necessity_test.py`: 3 questions from B's chunks, a learner who knows only the concepts taught before B (A forbidden), the same learner knowing A, a blind grader; gap → strong / medium / weak / none via `configs/default.json` (thresholds uncalibrated). Leakage check flags "without A" answers that use A's name, aliases or stems. One prompt per role: `prompts/necessity_{questions,learner_without,learner_with,grader}_v1.txt`.
- [x] Leakage check: does the "student without A" still use A's terms? Report the rate
- [x] Decision rule → ACCEPT / REJECT / HUMAN_REVIEW (tune thresholds on a small dev split, never on test) Done in `__main__.py` (thresholds in `configs/default.json` → `decision`, still uncalibrated; never tune them on test).
- [x] **Impact-ranked review queue (`review_queue.py` done; CLI wiring pending):** `--review-queue <path>` writes `review_queue.json`. For each HUMAN_REVIEW edge, impact = number of simulated students (`sim_students.json`) whose personalized path changes if the edge flips (accepted vs not). Store it as `paths_affected`, derive `impact_score` from it, and sort highest first so reviewers see the edges that matter most Edges that would close a cycle are **blocking** (`blocking: true`, impact null) and come before every impact-ranked edge; every review strategy handles them first. Wired: `python -m cdlp.validation ... --review-queue <path> --students <sim_students.json>`.
- [ ] **Day 7: hand off real `validated_graph.json`** to Shrestha and run `python pipeline.py` on real data
- [ ] RQ1 ablations: discovery only · single LLM judge · full agent · agent minus each check → P / R / F1, HUMAN_REVIEW rate → `cdlp/validation/results/`
- [ ] Website page 3: decisions, checks, evidence, necessity gap

## Notes for the paper
- **RQ1 on benchmarks reports the agent with the semantic and graph checks only** (decided 2026-11-02, revised the same day). AL-CPL and the University Course dataset give concept pairs only, no course text, so the evidence check has nothing to retrieve and the necessity test has no chunks to write questions on B from. On those datasets the reported agent is `minus_evidence_necessity`; on ds101 and ml101 it is `full_agent`. Each config in `configs/rq1/` names it in `reported_agent`, and the results files copy it. `full_agent` and `minus_evidence` are still scored on benchmarks but not reported. Suggested wording: *"The public benchmarks provide no course material, so on them we evaluate the agent with its semantic and graph-consistency checks only; the evidence check and the necessity test both need course text."*
- **Scoring conventions** (`cdlp/validation/evaluate.py`): our gold is scored on direct edges, and an unlabelled predicted pair counts as a false positive. Benchmarks score only labelled pairs; AL-CPL uses the transitive closure of our predictions, and University Course uses it only if its gold positives imply each other (count recorded in each result). State the convention next to every number.

## Done when
The full agent and every ablation run from one config each, results are in `cdlp/validation/results/`, and `pytest cdlp/validation` passes.

## Review-queue experiment (code ready, not run yet)

`python -m cdlp.validation.review_experiment --config cdlp/validation/configs/review_experiment/ds101.json`

Graph F1 after k = 0…10 simulated teacher answers (answers from gold, applied with `apply_review.py`), for three orders of the HUMAN_REVIEW edges: impact-ranked, random (20 seeds, mean ± std) and lowest validator confidence. Blocking edges come first in every strategy, and every strategy re-ranks after each answer. No LLM call. Writes `results/review_experiment_<course>.json`. Needs the RQ1 full-agent graph (`outputs/rq1/<course>/validated_graph.json`) and `sim_students.json`. Caveats are in the module docstring: only accepted gold positives move F1, blocking-first spends budget without changing F1, and the oracle teacher makes each curve an upper bound.
