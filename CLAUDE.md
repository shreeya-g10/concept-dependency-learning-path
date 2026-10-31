# CLAUDE.md

Context for Claude Code working in this repository.

## What this project is

A Gen AI lab research project. The goal is a **publishable research paper** plus a working prototype.

**One-line summary:** Take raw course material (PDF/PPT/notes), extract concepts, propose prerequisite relationships with an LLM, verify them with an independent **Validation Agent**, build an explainable concept-dependency graph, and generate a **learning path that adapts to what each individual student already knows**.

```
Course PDF / PPT
   → Concept Extraction (+ source page/slide)
   → Dependency Discovery (candidate prerequisite edges)
   → Validation Agent (ACCEPT / REJECT / HUMAN_REVIEW, with evidence)
   → Validated Knowledge Graph (DAG, explainable edges)
   → Student Knowledge State (what this student already knows)
   → Personalized Learning Path for a target concept
```

Running example used throughout the plan (Data Structures):
`Trees → Binary Trees → Binary Search Trees → AVL Trees`. Second domain for generality: an ML course (`Vectors → Matrices → Linear Regression → Gradient Descent → Neural Networks`).

The original plan is `docs/original_plan.docx`. `README.md` describes the project; `CONTRIBUTING.md` is the team guide (ownership, workflow, timeline).

## Research contributions (what the paper claims)

We do **not** claim prerequisite discovery itself is new (prior work: PCPL 2024, ACE 2024, LCPRE 2024, GKROM 2025, prerequisite-based course recommendation 2024). Our contributions are:

1. **Agent-based validation** of LLM-proposed prerequisite edges using (a) evidence retrieved from the course material, (b) semantic/pedagogical reasoning, (c) graph-consistency checks (cycles, duplicates, contradictions, transitive redundancy).
   Core RQ: *Does an independent validation agent improve the precision of LLM-generated prerequisite relations, and at what cost to recall?*
2. **Student-adaptive learning paths** (main novelty). The course graph is shared; each student gets a different prerequisite path depending on their knowledge state. If a student already knows a concept, that branch is pruned and recommendations change.
3. **Explainability:** every edge carries a confidence, the evidence chunk (doc + page), and a short rationale.
4. An end-to-end pipeline from raw material to personalized path, evaluated stage by stage.

### How personalization is modelled (current direction)

- There is **one global, validated course graph** per course. Prerequisite edges are a property of the concepts, not of the student.
- Personalization is a **student-specific overlay**: a knowledge state (mastered / not mastered / unknown, or a mastery probability per concept).
- Edges have a **necessity strength** (hard vs. soft prerequisite), so a soft prerequisite can be skipped depending on the student's background.
- The knowledge state is estimated by a **graph-guided diagnostic**: knowing a concept is evidence for knowing its ancestors; failing one is evidence of gaps in it or its ancestors. This should need fewer quiz questions than testing every concept.
- Personalized path = (ancestors of target) minus (mastered concepts), in topological order. Ties are broken by edge strength and mastery probability.

Relevant theory to cite and build on: Knowledge Space Theory (Doignon & Falmagne; ALEKS), Bayesian Knowledge Tracing, Deep Knowledge Tracing.

## Key design rules

- **The graph must stay a DAG.** Any edge that would create a cycle is never auto-accepted. It goes to the validator or to HUMAN_REVIEW.
- Store the **full graph and its transitive reduction** separately. Do not add redundant edges such as `Trees → AVL Trees` when `Trees → … → AVL Trees` already exists. Paths and visualizations use the reduced graph.
- **Concept canonicalization is required** before dependency discovery. Example: "BST", "Binary Search Tree" and "binary search trees" become one node, with aliases kept.
- **Don't send all O(n²) concept pairs to the LLM.** Generate candidates first (embedding similarity, co-occurrence in a chunk, ordering in the syllabus/material), then run LLM discovery on the candidates only.
- The validator should not be the same prompt or model call that proposed the edge. Use a separate prompt, and ideally a separate model, grounded in retrieved evidence, to avoid correlated errors.
- Every pipeline stage writes **structured, versioned outputs** (JSON/JSONL) so stages can be evaluated and ablated independently.
- Every LLM prompt lives in its own file (not inline strings) and is versioned. Results must record the model ID, prompt version and temperature.
- Prerequisite is the only relation type in scope for the paper. Other types (related, sub-concept, extension, application) are future work.

## Core data shapes (target, refine as code is written)

```jsonc
// concept
{ "id": "bst", "name": "Binary Search Tree", "aliases": ["BST"], "sources": [{"doc": "ds_lec7.pdf", "page": 18}] }
// candidate / validated edge
{ "source": "binary_tree", "target": "bst", "type": "PREREQUISITE",
  "discovery_confidence": 0.89, "strength": "hard",
  "validation": { "decision": "ACCEPT", "confidence": 0.9,
                  "evidence": [{"doc": "ds_lec7.pdf", "page": 18, "text": "..."}],
                  "checks": {"evidence": "strong", "semantic": "strong", "graph": "valid"},
                  "rationale": "..." } }
// student knowledge state
{ "student_id": "s01", "course": "ds", "mastery": { "trees": 0.95, "binary_tree": 0.8, "bst": 0.3 } }
```

## Evaluation plan (must be supported by the code)

- **Concept extraction:** P/R/F1 against a hand-annotated concept list.
- **Dependency discovery and validation:** P/R/F1 against gold edges. Use public benchmarks where possible (e.g. AL-CPL, University Course dataset, LectureBank) plus our own annotated course with inter-annotator agreement (Cohen's κ).
- **Ablations:** discovery only, discovery + single LLM-judge, discovery + full validation agent, and the agent without each check (evidence / semantic / graph). Also report the HUMAN_REVIEW rate.
- **Personalization:** simulated students with known ground-truth knowledge states (offline), measuring diagnosis accuracy, number of questions asked and path length reduction. Then a small real-student study if time allows (pre/post test).
- **Learning paths:** order violations against the gold graph, plus educator ratings.

Any experiment script must be reproducible: fixed seeds, configs in files, results written to the module's own `results/` folder with the config that produced them.

## Team, modules and ownership (20-day plan in 4 phases, 2 people)

Each person owns specific paths (see `CONTRIBUTING.md`, `website/README.md` and `.github/CODEOWNERS`). **Only edit paths owned by the person you are working for.** If you don't know who that is, ask before editing. Never edit someone else's paths unless the user says the owner agreed.

| Person | Owns | Builds | Writes |
|---|---|---|---|
| Vaidehi | `cdlp/extraction/`, `cdlp/learning_path/` (incl. `api.py`), `cdlp/discovery/quiz.py`, `cdlp/discovery/sim_students.py`, `website/` except `pages/2_*` and `pages/3_*`, `data/raw/`, `data/gold/` | parsing, chunking, concept extraction, dedup; graph, adaptive diagnosis, personalized path, RQ2 eval; quiz items; simulated students; website shell + deployment; gold merge + kappa | `chunks.jsonl`, `concepts.json`, `quiz_items.json`, `sim_students.json`, `student_state.json`, `learning_path.json` |
| Shreeya (team lead) | everything else: `cdlp/discovery/` (except the two files above), `cdlp/validation/`, `cdlp/root_cause/`, `cdlp/benchmarks/`, `website/pages/2_*`, `website/pages/3_*`, `cdlp/shared/`, `pipeline.py`, root files, `docs/`, `.github/` | candidate filter, LLM discovery (hard/soft); validation agent + simulated-learner necessity test, RQ1 ablations; root-cause tracing (`cdlp/root_cause/`); public datasets (`cdlp/benchmarks/`); contracts and integration | `relationships.json`, `validated_graph.json` |

Sneha and Shrestha contributed the initial discovery and learning-path code.

Each module's `README.md` (e.g. `cdlp/validation/README.md`) is its owner's task list. Annotators write only to their own `data/gold/annotations/annotator_<x>.csv` (a = Vaidehi, c = Shreeya; b and d hold the earlier labels from Sneha and Shrestha).

The website is a multi-page Streamlit app in `website/`. Pages read contract files via `website/common.py` (falling back to `cdlp/shared/examples/`). The only module code a page may import is `cdlp/learning_path/api.py` and `cdlp/root_cause/api.py`; keep their function signatures stable.

Root-cause tracing lives in `cdlp/root_cause/` (Phase 2) and the real-student study is Phase 4. The ML second domain is out of scope.

### Integration rules

- **Modules talk through JSON files only, never by importing each other's code.** Each module is run as `python -m <module> ...` (see its `__main__.py`). `pipeline.py` only calls these CLIs.
- Read and write contract files with `cdlp.shared.io` (`read_json`, `write_json`, ...). Writes are validated against `cdlp/shared/schemas/`, and the schema is picked from the file-name ending.
- Contracts are frozen: only additive optional fields, a bumped `schema_version`, and lead approval. `cdlp/shared/examples/` is the canonical mock data for every stage.
- Concept IDs are stable slugs (`binary_search_tree`), not positional IDs like `C001`.
- `validated_graph.json` keeps every decision (ACCEPT / REJECT / HUMAN_REVIEW). Downstream code uses ACCEPT edges only.
- All LLM calls go through `cdlp/shared/llm.py`, which caches responses and logs the model and prompt version. Prompts live as versioned files in the module's `prompts/` folder.
- A module's dependencies go in its own `requirements.txt`; results go in its own `results/`. Module folders are named by function (`cdlp/extraction`, `cdlp/discovery`, `cdlp/validation`, `cdlp/learning_path`, `cdlp/root_cause`, `cdlp/benchmarks`), never by person; branches are `<module>/<task>`.
- Never commit `outputs/`, `.cache/`, `.env`, `.streamlit/secrets.toml` or notebook outputs. Keep `pytest` and `python pipeline.py` passing.

## Tech stack (free only)

**Every tool must be free.** Never add paid APIs or paid services.

- Python 3.10+
- LLMs: local open models via Ollama (default `qwen2.5:7b-instruct`, validator `llama3.1:8b`), or a free-tier OpenAI-compatible endpoint configured in `.env`
- Embeddings and retrieval: sentence-transformers, FAISS
- Graph: NetworkX
- Parsing: PyMuPDF, python-pptx
- Website: Streamlit (multi-page) + pyvis, hosted free on Streamlit Community Cloud
- Tooling: jsonschema, pytest, ruff, GitHub Actions

Ask before adding anything not listed here.

## Working with the user

- This is a team student research project. Explain non-obvious design choices briefly, since they will need to defend them in the paper.
- Flag anything that weakens the research claim, such as data leakage between annotation and evaluation, no baseline, or an unverifiable citation.
- Do not invent citations. If a paper is referenced, say it needs verification unless the user has supplied it.
