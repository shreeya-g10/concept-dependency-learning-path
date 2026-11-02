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

## Merge and agreement

```bash
python data/gold/merge_gold.py
```

- Puts every pair in its course with `courses.json` (both concepts must be in exactly one course).
- Writes `merged/agreement.json`: Cohen's κ for every annotator pair with ≥ 2 shared pairs, per course and overall, **on the labels as committed, before any adjudication**, both **raw** and after the **shortcut rule** (a hard/soft pair becomes `none` if the same annotator's own hard/soft pairs already form a path from A to B through another concept), plus the labels the rule changed per annotator.
- Writes `merged/<course>/gold_edges.csv` (same columns as `gold_edges.csv`): majority of the committed labels. A tie is decided only by a row in `adjudication.csv` (`source,target,label,note`); otherwise the pair is left out and listed under `merge.unresolved` in `agreement.json`.
- Never edits an annotator file or `gold_edges.csv`. `gold_edges.csv` is still the gold of record (ds101, merged earlier from four annotators' labels, some of which were later removed from `annotator_b.csv` and `annotator_d.csv`). Replacing it with the `merged/` files is a separate, explicit decision.
- `cdlp/shared/test_merge_gold.py` fails if `merged/agreement.json` is out of date with the annotator files: rerun the script after any label change.

