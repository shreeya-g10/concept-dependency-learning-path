# Concept extraction results

`evaluation_metrics.json`: concept extraction vs. the hand-annotated concept list (`data/gold/gold_concepts.json`), written by `python -m cdlp.extraction.evaluate --concepts outputs/<course>/concepts.json`.

| Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|
| 0.86 | 1.00 | 0.92 | 6 | 1 | 0 |

Caveat: measured on the stub lectures; rerun on the real material before reporting.

Inter-annotator agreement is no longer reported here. The κ values this file used to show (average 0.92 over annotators a–d) included labels of annotators b and d that were later removed from their files, so they cannot be reproduced. The reproducible κ (raw and with the shortcut rule, per course) is in `data/gold/agreement.json` (`python data/gold/merge_gold.py`).
