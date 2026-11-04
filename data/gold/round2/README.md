# Gold labels, round 2 (ds101)

## Set 1: not used

Set 1 (`set1_ai_assisted_not_used/`) was labelled with AI help, so it is not gold and is not used for any result. Its AI-assisted labels and the topic list are not in this repo. Only its blank file, key and config are, because they hold no labels and `sample_pairs.py` needs them.

## Set 2

| | |
|---|---|
| Pairs | 120: 90 from the candidate filter and 30 from outside it, seed 43 (`sample_pairs.py`) |
| Labeller | Vaidehi, on 2026-11-04. She says she did it without AI. |
| What she had seen | Set 1's AI answers and the filter's concept names, before labelling set 2 |
| Overlap with set 1 | None: set 2 shares no pairs with set 1 (a test checks this) |
| Labellers | **One. There is no second labeller, so set 2 has no agreement score.** |
| Raw file | `ds101_set2_labels_vaidehi.csv`, saved from the text Vaidehi sent, unchanged. Shreeya confirmed that its 120 pairs match the blank file. SHA-256 `319e1d9454c36589fbc8f4d7eae9e24289baa7e753a54b0b8801433bbc9e8a3b` |

What she had seen means set 2 is not fully independent of the AI and the filter, even though the pairs are new. Report this with any result that uses it, and do not describe set 2 as independently annotated.

### Files

| File | What it is |
|---|---|
| `ds101_set2_labels_vaidehi.csv` | Her raw file. Never change it. |
| `annotator_a_set2.csv` | The same labels in gold format: `source,target,label,note` |
| `set2_split.json` | The development and test split, as pair numbers |
| `prepare_set2.py` | Checks the raw file, then writes the two files above |
| `sample_pairs.py` | Drew the pairs. To rerun it, it needs `private_keys/` and set 1's key. |
| `send_to_annotator/ds101_set2_to_label.csv` | The blank file she was sent |
| `private_keys/` | Which concept IDs and group each pair number is. Holds no labels. |

### Conversion

`first = a` means concept A comes first, and `first = b` means concept B comes first. `strength` gives the label. `first = neither` becomes `none`, and because neither concept comes first, `source` and `target` are simply in sorted ID order: that order means nothing. `python data/gold/round2/prepare_set2.py` reproduces both files exactly.

### Counts

| Group | hard | soft | none | Total |
|---|---|---|---|---|
| candidate | 15 | 37 | 38 | 90 |
| not_candidate | 1 | 5 | 24 | 30 |
| All | 16 | 42 | 62 | 120 |

### Findings, reported and not changed

- Her file had no problems: same 120 pairs, numbers and order as the blank file, with valid values throughout.
- There are no cycles among her hard and soft labels.
- Pairs 37 and 58 are labelled, and are also implied by a longer path of her labels. `data/gold/merge_gold.py` has a shortcut rule for such pairs, so decide how to treat them, and say so, before any merge.

### Development and test split

`set2_split.json` holds a split stratified by label, seed 44: 36 development pairs (5 hard, 13 soft, 18 none) and 84 test pairs (11 hard, 29 soft, 44 none).

- **Development** is for threshold calibration only. Scores must never come from it.
- **Test** is for final scores only. Never use it to choose a threshold or a setting.

### Not merged

Set 2 is not in `data/gold/<course>/gold_edges.csv` or `merge_gold.py`, because the agreement checks there need a second labeller.
