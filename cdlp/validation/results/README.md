
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
