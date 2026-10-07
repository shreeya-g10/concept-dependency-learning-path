# Contributing (team guide)

How the four of us work in parallel without merge conflicts. Read this once before you start.

## Who owns what

**Golden rule: you only edit files you own.** Modules talk through JSON files, never by importing each other's code.

| Who | Owns (only they edit) | Builds | Hands off |
|---|---|---|---|
| **Vaidehi** (@vkumaw) | `cdlp/extraction/` · `website/Home.py`, `common.py`, `requirements.txt`, `pages/1_*` · `data/raw/`, `data/gold/` | PDF/PPT parsing, chunking, concept extraction, dedup · website shell + deployment · merging gold labels + κ | `chunks.jsonl`, `concepts.json` (Day 5) |
| **Sneha** (@snehadebnath26) | `cdlp/discovery/` · `website/pages/2_*` | Candidate filter, LLM discovery, baseline · quiz items · simulated students | `relationships.json` (Day 6) · `quiz_items.json`, `sim_students.json` (Day 7) |
| **Shreeya** (@shreeya-g10, lead) | `cdlp/validation/` · `website/pages/3_*` · `cdlp/shared/`, `pipeline.py`, root files, `docs/`, `.github/` | Validation agent + necessity test · ablations · reviews + integration | `validated_graph.json` (Day 7) |
| **Shrestha** (@shrestha035) | `cdlp/learning_path/` (incl. `api.py`) · `website/pages/4_*`, `pages/5_*` | Graph, adaptive diagnosis + personalized path · diagnosis evaluation | `student_state.json`, `learning_path.json` |

- Gold labels go only in your own file: `data/gold/annotations/annotator_<x>.csv` (a = Vaidehi, b = Sneha, c = Shreeya, d = Shrestha). Read `docs/annotation_guidelines.md` first.
- Your task list, in order, is in your module's `README.md` (e.g. `cdlp/validation/README.md`). The website split is in `website/README.md`.
- `.github/CODEOWNERS` asks the owner to review any change to their files.

## Developer setup

Follow **Quick start** in the [README](README.md), then also run:

```bash
nbstripout --install      # strips notebook outputs before every commit
```

Every module currently ships a stub that copies `cdlp/shared/examples/`, so `pytest`, `python pipeline.py` and the website all work from day one. Replace **your** stub with real code; everyone else's keeps working.

## Daily workflow

```bash
git checkout main && git pull
git checkout -b validation/necessity-test     # <your module>/<small-task>
# ...work only in files you own...
ruff format <your folder> && ruff check <your folder> && pytest <your folder>
git add <your files> && git commit -m "validation: add necessity test"
git push -u origin validation/necessity-test  # open a PR, merge the same day
```

## Rules that keep us conflict-free

1. **Only edit files you own.** Need a change elsewhere? Ask the owner.
2. **Small branches, merged daily.** Never sit on a branch for days. Pull `main` every morning.
3. **Contracts are frozen.** Formats are in `cdlp/shared/schemas/`, examples in `cdlp/shared/examples/`. Need a change? Ask Shreeya. Only *adding* an optional field is allowed, and `schema_version` gets bumped.
4. **Talk through files, not imports.** Read and write with `cdlp.shared.io`, which rejects anything that breaks a contract. Never import another person's module. The one exception is the website using `cdlp/learning_path/api.py`.
5. **Your libraries go in your own `requirements.txt`.** Never edit the root one.
6. **Never commit** `.env`, `outputs/`, `.cache/`, model files or notebook outputs (see `.gitignore`).
7. **All LLM calls go through `cdlp/shared/llm.py`.** It's free (Ollama), caches every response, and logs the model and prompt version for the paper.
8. **Prompts are files** in your `prompts/` folder (`discover_v1.txt`, `discover_v2.txt`), never long strings in code.
9. **Results** go in your own module's `results/`: small CSV/JSON files plus the config that produced them.

## Timeline (10 working days)

| Day | What happens |
|---|---|
| 1 | Everyone: clone, set up, read your module README, agree the annotation guidelines, label your gold share. Contracts are frozen. |
| 2–4 | Everyone builds against `cdlp/shared/examples/`. Nobody waits for anybody. |
| 5 | **Hand-off 1:** Vaidehi's real `concepts.json` + `chunks.jsonl` |
| 6 | **Hand-off 2:** Sneha's real `relationships.json` |
| 7 | **Hand-off 3:** Shreeya's `validated_graph.json` + Sneha's quiz items and simulated students. **First full real run:** `python pipeline.py` |
| 8–9 | Evaluation, ablations, website pages |
| 10 | Results tables, deployed website, demo |

A hand-off means: run your CLI on the real input, check the output with `python -m cdlp.shared.validate outputs/<file>`, and post in the group. Downstream modules then read from `outputs/` instead of `cdlp/shared/examples/`.

## AI assistance

`CLAUDE.md` gives AI coding assistants (Claude Code) the project context and these ownership rules. We disclose AI-assisted development in the paper, as venues require.
