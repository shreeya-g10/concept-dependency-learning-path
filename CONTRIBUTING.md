# Contributing (team guide)

How the two of us work in parallel without merge conflicts. Read this once before you start.

## Who owns what

**Golden rule: you only edit files you own.** Modules talk through JSON files, never by importing each other's code.

| Who | Owns (only they edit) | Builds | Hands off |
|---|---|---|---|
| **Vaidehi** (@vkumaw) | `cdlp/extraction/` · `cdlp/learning_path/` (incl. `api.py`) · `cdlp/discovery/quiz.py`, `cdlp/discovery/sim_students.py` · `website/` except pages 2 and 3 · `data/raw/`, `data/gold/` | PDF/PPT parsing, chunking, concept extraction, dedup · graph, adaptive diagnosis + personalized path · quiz items, simulated students · website shell + deployment, pages 1, 4, 5 · merging gold labels + κ | `chunks.jsonl`, `concepts.json` · `quiz_items.json`, `sim_students.json` · `student_state.json`, `learning_path.json` |
| **Shreeya** (@shreeya-g10, lead) | everything else: `cdlp/discovery/` (except the two files above) · `cdlp/validation/` · `cdlp/root_cause/` · `cdlp/benchmarks/` · `website/pages/2_*`, `pages/3_*` · `cdlp/shared/`, `pipeline.py`, root files, `docs/`, `.github/` | Candidate filter, LLM discovery, baseline · validation agent + necessity test · root-cause tracing · public benchmarks · ablations · reviews + integration | `relationships.json`, `validated_graph.json` |

Sneha (@snehadebnath26) and Shrestha (@shrestha035) contributed the initial discovery and learning-path code.

- Gold labels go only in your own file: `data/gold/annotations/annotator_<x>.csv` (a = Vaidehi, c = Shreeya; b and d are the earlier labels from Sneha and Shrestha). Read `docs/annotation_guidelines.md` first.
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
4. **Talk through files, not imports.** Read and write with `cdlp.shared.io`, which rejects anything that breaks a contract. Never import another person's module. The one exception is the website using `cdlp/learning_path/api.py` and `cdlp/root_cause/api.py`.
5. **Your libraries go in your own `requirements.txt`.** Never edit the root one.
6. **Never commit** `.env`, `outputs/`, `.cache/`, model files or notebook outputs (see `.gitignore`).
7. **All LLM calls go through `cdlp/shared/llm.py`.** It's free (Ollama), caches every response, and logs the model and prompt version for the paper.
8. **Tests must never call a real LLM — mock it with `monkeypatch`.** CI has no Ollama; run `python pipeline.py` locally for a real end-to-end run.
9. **Prompts are files** in your `prompts/` folder (`discover_v1.txt`, `discover_v2.txt`), never long strings in code.
10. **Results** go in your own module's `results/`: small CSV/JSON files plus the config that produced them.

## Timeline (4 phases, 20 working days)

| Phase | Days | What happens |
|---|---|---|
| 0 | 1–2 | **Contracts and handover.** Ownership moves to two people; contracts are frozen; read the inherited discovery and learning-path code. |
| 1 | 3–7 | **Finish inherited work.** Real `concepts.json` + `chunks.jsonl` → `relationships.json` → `validated_graph.json`, plus quiz items and simulated students. **First full real run:** `python pipeline.py` |
| 2 | 8–12 | **Novelties.** Validation agent with all checks + necessity test; adaptive diagnosis and personalized paths; root-cause tracing. |
| 3 | 13–16 | **Experiments.** RQ1 ablations, RQ2 on simulated students, public benchmarks; results tables and website pages. |
| 4 | 17–20 | **Real-student study and paper.** Pre/post test with real students, deployed website, paper draft. |

A hand-off means: run your CLI on the real input, check the output with `python -m cdlp.shared.validate outputs/<file>`, and post in the group. Downstream modules then read from `outputs/` instead of `cdlp/shared/examples/`.

## AI assistance

`CLAUDE.md` gives AI coding assistants (Claude Code) the project context and these ownership rules. We disclose AI-assisted development in the paper, as venues require.
