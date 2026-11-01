# Root cause · owner: Shreeya

Root-cause tracing: which concept is really behind a wrong answer?

**Question you answer:** *This student got the AVL question wrong. Is the gap in AVL trees, or further back in BSTs?*

**You own (only you edit):** `cdlp/root_cause/` (including `api.py`)

| | File | Notes |
|---|---|---|
| Input | `validated_graph.json`, `quiz_items.json`, `student_answers.json` | Until real answers exist use `cdlp/shared/examples/` |
| Output | `root_cause.json` | Per wrong answer: traced concept, ranked candidates, confidence, explanation |
| Public API | `api.py` | `trace(graph, quiz_item, answer, mastery) -> dict`. The website calls it; keep the signature stable |

Use **ACCEPT edges only** for the prerequisite chain. `pipeline.py` runs this step only when `student_answers.json` exists.

## Tasks, in order
- [x] Prerequisite chain: the item's concept plus its ancestors over ACCEPT edges (NetworkX), nearest first
- [x] LLM tracing (`prompts/trace_v1.txt`): the LLM reads the question, the wrong answer, the correct answer and the prerequisite chain with mastery, and returns ranked candidate concepts with scores and a short explanation. All calls go through `cdlp/shared/llm.py`
- [x] Implement `api.trace` with it, then make the CLI call `api.trace` for every wrong answer in `student_answers.json`
- [x] Baselines for the paper: **blame the target** (always the item's own concept; the current stub) and **blame the nearest prerequisite** (the direct ACCEPT prerequisite with the lowest mastery)
- [ ] **RQ3:** top-1 / top-3 accuracy of LLM tracing vs both baselines against Vaidehi's test set `data/gold/root_cause_testset.json` → `cdlp/root_cause/results/`. Never tune the prompt on the test set
- [x] Tests mock the LLM with `monkeypatch` (see `tests/test_contract.py`)

## How to run
- CLI: `python -m cdlp.root_cause --graph ... --quiz ... --answers ... [--state student_state.json] [--method llm|target|nearest] --out root_cause.json`. `--state` gives each student's mastery; without it mastery is unknown.
- Dev set (my labels, built from the shared example items): `tests/fixtures/dev_set.json`. Tune the prompt here only.
- Evaluate: `python -m cdlp.root_cause.evaluate --dataset <file> --graph ... --quiz ... --methods llm target nearest` → `results/<name>.json` with config, per-row predictions, top-1/top-3 and LLM fallback count.
- Unusable LLM output falls back to the nearest-prerequisite baseline, marked `[fallback: nearest prerequisite]` in the explanation. A concept with no prerequisites gets no LLM call.

## Done when
The CLI writes `root_cause.json` from real answers, RQ3 results for the LLM and both baselines are in `cdlp/root_cause/results/`, and `pytest cdlp/root_cause` passes.
