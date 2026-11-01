# Validation · owner: Shreeya (lead)

The validation agent (novelty 1).

**Question you answer:** *Can we trust this relationship?*

**You own (only you edit):** `cdlp/validation/`, `website/pages/3_Validation_Agent.py`, `data/gold/annotations/annotator_c.csv`.
As lead you also own `cdlp/shared/`, `pipeline.py`, root files, `docs/` and `.github/`. These change rarely; you review PRs.

| | File | Notes |
|---|---|---|
| Input | `relationships.json`, `concepts.json`, `chunks.jsonl` | Until Day 6 use `cdlp/shared/examples/` (it already includes a bad edge: graphs → avl_tree) |
| Output | `validated_graph.json` | Every edge kept with ACCEPT / REJECT / HUMAN_REVIEW, the four checks, necessity gap, reason |
| Output (planned) | `review_queue.json` | With `--review-queue <path>`: HUMAN_REVIEW edges ranked by impact (contract 1.1) |

Use a **different model** from discovery (`LLM_VALIDATOR_MODEL` in `.env`) so the two models' errors don't line up.

## Tasks, in order
- [ ] **Day 1:** push the repo, share the link, fill in `CODEOWNERS` usernames, label your share of gold edges
- [ ] Graph check (NetworkX): cycles, self-loops, duplicates, contradictions, redundant (transitive) edges
- [ ] Evidence check: retrieve chunks for A and B; does the text support A before B?
- [ ] Semantic check: does the edge make teaching sense?
- [ ] **Necessity test (simulated learner):** an LLM plays a student who doesn't know A and answers questions on B, then does it again knowing A. `necessity_gap` = score with A − score without A
- [ ] Leakage check: does the "student without A" still use A's terms? Report the rate
- [ ] Decision rule → ACCEPT / REJECT / HUMAN_REVIEW (tune thresholds on a small dev split, never on test)
- [ ] **Impact-ranked review queue (planned, not implemented):** `--review-queue <path>` writes `review_queue.json`. For each HUMAN_REVIEW edge, impact = number of simulated students (`sim_students.json`) whose personalized path changes if the edge flips (accepted vs not). Store it as `paths_affected`, derive `impact_score` from it, and sort highest first so reviewers see the edges that matter most
- [ ] **Day 7: hand off real `validated_graph.json`** to Shrestha and run `python pipeline.py` on real data
- [ ] RQ1 ablations: discovery only · single LLM judge · full agent · agent minus each check → P / R / F1, HUMAN_REVIEW rate → `cdlp/validation/results/`
- [ ] Website page 3: decisions, checks, evidence, necessity gap

## Notes for the paper
- **RQ1 on benchmarks reports the agent without the evidence check** (decided 2026-11-02). AL-CPL and the University Course dataset give concept pairs only, no course text, so the evidence check has nothing to retrieve. On those datasets the reported agent is `minus_evidence`; on ds101 and ml101 it is `full_agent`. Each config in `configs/rq1/` names it in `reported_agent`, and the results files copy it. `full_agent` is still scored on benchmarks but not reported. Suggested wording: *"The public benchmarks provide no course material, so on them we evaluate the agent without the evidence check."*
- **Scoring conventions** (`cdlp/validation/evaluate.py`): our gold is scored on direct edges, and an unlabelled predicted pair counts as a false positive. Benchmarks score only labelled pairs; AL-CPL uses the transitive closure of our predictions, and University Course uses it only if its gold positives imply each other (count recorded in each result). State the convention next to every number.

## Done when
The full agent and every ablation run from one config each, results are in `cdlp/validation/results/`, and `pytest cdlp/validation` passes.
