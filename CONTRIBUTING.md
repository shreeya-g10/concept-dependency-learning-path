# Contributing (maintainer guide)

How the project is run. Read this once before you start.

## Maintainer

Since 2026-11-02 the project has one maintainer, **Shreeya** (@shreeya-g10), who owns and reviews every path (`.github/CODEOWNERS`). The module boundaries stay: modules talk through JSON files, never by importing each other's code, so every stage can be tested, evaluated and ablated on its own.

| Module | Builds | Hands off |
|---|---|---|
| `cdlp/extraction/` | PDF/PPT parsing, chunking, concept extraction, dedup | `chunks.jsonl`, `concepts.json` |
| `cdlp/discovery/` | candidate filter, LLM discovery, baseline | `relationships.json` |
| `cdlp/validation/` | validation agent + necessity test, RQ1 ablations | `validated_graph.json` |
| `cdlp/learning_path/` | graph, quiz items, simulated students, adaptive diagnosis, personalized path | `quiz_items.json`, `sim_students.json`, `student_state.json`, `learning_path.json` |
| `cdlp/root_cause/` | root-cause tracing of wrong answers | `root_cause.json` |
| `cdlp/benchmarks/` | public benchmarks in our formats | benchmark files |
| `cdlp/shared/`, `pipeline.py`, `website/`, `data/`, `docs/` | contracts, integration, website, gold data, paper | |

- Gold labels are frozen per annotator in `data/gold/annotations/annotator_<x>.csv` (a = Vaidehi, c = Shreeya; b and d are the earlier labels from Sneha and Shrestha). Never edit another annotator's file. Read `docs/annotation_guidelines.md` first.
- Each module's task list is in its `README.md` (e.g. `cdlp/validation/README.md`).

## Contributors

- **Vaidehi** (@vkumaw): extraction, learning path, website shell, gold labels (annotator a), root-cause test set.
- **Sneha** (@snehadebnath26): initial discovery code.
- **Shrestha** (@shrestha035): initial learning-path code.

## Developer setup

Follow **Quick start** in the [README](README.md), then also run:

```bash
nbstripout --install      # strips notebook outputs before every commit
```

Every module currently ships a stub that copies `cdlp/shared/examples/`, so `pytest`, `python pipeline.py` and the website all work from day one. Replace a stub with real code and every other stage keeps working.

## Daily workflow

```bash
git checkout main && git pull
git checkout -b validation/necessity-test     # <module>/<small-task>
ruff format <changed files> && ruff check . && pytest -q
git add <changed files> && git commit -m "validation: add necessity test"
git push -u origin validation/necessity-test  # open a PR; merge once CI is green
```

## Rules

1. **One PR per task, never on `main`.** Small branches named `<module>/<task>`, merged once CI is green.
2. **Contracts are frozen.** Formats are in `cdlp/shared/schemas/`, examples in `cdlp/shared/examples/`. Only *adding* an optional field is allowed, and `schema_version` gets bumped (log it in `cdlp/shared/CHANGELOG.md`).
3. **Talk through files, not imports.** Read and write with `cdlp.shared.io`, which rejects anything that breaks a contract. Never import another module's code. The one exception is the website using `cdlp/learning_path/api.py` and `cdlp/root_cause/api.py`.
4. **A module's libraries go in its own `requirements.txt`.** Never edit the root one.
5. **Never commit** `.env`, `outputs/`, `.cache/`, model files or notebook outputs (see `.gitignore`).
6. **All LLM calls go through `cdlp/shared/llm.py`.** It's free (Ollama), caches every response, and logs the model and prompt version for the paper.
7. **Tests must never call a real LLM — mock it with `monkeypatch`.** CI has no Ollama; run `python pipeline.py` locally for a real end-to-end run.
8. **Prompts are files** in the module's `prompts/` folder (`discover_v1.txt`, `discover_v2.txt`), never long strings in code.
9. **Results** go in the module's own `results/`: small CSV/JSON files plus the config that produced them.

## Timeline (4 phases, 20 working days)

| Phase | Days | What happens |
|---|---|---|
| 0 | 1–2 | **Contracts and handover.** Contracts are frozen; read the inherited discovery and learning-path code. |
| 1 | 3–7 | **Finish inherited work.** Real `concepts.json` + `chunks.jsonl` → `relationships.json` → `validated_graph.json`, plus quiz items and simulated students. **First full real run:** `python pipeline.py` |
| 2 | 8–12 | **Novelties.** Validation agent with all checks + necessity test; adaptive diagnosis and personalized paths; root-cause tracing. |
| 3 | 13–16 | **Experiments.** RQ1 ablations, RQ2 on simulated students, public benchmarks; results tables and website pages. |
| 4 | 17–20 | **Real-student study and paper.** Pre/post test with real students, deployed website, paper draft. |

A hand-off means: run the module's CLI on the real input and check the output with `python -m cdlp.shared.validate outputs/<file>`. Downstream modules then read from `outputs/` instead of `cdlp/shared/examples/`.

## AI assistance

`CLAUDE.md` gives AI coding assistants (Claude Code) the project context and these rules. We disclose AI-assisted development in the paper, as venues require.
