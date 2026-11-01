# Contract changelog

Contracts in `cdlp/shared/schemas/` are the interface between modules. Every file carries a `schema_version` and a `course_id`.

## The rule: additive only

- A new version may **add** new contract files or new **optional** fields.
- It may never rename, remove or retype a field, or make an optional field required.
- So a file written at an older version stays valid. Bump `schema_version`, add an example to `cdlp/shared/examples/`, register the file name in `FILE_SCHEMAS` (`validate.py`), and get lead approval.

## 1.5

- `validated_graph.json`: every check (`evidence`, `semantic`, `necessity`, `graph`) may now be `skipped`, meaning the check was not run (an RQ1 ablation such as `--skip-evidence`, or a benchmark without course text). A skipped check never blocks ACCEPT and is left out of the decision score.
- New optional top-level `skipped_checks`: the list of checks the run skipped. Example: `examples/minus_evidence_validated_graph.json`.
- **Exception to the additive rule, approved by the lead (2026-11-02):** adding `skipped` widens four enums. Every older file stays valid, but a reader that maps check values (e.g. website page 3) must handle `skipped`.

## 1.4

- `review_queue.json` rows may carry a new optional `blocking` (boolean, absent = false): accepting the edge as it is would close a cycle with ACCEPT edges (or it is a self-loop). **Every review strategy handles blocking edges first**, before any impact-ranked edge; the file lists them first.
- For a blocking row only, `impact_score` and `paths_affected` may be `null`: the path with the edge accepted is undefined, so no number is made up. The schema enforces this (a null needs `blocking: true`).
- **Exception to the additive rule, approved by the lead (2026-11-02):** these two fields were widened from number to number-or-null. Every 1.1 file stays valid, but a reader must handle `null`. Known readers: `website/pages/3_Validation_Agent.py` (handles it).
- Not a contract change: `cdlp/shared/llm.py` counts, per process, the requests the provider answered (`llm_calls`) and the answers read from the cache (`cache_hits`), plus the models and prompt versions used. `write_stats(path)` writes `{"llm_calls", "cache_hits", "model", "prompt_versions"}` as JSON; `model` is a string when one model was used, a sorted list when several were, `null` when none. `get_stats()` returns the same dict and `reset_stats()` zeroes it.
  Use: a run calls `write_stats(<run_dir>/<setting>.stats.json)` at the end, which `cdlp/validation/evaluate.py` reads for LLM calls per edge.
  Nothing else in `llm.py` changed: same cache key, same requests, same return values. A failed request is not counted.
- `validated_graph.json` edges may carry four new optional fields from the necessity test (`cdlp/validation/necessity_test.py`): `score_control` (control learner: knows A, an unrelated concept C banned), `score_without` (A banned), `n_questions` and `question_format` (`open` or `mcq`). `necessity_gap` = `score_control` − `score_without`. The necessity test writes all four per edge. Example: edge `r1` in `examples/validated_graph.json`.
- The four `validated_graph.json` fields are purely additive (new and optional); no other field changed type.

## 1.3

- New `relationships_baseline.json` (example in `examples/`): the RQ1 baseline written by `python -m cdlp.discovery --baseline` (one LLM call with the full concept list, no candidate filter). It uses the `relationships` schema unchanged; `evidence` is always empty because the baseline sees no chunks. Registered in `FILE_SCHEMAS`.
- No existing schema changed; 1.0-1.2 files stay valid.

## 1.2

- `relationships.json` edges may carry three new optional fields: `bidirectional` (true when the LLM said DIRECT in both directions for two concepts at the same course position), `reverse_strength` and `reverse_confidence` (the LLM's answer for target -> source). Discovery keeps one edge for such a pair, never two opposite edges; the validator decides the direction or sends it to HUMAN_REVIEW.
- Discovery no longer writes `sim_students.json` or `quiz_items.json`; both will be built by `cdlp/learning_path`. Until then `pipeline.py` falls back to the files in `cdlp/shared/examples/`.
- Example: `examples/relationships.json` is at 1.2, and edge `r5` (`trees -> graphs`) shows the bidirectional fields.
- Not a contract change: `cdlp/shared/llm.py` takes a `seed` (default 42), sends it as `options.seed` to Ollama and `seed` to OpenAI-compatible endpoints, and stores it in the cache key and cache record. Because the key changed, responses cached before this version are not reused.
- No field renamed, removed or made required; 1.0 and 1.1 files stay valid.

## 1.1

- New `student_answers.json`: one row per quiz answer (`student_id`, `item_id`, `concept_id`, `answer`, `correct`). Input for root-cause tracing.
- New `root_cause.json`: one trace per wrong answer (`traced_concept`, ranked `candidates`, `confidence`, `explanation`).
- New `root_cause_testset.json` (added to 1.1 after its release; additive, so nothing breaks): the gold test set for root-cause tracing. Each row has the `student_answers.json` fields plus a required `expected_concept` (the gold root-cause slug) and an optional `note`. Example in `examples/`.
- New `review_queue.json`: one row per HUMAN_REVIEW edge, ranked by `impact_score`, with `paths_affected` and `reason`.
- `pipeline.py --course <id>` reads `data/raw/<course>/` and writes `outputs/<course>/`. No module CLI changed.
- No existing schema changed; 1.0 files stay valid.

## 1.0

- Initial contracts: `chunks.jsonl`, `concepts.json`, `relationships.json`, `validated_graph.json`, `quiz_items.json`, `sim_students.json`, `student_state.json`, `learning_path.json`.
