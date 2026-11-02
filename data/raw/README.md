# Course material

One folder per course (`data/raw/<course_id>/`). `python pipeline.py --course <course_id>` reads it.
Only openly licensed material goes here. If a file can't be shared, keep it local and list its name here so everyone knows to ask for it.

The old stub lectures (`ds_lec*.pdf`, `ds_lec8.pptx`, `ml_lec*.pdf`) are now test fixtures in `cdlp/extraction/tests/fixtures/`.

Every file below is a set of pages cut, unmodified, from the book PDF named for it (PyMuPDF `insert_pdf`, 2026-11-02). Page numbers in `chunks.jsonl` count from 1 within each file. To get the page in the book PDF, add `first page − 1`.

## ds101: Open Data Structures (Pat Morin)

- Site: https://opendatastructures.org/
- Source file: https://opendatastructures.org/ods-python.pdf (pseudocode edition, **Edition 0.1Gβ**, PDF dated 2015-01-26, 326 pages, SHA-256 `2bdd7e8129fff83daf04cd594fce5236d72b1d8b8c72832fde22ea762a7e014f`)
- Licence: **Creative Commons Attribution (CC BY 2.5 Canada)**, https://creativecommons.org/licenses/by/2.5/ca/. The site says: "the book and source code are released under a Creative Commons Attribution License."
- Attribution: Pat Morin, *Open Data Structures (in pseudocode)*, Edition 0.1Gβ. Changes: individual chapters extracted, no text changed.

| File | Chapter | Book PDF pages |
|---|---|---|
| `ods_ch02_array_based_lists.pdf` | 2 Array-Based Lists | 43–72 |
| `ods_ch03_linked_lists.pdf` | 3 Linked Lists | 73–94 |
| `ods_ch06_binary_trees.pdf` | 6 Binary Trees (incl. 6.2 Binary Search Tree, recursive algorithms) | 139–156 |
| `ods_ch08_scapegoat_trees.pdf` | 8 Scapegoat Trees (balanced) | 177–188 |
| `ods_ch09_red_black_trees.pdf` | 9 Red-Black Trees (2-4 trees, balanced) | 189–214 |
| `ods_ch10_heaps.pdf` | 10 Heaps | 215–228 |
| `ods_ch12_graphs.pdf` | 12 Graphs (incl. BFS/DFS) | 251–268 |

Coverage gaps: ODS has **no AVL-tree chapter** (AVL trees appear only in the exercises), no chapter on general (non-binary) trees, and no separate recursion chapter. Recursion is taught inside 6.1 (recursive traversal). Balanced trees are covered by scapegoat and red-black trees.

## ml101: Dive into Deep Learning (Zhang, Lipton, Li, Smola)

- Site: https://d2l.ai/ (release **1.0.3**)
- Source file: https://d2l.ai/d2l-en.pdf (PyTorch edition, PDF dated 2023-08-18, 1151 pages, SHA-256 `b3129f44c4a26b534176bb0f83d85e1ed26a6cdf93ebebacb20104eab2d6bc00`)
- Licence: text is **CC BY-SA 4.0**, https://creativecommons.org/licenses/by-sa/4.0/. Sample code is under a modified MIT licence (https://github.com/d2l-ai/d2l-en, `LICENSE` and `LICENSE-SAMPLECODE`).
- Attribution: Aston Zhang, Zachary C. Lipton, Mu Li, Alexander J. Smola, *Dive into Deep Learning*, release 1.0.3. Changes: individual sections extracted, no text changed.
- ShareAlike: anything derived from this text that we redistribute (e.g. `chunks.jsonl`, evidence snippets in `validated_graph.json`) must also be shared under CC BY-SA 4.0.

| File | Section | Book PDF pages |
|---|---|---|
| `d2l_3_1_linear_regression.pdf` | 3.1 Linear Regression (incl. squared loss, minibatch SGD) | 122–132 |
| `d2l_3_6_generalization.pdf` | 3.6 Generalization (over/underfitting) | 152–157 |
| `d2l_3_7_weight_decay.pdf` | 3.7 Weight Decay (L2 regularization) | 158–164 |
| `d2l_4_1_softmax_regression.pdf` | 4.1 Softmax Regression (incl. cross-entropy loss) | 165–172 |
| `d2l_5_1_multilayer_perceptrons.pdf` | 5.1 Multilayer Perceptrons | 207–214 |
| `d2l_5_3_forward_backward_propagation.pdf` | 5.3 Forward/Backward Propagation | 219–223 |
| `d2l_5_6_dropout.pdf` | 5.6 Dropout (regularization) | 234–238 |
| `d2l_12_3_gradient_descent.pdf` | 12.3 Gradient Descent | 522–531 |
| `d2l_12_4_stochastic_gradient_descent.pdf` | 12.4 Stochastic Gradient Descent | 532–538 |

Coverage gaps: D2L has **no separate logistic-regression section**. Binary classification is the two-class case of softmax regression (4.1). The from-scratch and concise implementation sections are left out because they are mostly code. D2L sections start mid-page, so the first page of most files also holds the end of the previous section (often its exercises). The ODS files each start at their chapter's first page.
