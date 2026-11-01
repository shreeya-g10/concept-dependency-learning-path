
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
