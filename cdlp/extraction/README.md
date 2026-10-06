# Extraction · owner: Vaidehi

Content extraction, plus the website shell and gold data.

**Question you answer:** *What concepts are in this course, and where?*

**You own (only you edit):**
- `cdlp/extraction/`
- `website/Home.py`, `website/common.py`, `website/requirements.txt`, `website/pages/1_Course_Material.py`
- `data/raw/`, `data/gold/` (merged gold files)

| | File | Notes |
|---|---|---|
| Input | PDFs / PPTX in `data/raw/` | Start with the Data Structures lectures |
| Output | `chunks.jsonl` | One chunk ≈ 300–500 tokens; keep `doc`, `page`, `heading` |
| Output | `concepts.json` | Stable slug ids (`binary_search_tree`), aliases merged |

Format and example: `cdlp/shared/schemas/`, `cdlp/shared/examples/`.

## Tasks, in order
- [ ] **Day 1:** collect the course PDFs into `data/raw/`. Label your share of gold edges in `data/gold/annotations/annotator_a.csv`
- [ ] PDF extraction (PyMuPDF) and PPTX extraction (python-pptx), keeping page/slide numbers
- [ ] Cleaning + chunking → `chunks.jsonl`
- [ ] LLM concept extraction per chunk (`prompts/extract_v1.txt`, via `cdlp/shared/llm.py`)
- [ ] Canonicalization: merge "BST" / "Binary Search Tree" (embeddings + LLM check), keep aliases
- [ ] Granularity filter: drop too-fine ("Left Subtree") and too-broad ("Computer Science") concepts
- [ ] **Day 5: hand off real `chunks.jsonl` + `concepts.json`** (post in the group when they're ready)
- [ ] Merge everyone's annotation files into `data/gold/gold_edges.csv` + `gold_concepts.json`, and report Cohen's κ
- [ ] Evaluation: concept precision / recall / F1 vs gold → `cdlp/extraction/results/`
- [ ] Website shell: navigation, styling, course selector, page 1; deploy free on Streamlit Community Cloud

## Done when
`python -m cdlp.extraction --input data/raw --out-dir outputs` writes both files from the real PDFs, the site is deployed, and `pytest cdlp/extraction` passes.
