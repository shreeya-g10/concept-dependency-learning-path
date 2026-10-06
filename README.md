# Concept Dependency Learning Path

Course material in → validated prerequisite graph → a different learning path for every student, shown on a website.
Gen AI lab research project · 4 members · 2-week sprint · **100% free tools**.

```
PDF/PPT ─▶ Vaidehi ─────▶ Sneha ─────────▶ Shreeya ──────────▶ Shrestha ─────────────▶ website
           extraction     discovery        validation agent    graph + adaptive path
           chunks.jsonl   relationships    validated_graph     student_state
           concepts.json  quiz_items                           learning_path
                          sim_students
```

## Who owns what

**Golden rule: you only edit files you own.** Modules talk through JSON files, never by importing each other's code.

| Who | Owns (only they edit) | Builds | Hands off |
|---|---|---|---|
| **Vaidehi** | `cdlp/extraction/` · `website/Home.py`, `common.py`, `requirements.txt`, `pages/1_*` · `data/raw/`, `data/gold/` | PDF/PPT parsing, chunking, concept extraction, dedup · website shell + deployment · merging gold labels + κ | `chunks.jsonl`, `concepts.json` (Day 5) |
| **Sneha** | `cdlp/discovery/` · `website/pages/2_*` | Candidate filter, LLM discovery, baseline · quiz items · simulated students | `relationships.json` (Day 6) · `quiz_items.json`, `sim_students.json` (Day 7) |
| **Shreeya** (lead) | `cdlp/validation/` · `website/pages/3_*` · `cdlp/shared/`, `pipeline.py`, root files, `docs/`, `.github/` | Validation agent + **necessity test** (novelty 1) · ablations · reviews + integration | `validated_graph.json` (Day 7) |
| **Shrestha** | `cdlp/learning_path/` (incl. `api.py`) · `website/pages/4_*`, `pages/5_*` | Graph, **adaptive diagnosis + personalized path** (novelty 2) · RQ2 evaluation | `student_state.json`, `learning_path.json` |

Everyone labels gold edges only in their own file, `data/gold/annotations/annotator_<x>.csv` (a = Vaidehi, b = Sneha, c = Shreeya, d = Shrestha).
Your full task list is in your module's `README.md` (e.g. `cdlp/validation/README.md`). The website split is in `website/README.md`.

## Setup (once)

```bash
git clone https://github.com/shreeya-g10/concept-dependency-learning-path.git
cd concept-dependency-learning-path
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env
nbstripout --install
```

Free LLM: install [Ollama](https://ollama.com), then run `ollama pull qwen2.5:7b-instruct` and `ollama pull llama3.1:8b`.
If your laptop is too slow, `.env.example` shows how to use a free-tier hosted endpoint instead.

Check everything works:

```bash
pytest -q
python pipeline.py
streamlit run website/Home.py
```

All three already work: every module is a stub that copies `cdlp/shared/examples/`. Replace **your** stub with real code; everyone else's keeps working.

## Daily workflow

```bash
git checkout main && git pull
git checkout -b validation/necessity-test  # <your module>/<small-task>
# ...work only in files you own...
ruff format <your folder> && ruff check <your folder> && pytest <your folder>
git add <your files> && git commit -m "validation: add necessity test"
git push -u origin validation/necessity-test  # open a PR, merge the same day
```

## Rules that keep us conflict-free

1. **Only edit files you own** (table above; enforced by `.github/CODEOWNERS`). Need a change elsewhere? Ask the owner.
2. **Small branches, merged daily.** Never sit on a branch for days. Pull `main` every morning.
3. **Contracts are frozen.** Formats are in `cdlp/shared/schemas/`, examples in `cdlp/shared/examples/`. Need a change? Ask Shreeya. Only *adding* an optional field is allowed, and `schema_version` gets bumped.
4. **Talk through files, not imports.** Read and write with `cdlp.shared.io`, which rejects anything that breaks a contract. Never import another person's module. The one exception is the website using `cdlp/learning_path/api.py`.
5. **Your libraries go in your own `requirements.txt`.** Never edit the root one.
6. **Never commit** `.env`, `outputs/`, `.cache/`, model files or notebook outputs.
7. **All LLM calls go through `cdlp/shared/llm.py`.** It's free (Ollama), caches every response, and logs the model and prompt version for the paper.
8. **Prompts are files** in your `prompts/` folder (`discover_v1.txt`, `discover_v2.txt`), never long strings in code.
9. **Results** go in your own folder's `results/`: small CSV/JSON files plus the config that produced them.

## Timeline (10 working days)

| Day | What happens |
|---|---|
| 1 | Everyone: clone, set up, read your README, agree the annotation guidelines, label your gold share. Contracts are frozen. |
| 2–4 | Everyone builds against `cdlp/shared/examples/`. Nobody waits for anybody. |
| 5 | **Hand-off 1:** Vaidehi's real `concepts.json` + `chunks.jsonl` |
| 6 | **Hand-off 2:** Sneha's real `relationships.json` |
| 7 | **Hand-off 3:** Shreeya's `validated_graph.json` + Sneha's quiz items and simulated students. **First full real run:** `python pipeline.py` |
| 8–9 | Evaluation, ablations, website pages |
| 10 | Results tables, deployed website, demo |

A hand-off means: run your CLI on the real input, check the output with `python -m cdlp.shared.validate outputs/<file>`, and post in the group. Downstream members then point their input at `outputs/` instead of `cdlp/shared/examples/`.

## Free tech stack

Python · Ollama (Qwen 2.5 7B, Llama 3.1 8B) · sentence-transformers · FAISS · NetworkX · PyMuPDF · python-pptx · Streamlit + pyvis (free hosting on Streamlit Community Cloud) · jsonschema · pytest · ruff · GitHub + Actions

Research plan: `docs/original_plan.docx`, plus the team master-plan doc (ask Shreeya for access).

## Repository notes

- `.github/CODEOWNERS` records who reviews each part of the codebase.
- `CLAUDE.md` gives AI coding assistants (Claude Code) the project context and ownership rules. We disclose AI-assisted development in the paper, as venues require.
