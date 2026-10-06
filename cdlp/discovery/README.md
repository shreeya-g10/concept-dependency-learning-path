# Discovery · owner: Sneha

Dependency discovery, plus quiz items and simulated students.

**Question you answer:** *How might these concepts depend on each other?*

**You own (only you edit):** `cdlp/discovery/`, `website/pages/2_Proposed_Dependencies.py`, `data/gold/annotations/annotator_b.csv`

| | File | Notes |
|---|---|---|
| Input | `concepts.json`, `chunks.jsonl` | Until Day 5 use `cdlp/shared/examples/` |
| Output | `relationships.json` | Every proposed A → B with strength (hard/soft), confidence, evidence chunks |
| Output | `quiz_items.json` | 3–5 multiple-choice items per concept, each tied to a chunk |
| Output | `sim_students.json` | Synthetic students with a known TRUE mastery per concept |

## Tasks, in order
- [ ] **Day 1:** label your share of gold edges in `data/gold/annotations/annotator_b.csv`
- [ ] Candidate filter: embeddings + co-occurrence in a chunk + course order + name-in-definition. Report candidate recall vs gold (target ≥ 95%)
- [ ] LLM discovery on candidates only (`prompts/discover_v1.txt`): direction, hard/soft, confidence, evidence chunk ids
- [ ] Baseline for the paper: a plain "list all prerequisites" prompt with no filter
- [ ] **Day 5:** switch input to Vaidehi's real files; **Day 6: hand off real `relationships.json`** to Shreeya
- [ ] Quiz item generation per concept → `quiz_items.json`
- [ ] Simulated students: 500 students whose TRUE knowledge respects the graph (if you know BST, you know its hard prerequisites), plus slip/guess noise → `sim_students.json`. **Hand off by Day 7** to Shrestha
- [ ] Evaluation: edge precision / recall / F1 vs gold → `cdlp/discovery/results/`
- [ ] Website page 2: proposed edges, evidence quotes, filter stats

## Done when
The CLI writes all three files from the real `concepts.json`, metrics are in `cdlp/discovery/results/`, and `pytest cdlp/discovery` passes.
