# Validation results

## Semantic check: prompt iteration v1 → v2

Both runs judge the same 6 edges in `cdlp/shared/examples/relationships.json` with
`llama3.1:8b` (seed 42, temperature 0). Files: `semantic_v1_examples.json`,
`semantic_v2_examples.json`; each records model, prompt version, seed and date.

| Edge | v1 | v2 |
|---|---|---|
| trees → binary_tree | weak / REJECT | strong / ACCEPT |
| binary_tree → binary_search_tree | weak / REJECT | strong / ACCEPT |
| binary_search_tree → avl_tree | strong / ACCEPT | strong / ACCEPT |
| recursion → binary_tree | weak / REJECT | strong / ACCEPT |
| trees → graphs | weak / REJECT | weak / REJECT |
| graphs → avl_tree | weak / REJECT | none / REJECT |

**Why v2.** v1 graded "B is a kind of A" edges weak (e.g. a binary search tree *is*
a binary tree), even when its own rationale said so. v2 adds one rule (a
specialisation of A builds on A, so it is strong) and one music example for it.

**Side effect seen in v2.** `recursion → binary_tree` jumped from weak to strong,
with the rationale "binary trees are a specialisation of recursion". The rule
makes the model over-apply "specialisation"; the gold label for this pair is soft.

**Not tuned further, on purpose.** These example edges overlap the gold set, so
iterating the prompt until they look right would leak gold labels into the
validator. v2 was written once from the v1 failure mode and run once. This table
is a sanity check of the prompt change, not an evaluation.

v2 is the default for both the agent's semantic check and the RQ1 single-judge
baseline, so RQ1 isolates what the evidence, necessity and graph checks add.

## Necessity test v1: first run on the examples

`necessity_v1_examples.json`: edges r2, r4, r6 of `cdlp/shared/examples/`, `llama3.1:8b` for every role, seed 42, temperature 0, `configs/default.json` (3 questions; thresholds 0.15 / 0.3 / 0.5). 15 calls took 545 s.

| Edge | Score without A | Score with A | Gap | Grade | Gold | Leakage |
|---|---|---|---|---|---|---|
| binary_tree → binary_search_tree | 0.50 | 1.00 | 0.50 | strong | hard | 0/3 |
| recursion → binary_tree | 0.67 | 0.83 | 0.17 | weak | soft | 0/3 |
| graphs → avl_tree | 0.33 | 0.83 | 0.50 | **strong** | none | 0/3 |

**Confound found.** `graphs → avl_tree` should be near zero, but the "without A" learner hedges on every question ("I don't know…, but I think…"), even though AVL trees do not depend on graphs. Two effects are mixed into the gap:
1. **Role-play penalty:** being told it has *never learned* something makes the model answer less confidently overall, not only where A is needed.
2. **Extra context:** the "with A" learner also receives A's description.

Zero leakage shows the learner obeyed the ban, so leakage is not the cause. Until a control condition separates these effects (for example, a "without" run that forbids an unrelated concept, with the gap measured against that run), a necessity gap is **not** evidence of necessity on its own. Not tuned further on these edges, since they overlap gold.

## Necessity test v1 with a control run (2026-11-02)

The gap is now **control score − score without A**. The control learner gets the same "without" prompt, but with an unrelated concept C banned instead of A. C is neither an ancestor nor a descendant of B in the proposed edges; the placeholder "Origami Folding" is used when no such concept exists. "With A" is kept as a diagnostic. Same 3 edges, same model, seed and config. 6 new calls per run; the other 15 came from cache; 164 s each.

**Variant 1: control learner does not know A** (`necessity_v1_control_a_unlisted_examples.json`). Discarded as a design flaw, not because of its numbers: A was unlisted in both runs, so the gap measured only the explicit ban, not the absence of A. It gave 0.50 strong / 0.00 none / 0.17 weak.

**Variant 2 (current): control learner knows A by name** (`necessity_v1_control_examples.json`). A's description is withheld, so no extra context. It differs from "without A" only in which concept is banned and whether A is listed as known.

| Edge | C | Control | Without A | Gap | Grade | With A (diag.) | Gold | Leakage A / C |
|---|---|---|---|---|---|---|---|---|
| binary_tree → binary_search_tree | Graphs | 0.67 | 0.50 | 0.17 | weak | 1.00 | hard | 0/3 · 0/3 |
| recursion → binary_tree | Graphs | 0.83 | 0.67 | 0.17 | weak | 0.83 | soft | 0/3 · 0/3 |
| graphs → avl_tree | Origami Folding (placeholder) | 0.67 | 0.33 | 0.33 | medium | 0.83 | none | 0/3 · 0/3 |

**What this shows (not tuned on these edges):**
1. **Noise is as large as the signal.** With 3 questions, scores move in 1/6 steps. For `binary_tree → binary_search_tree`, the control learner (who knows strictly more) got Q1 wrong while the "without A" learner got it right, a run-to-run difference of one step. At n = 3 the gaps here are within that noise.
2. **The placeholder is a weaker control.** Banning an off-topic subject (origami) likely triggers less hedging than banning an in-course concept, so the role-play penalty is not matched. The one placeholder edge got the largest gap despite gold none.
3. Leakage is 0 everywhere, so the learner obeys the bans; that is not the problem.

The necessity grade is **not usable as evidence yet**. The next steps are a stability study (n = 2 vs 3, more questions, several seeds) and a better fallback control before any threshold is set.

## Necessity stability study (2026-11-02)

`necessity_stability/`: one file per (format, n, seed) plus `summary.json` (config, timing, skipped and failed runs). Same 3 edges, `llama3.1:8b`, temperature 0, seeds 42 / 43 / 44, "with A" diagnostic off, thresholds unchanged. Control C: Graphs (in-course) for the first two edges, Gradient Descent (cross-course, ml101) for `graphs → avl_tree`. About 55 of the approved 60 minutes were used: 40.0 min of finished runs, ~10 min lost when one Ollama call hung until its 600 s read timeout (another process was using the GPU), and 5.3 min to redo that run with `--resume`. `summary.json`'s `spent_minutes` counts only the resumed invocation. **Open n = 5 was not run**: it did not fit in the budget.

Mean gap ± SD across seeds (expected order: BT→BST > rec→BT > graphs→AVL ≈ 0):

| Format | n | binary_tree → BST | recursion → binary_tree | graphs → avl_tree | Order holds (means / per seed) |
|---|---|---|---|---|---|
| open | 3 | 0.167 ± 0.000 | 0.167 ± 0.000 | 0.167 ± 0.000 | no / 0 of 3 |
| mcq | 3 | 0.000 ± 0.000 | 0.333 ± 0.000 | 0.000 ± 0.000 | no / 0 of 3 |
| mcq | 5 | 0.000 ± 0.000 | 0.267 ± 0.231 | 0.000 ± 0.000 | no / 0 of 3 |
| mcq | 8 | 0.000 ± 0.000 | 0.167 ± 0.289 | 0.000 ± 0.000 | no / 0 of 3 |

**Findings:**
1. **At temperature 0 the seed is nearly irrelevant.** Decoding is greedy, so open n = 3 gave identical questions, answers and grades for all three seeds: SD 0 means repetition, not stability. The MCQ runs did vary with the seed. This study therefore does not measure question-set variance; that needs a non-zero temperature for question writing.
2. **MCQ is insensitive to the ban.** In most MCQ runs the control and "without A" learners scored exactly the same (e.g. both 1.00 on `binary_tree → BST` at n = 3, both 0.25 at n = 8). That correctly gives `graphs → avl_tree` ≈ 0, but also gives 0 for the hard edge. The learner chooses between options by elimination, whether or not A is banned.
3. **Open n = 3 responds to the ban, but too little to rank.** Every edge got exactly one half-step (0.167), the smallest non-zero gap possible, so it cannot separate a hard prerequisite from an unrelated one.
4. No setting reproduces the expected order, in the means or in any single seed. No thresholds were tuned.
