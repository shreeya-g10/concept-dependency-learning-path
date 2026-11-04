# Contract changelog

Contracts in `cdlp/shared/schemas/` are the interface between modules. Every file carries a `schema_version` and a `course_id`.

## The rule: additive only

- A new version may **add** new contract files or new **optional** fields.
- It may never rename, remove or retype a field, or make an optional field required.
- So a file written at an older version stays valid. Bump `schema_version`, add an example to `cdlp/shared/examples/`, register the file name in `FILE_SCHEMAS` (`validate.py`), and get lead approval.

## 1.13

- `quiz_items.json` items may carry an optional `difficulty` (`easy`, `medium`, `hard`) and `difficulty_source` (`ai_suggestion`, `teacher`). An AI label is only a suggestion until a teacher approves it. An item with no `difficulty` is treated as easy or any level, and a course with no labelled item keeps the old question selection.
- `generation` may carry optional `drop_rate_by_level` and `concepts_missing_level`, written by prompt `quiz_v3`, which is now the default. Quiz generation writes `schema_version` 1.13. Example: `examples/ladder_quiz_items.json` (mock, hand-written questions and made-up counts).
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.12

- New contract file `preview.json`: a Quick Preview made by the website without AI. It lists headings as possible topics and joins them in heading order. It has no decision, confidence, check grade or necessity gap, and `additionalProperties: false` stops them being added. It lives in `outputs/_previews/<course>/`, is never a validated course, and must not be used for any result. Example: `examples/preview.json`.
- `quiz_items.json` items may carry an optional `origin` (`general_practice`): a fixed question written by hand, not from the course's notes or the AI check. Example: `examples/preview_quiz_items.json`.
- `concepts.json` may carry an optional `chunks_truncated` (`kept`, `total`, `limit_from`), written when `CDLP_MAX_CHUNKS` cut the run short. `preview.json` may carry the same field. A cut run writes `schema_version` 1.12; other extraction runs stay at 1.7. Example: `examples/truncated_concepts.json`.
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.11

- `relationships.json` may carry an optional top-level `pair_answers` (both raw answers per asked pair, `asks[0]` being the hash order) and an optional `discovery.both_orders` (counts per pair and the rule version), and edges may carry an optional `order_agreement` (`stable`, `unstable` or `reversed`). Written by course runs, which now ask every candidate pair in both orders under `cdlp/discovery/configs/order_rule_v1.json`. In such a file `discovery.answers` counts the hash-order asks only. `--pairs` benchmark runs and `--one-order` do not write them. Both edges of a reversed pair go to the validator, whose contradiction label sends both to HUMAN_REVIEW.
- `quiz_items.json` items may carry an optional `second_model` (the reply, for the record), and `generation` may carry optional `check_version` and `dropped` (every dropped draft with its reason). Quiz generation now defaults to `quiz_check_v3` (no-LLM subject and answer-support checks, a formatting-tolerant quote match, then the unchanged `quiz_check_v2` prompt as a veto).
- Discovery and quiz generation write `schema_version` 1.11.
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.10

- `relationships.json` may carry an optional top-level `discovery` (`prompt_version`, `pair_order_rule`, `answers`), and edges may carry an optional `pair_order` (`a`, `b`, `rule`, `answer`). Written by the neutral prompts, now `discover_v3_1` by default for course runs, so a position bias can be measured. `--pairs` benchmark runs keep `discover_v2` and do not write them. Discovery now writes `schema_version` 1.10 (`relationships_baseline.json` stays at 1.3). Example: `examples/neutral_relationships.json`.
- `quiz_items.json` `generation` may carry optional `min_items_per_topic`, `retry_prompt_version`, `topics_retried` and `skipped_on_retry`; `skipped` now counts retries too. The check prompt is now `quiz_check_v2`. Quiz generation writes `schema_version` 1.10. Example: `examples/checked_quiz_items.json`.
- Not a contract change: `python -m cdlp.extraction.concept_filter` writes an ordinary `concepts.json` with kept concepts unchanged, and its `concept_filter_report.json` is not a contract file.
- Versions are labels, not decimals: 1.10 comes after 1.9.
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.9

- `quiz_items.json` items may carry an optional `source_quote` (word-for-word from `chunk_id`), and `generation` may carry `check_model`, `check_prompt_version` and `items_checked`. Written by prompt `quiz_v2` with the second-model check `quiz_check_v1`.
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.8

- `validated_graph.json` may carry an optional top-level `subset` (`kind`, `n`, `of`, `selection`), written when only part of the proposed edges was validated (`python -m cdlp.validation --demo-subset N`: the N highest-confidence edges). Such a graph is a demo, not an evaluation; the website shows a banner for it. Example: `examples/demo_subset_validated_graph.json`.
- No field renamed, removed, retyped or made required; older files stay valid.

## 1.7

- `concepts.json` may carry four new optional top-level fields written by `cdlp.extraction`:
  - `extraction_method`: `llm`, `rule_based` (the built-in keyword catalog for every chunk, only with `--allow-rule-based`) or `mixed`.
  - `extraction_fallback_chunks`: ids of the chunks whose concepts came from the catalog because the LLM failed for them.
  - `dedup_method`: `embedding` (sentence embeddings, the default), `tfidf` or `jaccard` (fallbacks, used only with `--allow-tfidf`), or `mixed` (more than one in a run).
  - `dedup_comparisons`: fuzzy name comparisons per method, plus `embedding_failed`.
  Extraction writes `schema_version` 1.7. Example: `examples/concepts.json`.
- Not a contract change: without the embedding model, extraction now fails (exit 2) unless `--allow-tfidf` is given. Before, it silently compared names with TF-IDF. Without a reachable LLM, or when more than 20% of chunks fell back to the catalog, it fails (exit 2) unless `--allow-rule-based` is given. With course files present, a parse or extraction error exits 1 instead of writing the example files. `pipeline.py` passes both flags on.
- Purely additive: four new optional fields. Older files stay valid.

## 1.6

- New `review_decisions.json` (example in `examples/`): a teacher's ACCEPT / REJECT on HUMAN_REVIEW edges, one row per edge (`edge_id`, `source`, `target`, `decision`, `decided_by`, `decided_at`, optional `comment`). Written from website page 3 through `python -m cdlp.validation.apply_review --decide <edge_id> <ACCEPT|REJECT>`. Registered in `FILE_SCHEMAS`.
- `validated_graph.json` edges may carry a new optional `review` object: `decided_by` (`teacher`), `decision`, `validator_decision` (always `HUMAN_REVIEW`), `status` (`applied` or `refused_cycle`), and optional `comment`, `decided_at`, `cycle`. With `applied`, the edge's `decision` is the teacher's. With `refused_cycle`, the teacher's ACCEPT would have closed a cycle, so the edge stays `HUMAN_REVIEW` and the graph stays a DAG. The validator's `confidence`, `checks`, `evidence` and `reason` are never changed. Example: `examples/reviewed_validated_graph.json` (edge `r5` accepted by a teacher).
- `cdlp/validation/apply_review.py` writes `validated_graph.json` at `schema_version` 1.6. It first undoes earlier teacher decisions (restores `validator_decision`), then applies all of them, so re-running it changes nothing. `pipeline.py` re-applies `outputs/<course>/review_decisions.json` right after validation, when that file exists.
- (Also 1.6, from the quiz-generation PR #51.) `quiz_items.json` may carry a new optional top-level `generation` object: `model`, `prompt_version`, `temperature`, `seed`, `max_chunks_per_concept`, `concepts`, `concepts_without_chunks`, `concepts_without_items` and `skipped` (count of dropped items per reason). Written by `python -m cdlp.learning_path.quiz`, which generates the items from any course's `chunks.jsonl` (`cdlp/learning_path/prompts/quiz_v1.txt`). `examples/quiz_items.json` is hand-written, so it stays at 1.0 without the block.
- `pipeline.py` no longer falls back to the ds101 example quiz: it generates `quiz_items.json` per course.
- Purely additive: a new file and two new optional fields (`review` on `validated_graph.json` edges, `generation` on `quiz_items.json`). 1.0–1.5 files stay valid.

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
