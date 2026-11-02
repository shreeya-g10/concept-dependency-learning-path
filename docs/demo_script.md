# Demo script (ds101, about 5 minutes)

What the demo shows: upload → concept graph → AI validation → adaptive quiz → personalized path, on the real ds101 textbook chapters. The validated graph is a **demo subset** (the 28 highest-confidence proposed edges), and every page says so in a yellow banner. It is not an evaluation.

## Tonight: build ds101 and the backups

Run in a plain terminal (not inside Claude Code), from the repo root, on an up-to-date `main`, one step at a time. Close memory-heavy apps first: the laptop has 8 GB, and swapping makes every LLM call several times slower.

```bash
cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && git checkout main && git pull --ff-only
```

**1. Extraction, default flags (qwen).** 149 calls, about 25–60 min.

```bash
caffeinate -i .venv/bin/python -m cdlp.extraction --input data/raw/ds101 --out-dir outputs/ds101 --course-id ds101 2>&1 | tee outputs/ds101_extraction.log
```

**2. Discovery (qwen).** It first prints `-> N LLM calls`; expect about N × 5 s.

```bash
caffeinate -i .venv/bin/python -m cdlp.discovery --concepts outputs/ds101/concepts.json --chunks outputs/ds101/chunks.jsonl --out-dir outputs/ds101 2>&1 | tee outputs/ds101_discovery.log
```

**3. Validation, demo subset (llama).** 28 edges × 2 calls (evidence, semantic) = 56 calls × about 48 s, so about 45–50 min. Necessity is skipped.

```bash
ollama stop qwen2.5:7b-instruct; caffeinate -i .venv/bin/python -m cdlp.validation --relationships outputs/ds101/relationships.json --concepts outputs/ds101/concepts.json --chunks outputs/ds101/chunks.jsonl --out outputs/ds101/validated_graph.json --skip-necessity --demo-subset 28 2>&1 | tee outputs/ds101_validation.log
```

**4. Quiz for the graph's concepts (qwen).** About one call per concept, 5–10 min.

Step 4 first keeps only the concepts that appear in the demo graph, then generates quiz items for them:

```bash
ollama stop llama3.1:8b; .venv/bin/python -c "import json; g=json.load(open('outputs/ds101/validated_graph.json')); ids={x for e in g['edges'] for x in (e['source'], e['target'])}; c=json.load(open('outputs/ds101/concepts.json')); c['concepts']=[k for k in c['concepts'] if k['id'] in ids]; json.dump(c, open('outputs/ds101/demo_graph_concepts.json','w'), indent=2); print(len(c['concepts']), 'concepts in the demo graph')" && caffeinate -i .venv/bin/python -m cdlp.learning_path.quiz --concepts outputs/ds101/demo_graph_concepts.json --chunks outputs/ds101/chunks.jsonl --course-id ds101 --out outputs/ds101/quiz_items.json 2>&1 | tee outputs/ds101_quiz.log
```

Progress at any time (calls made in the last 3 hours, by step; prompt versions: `extract_v1`, `discover_v2`, `evidence_v1` + `semantic_v2`, `quiz_v1`):

```bash
cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && for v in extract_v1 discover_v2 evidence_v1 semantic_v2 quiz_v1; do echo "$v: $(find .cache/llm -name '*.json' -mmin -180 -exec grep -l "\"prompt_version\": \"$v\"" {} + 2>/dev/null | wc -l)"; done
```

### Check all five pages on outputs/ds101

1. Automated (no LLM; run only when no LLM step is running): renders every page on `outputs/ds101` and prints `ok` or `ERROR` per page.
   ```bash
   .venv/bin/python -c "import sys; sys.path.insert(0, 'website'); from pathlib import Path; from streamlit.testing.v1 import AppTest; [print(p.name, 'ERROR' if AppTest.from_file(str(p), default_timeout=120).run().exception else 'ok') for p in [Path('website/Home.py'), *sorted(Path('website/pages').glob('*.py'))]]"
   ```
2. By eye: `.venv/bin/streamlit run website/Home.py`, choose **Active Course → ds101** in the sidebar, then open each page:
   - **Home:** green "Live Pipeline" badge, the yellow demo-subset banner, concept and edge counts.
   - **1 Course Material:** the 🔎 Concepts tab lists concepts with their source file and page.
   - **2 Proposed Dependencies:** proposed edges with evidence quotes.
   - **3 Validation Agent:** ACCEPT / REJECT / HUMAN_REVIEW counts; necessity shows ➖ (skipped); no "Necessity test" table (it only appears for graphs that ran it).
   - **4 Knowledge Graph:** the interactive graph draws, and an edge expands to its evidence.
   - **5 My Learning Path:** a quiz question appears; after a few answers the path lists steps with 📄 file and page.
3. **Start the website after the runs finish** (or use ☰ → **Clear cache**): pages cache the files they read.

### Test upload with a tiny notes file (tonight, about 5–10 min)

1. Create `~/Desktop/demo_notes.md` with three short paragraphs, e.g. one each on *Stacks*, *Queues* and *Breadth-first search (uses a queue)*.
2. Page 1 → **📤 Upload & build a course** → **Course ID** `notes101` → drop the file → **💾 Save files** → **🚀 Build course graph**.
3. The status shows each stage. Website builds skip the report-only necessity test to stay quick; the time estimate on the page is a rough range (only the validator speed, ≈48 s per call on this laptop, is measured).
4. When it finishes, sidebar **Active Course → notes101** and look at pages 1–5.

### Backups (after everything works)

```bash
mkdir -p ~/Desktop/demo_backup && cp -R outputs/ds101 outputs/notes101 ~/Desktop/demo_backup/ && cp ~/Desktop/demo_notes.md ~/Desktop/demo_backup/
```

Also take one screenshot of each page (⇧⌘4) into `~/Desktop/demo_backup/screens/`.

## Before you present (5 min)

1. Close other apps. `ollama stop qwen2.5:7b-instruct; ollama stop llama3.1:8b`.
2. `cd` to the repo and run `.venv/bin/streamlit run website/Home.py`. Sidebar → **Active Course → ds101**.
3. Open each page once, so nothing loads for the first time on stage.

## The 5-minute demo

| Time | Click | Say |
|---|---|---|
| 0:00 | **Home** | The problem: "I don't understand AVL trees." One course graph, a different path per student. Point at the pipeline and the counts; the yellow banner says this is a 28-edge demo subset. |
| 0:40 | **1 Course Material → 🔎 Concepts** | Concepts extracted from the real ds101 textbook chapters, each with its source file and page. Search "binary search tree". |
| 1:20 | **1 → 📤 Upload & build a course** | (Optional, live) Course ID `notes101_live`, drop `demo_notes.md`, **Save files**, **Build course graph**. It runs in the background; come back at 4:30. |
| 1:40 | **2 Proposed Dependencies** | The discovery model (qwen) proposes prerequisite edges only for candidate pairs, with an evidence quote for each. |
| 2:20 | **3 Validation Agent** | A *different* model (llama) checks every edge: evidence in the material, teaching sense, graph consistency (cycles, redundant shortcuts) → ACCEPT / REJECT / HUMAN_REVIEW. Open one REJECT and read its reason. Necessity is ➖: an experimental check, skipped here. |
| 3:00 | **4 Knowledge Graph** | Only accepted edges; click an edge for its evidence. |
| 3:30 | **5 My Learning Path** | Answer one question right and one wrong. A wrong answer is traced to a likely missing prerequisite. The path lists the steps in order, each with 📄 file and page. |
| 4:30 | **1 → Upload** (if started) | Show the build status, or the finished `notes101` course in the sidebar. |
| 4:50 | **Home** | Recap: upload → graph → validation → adaptive quiz → personalized path. Every number shown comes from the files in `outputs/ds101/`. |

## Backup plan

| If this fails live | Do this |
|---|---|
| A page shows an error or odd data | ☰ → **Clear cache**, reload. Still broken: `rm -rf outputs/ds101 && cp -R ~/Desktop/demo_backup/ds101 outputs/ds101`, then reload. |
| The live upload is slow or fails | Don't wait: switch the sidebar to `notes101` (built and backed up tonight). If that is missing too: `cp -R ~/Desktop/demo_backup/notes101 outputs/notes101`. |
| Ollama is down or slow | Pages 1–4 read saved files and need no model. On page 5 a wrong answer still works: the trace is labelled **offline estimate**. Skip the live upload. |
| The website will not start | Show the screenshots in `~/Desktop/demo_backup/screens/`, in page order. |
| `outputs/ds101` is gone and there is no backup | Select a course with no outputs: the pages fall back to the shared example data and show a 🟡 **Example Mock Data** badge. Say clearly that it is example data. |
