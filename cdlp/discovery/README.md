# Discovery · maintainer: Shreeya (initial code: Sneha)

Dependency discovery. Quiz items and simulated students moved to `cdlp/learning_path/` (2026-11-02), so modules never import each other.

**Question you answer:** *How might these concepts depend on each other?*

**Files:** `cdlp/discovery/`, `website/pages/2_Proposed_Dependencies.py`.

| | File | Notes |
|---|---|---|
| Input | `concepts.json`, `chunks.jsonl` | Until Day 5 use `cdlp/shared/examples/` |
| Output | `relationships.json` | Every proposed A → B with strength (hard/soft), confidence, evidence chunks |

## Tasks, in order
- [ ] **Day 1:** label your share of gold edges in `data/gold/annotations/annotator_b.csv`
- [ ] Candidate filter: embeddings + co-occurrence in a chunk + course order + name-in-definition. Report candidate recall vs gold (target ≥ 95%)
- [ ] LLM discovery on candidates only (`prompts/discover_v1.txt`): direction, hard/soft, confidence, evidence chunk ids
- [ ] Baseline for the paper: a plain "list all prerequisites" prompt with no filter
- [ ] **Day 5:** switch input to Vaidehi's real files; **Day 6: hand off real `relationships.json`** to Shreeya
- [ ] Evaluation: edge precision / recall / F1 vs gold → `cdlp/discovery/results/`
- [ ] Website page 2: proposed edges, evidence quotes, filter stats

## Done when
The CLI writes `relationships.json` from the real `concepts.json`, metrics are in `cdlp/discovery/results/`, and `pytest cdlp/discovery` passes.
