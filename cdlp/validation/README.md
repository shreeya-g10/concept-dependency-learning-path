# Validation · owner: Shreeya (lead)

The validation agent (novelty 1).

**Question you answer:** *Can we trust this relationship?*

**You own (only you edit):** `cdlp/validation/`, `website/pages/3_Validation_Agent.py`, `data/gold/annotations/annotator_c.csv`.
As lead you also own `cdlp/shared/`, `pipeline.py`, root files, `docs/` and `.github/`. These change rarely; you review PRs.

| | File | Notes |
|---|---|---|
| Input | `relationships.json`, `concepts.json`, `chunks.jsonl` | Until Day 6 use `cdlp/shared/examples/` (it already includes a bad edge: graphs → avl_tree) |
| Output | `validated_graph.json` | Every edge kept with ACCEPT / REJECT / HUMAN_REVIEW, the four checks, necessity gap, reason |

Use a **different model** from discovery (`LLM_VALIDATOR_MODEL` in `.env`) so the two models' errors don't line up.

## Tasks, in order
- [ ] **Day 1:** push the repo, share the link, fill in `CODEOWNERS` usernames, label your share of gold edges
- [ ] Graph check (NetworkX): cycles, self-loops, duplicates, contradictions, redundant (transitive) edges
- [ ] Evidence check: retrieve chunks for A and B; does the text support A before B?
- [ ] Semantic check: does the edge make teaching sense?
- [ ] **Necessity test (simulated learner):** an LLM plays a student who doesn't know A and answers questions on B, then does it again knowing A. `necessity_gap` = score with A − score without A
- [ ] Leakage check: does the "student without A" still use A's terms? Report the rate
- [ ] Decision rule → ACCEPT / REJECT / HUMAN_REVIEW (tune thresholds on a small dev split, never on test)
- [ ] **Day 7: hand off real `validated_graph.json`** to Shrestha and run `python pipeline.py` on real data
- [ ] RQ1 ablations: discovery only · single LLM judge · full agent · agent minus each check → P / R / F1, HUMAN_REVIEW rate → `cdlp/validation/results/`
- [ ] Website page 3: decisions, checks, evidence, necessity gap

## Done when
The full agent and every ablation run from one config each, results are in `cdlp/validation/results/`, and `pytest cdlp/validation` passes.
