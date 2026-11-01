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
- `api.trace(..., allow_fallback=True)` (keyword only, default False): if the LLM is unreachable (connection refused or timeout), returns the nearest-prerequisite baseline marked `[fallback: offline estimate]` instead of raising. Meant for the website; experiments and the CLI keep the strict default, and HTTP errors such as an unknown model always raise.

## RQ3 protocol (for the paper)
- **No mastery for any method.** RQ3 traces every wrong answer with mastery unknown, for the LLM and both baselines alike, so the comparison measures what each method gets from the question, the wrong answer and the graph, not from a separately estimated knowledge state (and the test set has no mastery to give). Run `evaluate.py` without `--state` and with `--no-mastery`. In the prompt every concept then shows `mastery unknown`.
- **Blame the target:** the item's own concept, then its ACCEPT ancestors by graph distance, then concept id.
- **Blame the nearest prerequisite:** among the item concept's direct ACCEPT prerequisites, the one with the lowest mastery (unknown counts as 0.5). With no mastery all of them tie, and ties break by graph distance, then concept id (alphabetical). So in the RQ3 setting this baseline picks the alphabetically first direct prerequisite; edge strength (hard/soft) is not used. The rest of the ranking is the other direct prerequisites, then the target, then the remaining ancestors by distance, then id. A concept with no prerequisites blames itself.
- **LLM tracing:** `prompts/trace_v1.txt`, model `LLM_MODEL`, temperature 0, seed 42, all recorded in the results config. Unusable LLM output falls back to the nearest-prerequisite baseline and is reported as `llm_fallbacks`. A concept with no prerequisites is traced to itself without an LLM call (it counts in n for every method).
- **Metrics:** top-1 and top-3 accuracy over the wrong answers, against `expected_concept`.
- **No tuning on the test set:** the prompt is developed on `tests/fixtures/dev_set.json` only. The dev set and the test set share no item ids (checked by Shreeya, 2026-11-02).

## Done when
The CLI writes `root_cause.json` from real answers, RQ3 results for the LLM and both baselines are in `cdlp/root_cause/results/`, and `pytest cdlp/root_cause` passes.
