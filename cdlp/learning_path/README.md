# Learning path · owner: Shrestha

Graph, adaptive diagnosis and personalized path (novelty 2).

**Question you answer:** *What should THIS student learn next?*

**You own (only you edit):** `cdlp/learning_path/` (including `api.py`), `website/pages/4_Knowledge_Graph.py`, `website/pages/5_My_Learning_Path.py`, `data/gold/annotations/annotator_d.csv`

| | File | Notes |
|---|---|---|
| Input | `validated_graph.json`, `quiz_items.json`, `sim_students.json` | Until Day 7 use `cdlp/shared/examples/` |
| Output | `student_state.json` | Estimated mastery per concept + questions asked |
| Output | `learning_path.json` | Ordered steps with "why" and evidence page |
| Public API | `api.py` | `next_question`, `update_mastery`, `personalized_path`. The website calls these; keep the signatures stable |

Use **ACCEPT edges only**. Ignore REJECT; HUMAN_REVIEW is excluded by default (make it a flag).

## Tasks, in order
- [ ] **Day 1:** label your share of gold edges in `data/gold/annotations/annotator_d.csv`
- [ ] Graph model (NetworkX): build from ACCEPT edges, transitive reduction, queries (ancestors, descendants, depth)
- [ ] Generic path: all ancestors of the target in topological order (baseline)
- [ ] Knowledge state: mastery probability per concept, prior from self-report
- [ ] **Adaptive diagnosis:** a correct answer on B raises B and its ancestors; a wrong one lowers B and makes its prerequisites uncertain; the next question has the highest information gain; stop when confident or out of budget
- [ ] Personalized path: ancestors − mastered concepts, soft prerequisites only when needed, topological order
- [ ] Implement the three functions in `api.py` (the CLI and the website both use them)
- [ ] RQ2 evaluation on simulated students: diagnosis accuracy vs number of questions, against "ask every concept" and "random order" → `cdlp/learning_path/results/`
- [ ] Website pages 4 and 5: interactive pyvis graph; live quiz followed by the personal path

## Done when
The CLI produces both files for all simulated students, the accuracy-vs-questions curve is in `cdlp/learning_path/results/`, page 5 runs a live quiz, and `pytest cdlp/learning_path` passes.
