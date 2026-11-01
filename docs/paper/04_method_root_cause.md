# 4 Method: Root-Cause Tracing

> Draft, written from `cdlp/root_cause/` (merged on `main`, 2026-11-02).

## 4.1 Task

Given a student's wrong answer to a quiz item on concept *T*, which concept most likely caused the error: *T* itself, or a prerequisite further back? In the running example, a student who answers an AVL question wrongly may have a gap in AVL rotations, or may never have understood the BST ordering rule. A system that always blames *T* recommends revising the wrong thing.

The output, per wrong answer, is a ranked list of candidate concepts with scores, the top concept (`traced_concept`), a confidence and a one-sentence explanation.

## 4.2 Prerequisite chain

The candidate set is the **prerequisite chain** of *T*: *T* itself (distance 0) plus every ancestor of *T* in the validated graph, using **ACCEPT edges only**. REJECT and HUMAN_REVIEW edges are not part of the course graph downstream. Concepts are ordered by shortest-path distance from *T*, then by concept id. Each chain entry records which chain concepts it is a direct prerequisite of, and with what strength (hard or soft).

## 4.3 LLM tracing

The LLM receives the question, its options, the correct answer, the student's answer, and the chain (nearest first) with each concept's role ("hard prerequisite of X") and the student's mastery (a probability, or "unknown"). The prompt asks the model to use two kinds of evidence:

1. **The wrong answer itself:** which misconception would lead to choosing exactly this option, and which chain concept does that misconception belong to?
2. **Mastery:** a clearly mastered prerequisite is an unlikely cause, and a low-mastery prerequisite is a likely cause only if the wrong answer fits a gap in it. Low mastery alone is not enough. If the wrong answer shows a mistake in *T*'s own content, *T* is blamed even when a prerequisite has low mastery.

The model may rank only concepts from the chain, by exact id. Two worked examples from an unrelated domain (Spanish verb conjugation) show the reasoning: the same wrong-option question traced once to the target and once to a prerequisite, depending on the option chosen and on mastery. This avoids leaking course content into the prompt. Prompt `trace_v1`, model `qwen2.5:7b-instruct` (`LLM_MODEL`), temperature 0, seed 42.

**Post-processing keeps the output inside the chain.** Unknown ids are dropped, and a duplicate keeps its first score. Scores are clamped to [0, 1] and normalized to sum 1. Chain concepts the model left out are appended with score 0, nearest first, so top-*k* is always defined. Ties keep the model's order.

**Fallbacks.** If nothing usable comes back (no valid candidate, or non-JSON output), the trace falls back to the nearest-prerequisite baseline (§4.4), and its explanation is marked so evaluation can count it (`llm_fallbacks`). If the LLM is unreachable, experiments and the CLI fail loudly instead of silently turning into a baseline. Only the website opts in to an offline estimate, and marks it as such. A concept with no prerequisites (a chain of length 1) is traced to itself without an LLM call.

## 4.4 Baselines

Both baselines rank the whole chain so top-3 is defined. Their scores are rank-based (1/rank, normalized) and encode only the order.

- **Blame the target.** *T* first, then its ancestors by distance, then id. This is what a system without a prerequisite graph does.
- **Blame the nearest prerequisite.** Among *T*'s direct ACCEPT prerequisites, the one with the lowest mastery (unknown counts as 0.5). Ties break by edge strength (hard before soft), then concept id. The rest of the ranking is the other direct prerequisites, then *T*, then the remaining ancestors by distance, then id. A concept with no prerequisites blames itself.

## 4.5 RQ3 protocol: no mastery for any method

In RQ3, every wrong answer is traced **with mastery unknown, for the LLM and both baselines alike**. The comparison then measures what each method gets from the question, the wrong answer and the graph, not from a separately estimated knowledge state, and the test set provides no mastery to give. In this setting every concept shows "mastery unknown" in the prompt. The nearest-prerequisite baseline reduces to "blame a hard direct prerequisite if there is one, else the alphabetically first direct prerequisite". We state this so the baseline is not mistaken for something stronger.

The prompt was developed only on a separate dev set built by the lead author from the shared example items, which shares no item ids with the test set. The test set (`data/gold/root_cause_testset.json`) was built by the other author, with `expected_concept` labels. Metrics are top-1 and top-3 accuracy over wrong answers, plus the LLM fallback count. [RESULT: RQ3 table]

## 4.6 How this differs from knowledge tracing

Knowledge tracing (BKT, DKT; Section 2.3) estimates *how likely* a student is to know each skill from many answers over time. Root-cause tracing explains *one* wrong answer using the content of the option chosen and the validated prerequisite structure. It needs no interaction history, and it returns a concept to revise with a human-readable reason. The two are complementary: with a knowledge state available, the mastery inputs in §4.3 can come from the diagnostic.
