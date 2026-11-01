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
