# Contract changelog

Contracts in `cdlp/shared/schemas/` are the interface between modules. Every file carries a `schema_version` and a `course_id`.

## The rule: additive only

- A new version may **add** new contract files or new **optional** fields.
- It may never rename, remove or retype a field, or make an optional field required.
- So a file written at an older version stays valid. Bump `schema_version`, add an example to `cdlp/shared/examples/`, register the file name in `FILE_SCHEMAS` (`validate.py`), and get lead approval.

## 1.1

- New `student_answers.json`: one row per quiz answer (`student_id`, `item_id`, `concept_id`, `answer`, `correct`). Input for root-cause tracing.
- New `root_cause.json`: one trace per wrong answer (`traced_concept`, ranked `candidates`, `confidence`, `explanation`).
- New `review_queue.json`: one row per HUMAN_REVIEW edge, ranked by `impact_score`, with `paths_affected` and `reason`.
- `pipeline.py --course <id>` reads `data/raw/<course>/` and writes `outputs/<course>/`. No module CLI changed.
- No existing schema changed; 1.0 files stay valid.

## 1.0

- Initial contracts: `chunks.jsonl`, `concepts.json`, `relationships.json`, `validated_graph.json`, `quiz_items.json`, `sim_students.json`, `student_state.json`, `learning_path.json`.
