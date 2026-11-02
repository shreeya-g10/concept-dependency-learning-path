# Gold standard (hand-labelled answers)

Used to measure precision / recall. **Freeze it before anyone tunes a prompt.**

To avoid conflicts, each person labels into their **own file**:

```
data/gold/annotations/annotator_a.csv   # Vaidehi
data/gold/annotations/annotator_b.csv   # Sneha
data/gold/annotations/annotator_c.csv   # Shreeya
data/gold/annotations/annotator_d.csv   # Shrestha
```

Edge file columns (one row per concept pair you judged):

```csv
source,target,label,note
trees,binary_tree,hard,
recursion,binary_tree,soft,traversals use recursion
graphs,avl_tree,none,
```

`label` ∈ `hard` · `soft` · `none`. Use concept ids from `concepts.json`. Rules: `docs/annotation_guidelines.md`.

## Files

| File | What |
|---|---|
| `annotations/annotator_<x>.csv` | each annotator's labels, frozen as committed |
| `courses.json` | concept ids per course (puts each pair in its course) |
| `ds101/gold_edges.csv`, `ml101/gold_edges.csv` | **the gold of record**, per course, written by `merge_gold.py` |
| `agreement.json` | κ raw and with the shortcut rule, labels changed by the rule, unresolved ties |
| `adjudication_needed.csv` | the worklist: one row per unresolved tie with each annotator's label and note |
| `gold_concepts.json` | hand-annotated concept list (ds101), for concept extraction |
| `root_cause_testset.json` | gold test set for root-cause tracing (RQ3) |

## Merge and agreement

```bash
python data/gold/merge_gold.py
```

- Puts every pair in its course with `courses.json` (both concepts must be in exactly one course).
- Writes `agreement.json`: Cohen's κ for every annotator pair with ≥ 2 shared pairs, per course and overall, **on the labels as committed, before any adjudication**, both **raw** and after the **shortcut rule** (a hard/soft pair becomes `none` if the same annotator's own hard/soft pairs already form a path from A to B through another concept), plus the labels the rule changed per annotator.
- Writes `<course>/gold_edges.csv` (`source,target,label,agreement,note`): majority of the committed labels. A tie is decided only by a row in `adjudication.csv` (`source,target,label,note`); otherwise the pair is left out, listed under `merge.unresolved` in `agreement.json` and written to `adjudication_needed.csv`. To adjudicate, add a row to `adjudication.csv` and rerun the script; the pair moves into the gold and out of the worklist.
- Never edits an annotator file. `cdlp/shared/test_merge_gold.py` fails if `agreement.json` or a `<course>/gold_edges.csv` is out of date with the annotator files: rerun the script after any label change.

## Provenance (rebuilt 2026-11-02)

The gold is rebuilt **only from labels that exist in the committed annotator files**, so anyone can reproduce it from this folder:

| File | Annotator | Rows used | Status |
|---|---|---|---|
| `annotator_a.csv` | Vaidehi | 20 (ds101 10, ml101 10) | genuine |
| `annotator_c.csv` | Shreeya | 20 (ds101 10, ml101 10) | genuine |
| `annotator_b.csv` | Sneha | 6 (ds101) | genuine |
| `annotator_d.csv` | Shrestha | 0 (header only) | empty |

Excluded: older rows of `annotator_b.csv` and `annotator_d.csv` that exist only in git history (removed in commit 6be20de). They were placeholder labels and are never read. The previous combined `data/gold/gold_edges.csv` ("4/4" agreement on ds101) was merged from them, could not be reproduced from the files, and was deleted in this rebuild; so were the κ values in `cdlp/extraction/results/` that included them.

Result: ds101 9 gold rows, ml101 4 gold rows, 7 unresolved ties, listed in `adjudication_needed.csv` (to be adjudicated later with the larger gold set). κ (a vs c, 20 pairs): raw 0.4909, with the shortcut rule 0.7701; see `agreement.json` for per-course values.
