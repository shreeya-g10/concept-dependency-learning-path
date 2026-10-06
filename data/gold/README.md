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

Vaidehi merges the files into `gold_concepts.json` and `gold_edges.csv`, and reports agreement (Cohen's κ) on the pairs that two people both labelled.
