# Course material

One folder per course (`data/raw/<course_id>/`). `python pipeline.py --course <course_id>` reads it.
Only openly licensed material goes here. If a file can't be shared, keep it local and list its name here so everyone knows to ask for it.

The old stub lectures (`ds_lec*.pdf`, `ds_lec8.pptx`, `ml_lec*.pdf`) are now test fixtures in `cdlp/extraction/tests/fixtures/`.

Two kinds of files:
- **PDF** files are pages cut, unmodified, from the book PDF named for them (PyMuPDF `insert_pdf`, 2026-11-02). Page numbers in `chunks.jsonl` count from 1 within each file. To get the page in the book PDF, add `first page − 1`.
- **Markdown** files (second sources, for topics the main book lacks) are converted from the source text. Headings and prose are kept; figures, code, interactive visualizations, tables and exercises are removed. Extraction numbers their sections (`page` = section number, `heading` = section title; see `cdlp/extraction/parse.py`). Each file starts with an HTML comment naming its source and licence.

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

Coverage gaps: ODS has **no AVL-tree chapter** (AVL trees appear only in the exercises), no chapter on general (non-binary) trees, and no separate recursion chapter. Recursion is taught inside 6.1 (recursive traversal). Balanced trees are covered by scapegoat and red-black trees. These gaps are filled from OpenDSA (next section).

## ds101 second source: OpenDSA (AVL trees, general trees, recursion)

- Site: https://opendsa.org/ (source: https://github.com/OpenDSA/OpenDSA)
- Version: commit **`f900a7aa3d7fd4289b82a767e4958974eb3e9d17`** (2026-10-27). The RST files were downloaded from `https://raw.githubusercontent.com/OpenDSA/OpenDSA/<commit>/RST/en/<path>.rst` on 2026-11-02.
- Licence: **MIT** (`MIT-license.txt` in the repository: "OpenDSA Project. Distributed under the MIT License. Copyright (c) 2011-2025 - Ville Karavirta and Cliff Shaffer"). Each RST file's header says the same. MIT permits copying and modification as long as the copyright notice is kept; it is in each file's header comment and here.
- Changes: RST converted to Markdown (headings and prose kept; `avembed`, `inlineav`, `odsafig`, code, `avmetadata` and other directives removed; `:term:`/`:math:` roles reduced to their text).
- Not used: *Problem Solving with Algorithms and Data Structures* (Miller & Ranum), checked first. Its official repository (`RunestoneInteractive/pythonds`, `LICENSE.txt`) says CC BY-NC-SA 4.0. NonCommercial is not clearly open, so it was left out.

| File | Source (`RST/en/…`) | Source SHA-256 | Topic |
|---|---|---|---|
| `opendsa_recursion_intro.md` | `RecurTutor/RecIntro.rst` | `ecf202c176ee3084ea4be8ac21bb474ecc20e27b4efcd5dae63278d5b59a862a` | recursion: base case, recursive call |
| `opendsa_recursion_writing.md` | `RecurTutor/Write.rst` | `df67a98aae7f207eef544d70ab0831ebe50405a9f98e0ef6a48d517affdfa704` | writing recursive functions |
| `opendsa_recursion_tracing.md` | `RecurTutor/Trace.rst` | `3e6717db99d529ca9151a67e2a0d2729a2798e5cd9b9574e0acd7b0828131d14` | tracing recursion, Towers of Hanoi |
| `opendsa_general_trees.md` | `General/GenTreeIntro.rst` | `1ebe8cf589c2cd67706755a19498d37f73a8a6765e1f22876a601a0879f1347b` | general (non-binary) trees |
| `opendsa_balanced_trees.md` | `SearchStruct/BalancedTree.rst` | `504c6920779be7dea04773052d90d88aee3e041e438a972c5bb7f32e4beb9bea` | why BSTs need balancing |
| `opendsa_avl_trees.md` | `SearchStruct/AVL.rst` | `306f8d021fa6167b08124910ebb03f20bf68e5f789b907e01b600ce45dcbc6e4` | AVL trees, rotations |

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

Coverage gaps: D2L has **no separate logistic-regression section**. Binary classification is the two-class case of softmax regression (4.1). The from-scratch and concise implementation sections are left out because they are mostly code. D2L sections start mid-page, so the first page of most files also holds the end of the previous section (often its exercises). The ODS files each start at their chapter's first page. Logistic regression comes from OpenIntro IMS (next section).

## ml101 second source: Introduction to Modern Statistics (logistic regression)

- Site: https://openintrostat.github.io/ims/ (the book's official site; publisher page https://www.openintro.org/book/ims/; source https://github.com/OpenIntroStat/ims)
- Version: **2nd edition**, web version built from repository commit `b88f367ac03a7b2998812d0dd49d57a8493c3b84` (2026-04-01). The chapter page was downloaded on 2026-11-02.
- Licence: **CC BY-SA 3.0**, https://creativecommons.org/licenses/by-sa/3.0/. The book's front matter says it is "available under a Creative Commons Attribution-ShareAlike 3.0 Unported United States License", and https://www.openintro.org/license/ says the statistics textbooks are CC BY-SA 3.0. As with D2L, anything derived from this text that we share stays CC BY-SA. OpenIntro's name and branding may not be used to suggest endorsement.
- Attribution: Mine Çetinkaya-Rundel and Johanna Hardin, *Introduction to Modern Statistics*, 2nd edition, OpenIntro. Changes: the chapter was converted to Markdown from the rendered page (computed values included); code, R output, figures, tables and the exercises (9.6) removed.

| File | Source | Source SHA-256 | Topic |
|---|---|---|---|
| `ims_09_logistic_regression.md` | https://openintrostat.github.io/ims/model-logistic.html | `de5535d073d230409a64812c31652e984910c6be1b4727c4a5cfe93c496dbbd0` | 9 Logistic regression (logit, GLM, multiple predictors) |

`python scripts/fetch_second_sources.py` rebuilds every Markdown file above from the pinned sources and stops if a download's SHA-256 differs; `--check` only reports whether a file would change. The SHA-256 values are for the downloaded source files (RST or HTML). The Markdown files are derived from them, so their hashes change if the conversion changes.
