# Demo script (ds101, about 5 minutes)

What the demo shows: upload → concept graph → AI validation → adaptive quiz → personalized path, on the real ds101 textbook chapters. The validated graph is a **demo subset** of 28 proposed edges, chosen by a written rule (below), and every page says so in a yellow banner. It is not an evaluation. The subset deliberately includes edges that look wrong, so **never quote its accept or reject counts as the agent's performance**.

**The subset rule** (`cdlp/validation/configs/demo_subset_ds101.json`, `cdlp/validation/demo_rule.py`). Slots are filled in this order, and only from edges discovery proposed:

1. **chain:** neighbouring forward steps of `general_tree → binary_tree → binary_search_tree → avl_tree`.
2. **likely_wrong (up to 8):** runs backwards along the chain, skips a chain concept, or joins an unlikely family pair such as a stack or queue into a tree or heap. This is a guess made before validation, so the agent may still accept these edges.
3. **tree_family:** both concepts in the tree family.
4. **other:** everything else, highest confidence first.

A chain link discovery did not propose is reported as missing and is never added. The rule uses no gold labels and no validator output. The chosen edges and the rule are saved to `outputs/ds101/validated_graph.demo_subset.json`.

## Tonight: build ds101 and the backups

Run in a plain terminal (not inside Claude Code), from the repo root, on an up-to-date `main`, one step at a time. Close memory-heavy apps first: the laptop has 8 GB, and swapping makes every LLM call several times slower.

```bash
cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && git checkout main && git pull --ff-only
```

**1. Extraction, default flags (qwen).** 149 calls, about 25–60 min.

```bash
caffeinate -i .venv/bin/python -m cdlp.extraction --input data/raw/ds101 --out-dir outputs/ds101 --course-id ds101 2>&1 | tee outputs/ds101_extraction.log
```

**2a. Discovery smoke test (qwen, `discover_v3`).** 6 calls, about 1–2 min. These replies are cached, so the full run reuses them. It keeps the old edges as `relationships_v2.json` first.

```bash
cp -n outputs/ds101/relationships.json outputs/ds101/relationships_v2.json; printf 'source,target\nbinary_tree,binary_search_tree\nbinary_search_tree,avl_tree\nbinary_tree,general_tree\nstack,heap\nrecursion,binary_tree\navl_tree,queue\n' > outputs/ds101_smoke_pairs.csv; TRUNC_BEFORE=$(grep -c 'truncating input prompt' ~/.ollama/logs/server.log); .venv/bin/python -m cdlp.discovery --concepts outputs/ds101/demo_concepts.json --chunks outputs/ds101/chunks.jsonl --pairs outputs/ds101_smoke_pairs.csv --prompt-version discover_v3 --out-dir outputs/ds101_smoke 2>&1 | grep -E 'candidates:|answers:'; echo "new truncations: $(( $(grep -c 'truncating input prompt' ~/.ollama/logs/server.log) - TRUNC_BEFORE ))"; .venv/bin/python -c "import json; [print(e['source'], '->', e['target'], e['strength'], e['confidence']) for e in json.load(open('outputs/ds101_smoke/relationships.json'))['relationships']]"
```

Go on only if `new truncations: 0` and `off_topic` is 0 or 1. Check that the edges read sensibly. If not, stop here, because the full run would be wrong too.

**2b. Discovery, full run (qwen, `discover_v3`).** The same 233 candidate pairs as the `discover_v2` run, one call each, about 30–50 min (the v2 run measured 12 s per call, and v3's prompts are shorter). It must print `candidates: 233 of 435 pairs (one neutral question each) -> 233 LLM calls`. If it prints another number, press Ctrl-C.

```bash
caffeinate -i .venv/bin/python -m cdlp.discovery --concepts outputs/ds101/demo_concepts.json --chunks outputs/ds101/chunks.jsonl --prompt-version discover_v3 --out-dir outputs/ds101 2>&1 | tee outputs/ds101_discovery.log
```

**2c. Check the edges (no LLM, instant).**

```bash
.venv/bin/python -c "import json, collections as c; r=json.load(open('outputs/ds101/relationships.json'))['relationships']; e={(x['source'],x['target']) for x in r}; print(len(r),'edges'); print('into', c.Counter(x['target'] for x in r).most_common(5)); print('strength', c.Counter(x['strength'] for x in r)); print('confidence', c.Counter(x['confidence'] for x in r)); [print(a,'->',b, (a,b) in e) for a,b in [('binary_tree','binary_search_tree'),('binary_search_tree','avl_tree'),('general_tree','binary_tree'),('binary_tree','general_tree')]]"; grep 'answers:' outputs/ds101_discovery.log
```

Look for: `off_topic` near 0; `general_tree` and `heap` no longer dominating `into`; a mix of hard and soft; both `binary_tree -> binary_search_tree` and `binary_search_tree -> avl_tree` printing `True`. If either prints `False`, don't add it by hand: see the backup plan.

**3. Validation, demo subset (llama).** 28 edges × 2 calls (evidence, semantic) = 56 calls × about 48 s, so about 45–50 min. Necessity is skipped.

```bash
ollama stop qwen2.5:7b-instruct; TRUNC_BEFORE=$(grep -c 'truncating input prompt' ~/.ollama/logs/server.log); caffeinate -i .venv/bin/python -m cdlp.validation --relationships outputs/ds101/relationships.json --concepts outputs/ds101/demo_concepts.json --chunks outputs/ds101/chunks.jsonl --out outputs/ds101/validated_graph.json --skip-necessity --demo-subset 28 --demo-rule cdlp/validation/configs/demo_subset_ds101.json 2>&1 | tee outputs/ds101_validation.log; echo "new truncations: $(( $(grep -c 'truncating input prompt' ~/.ollama/logs/server.log) - TRUNC_BEFORE ))"
```

The first line shows how many edges each tier got, and a `WARNING` for any chain link that is missing. The last lines show the ACCEPT / REJECT / HUMAN_REVIEW counts. Look at them before going on: the demo needs at least one REJECT to open and an accepted path into `avl_tree`. A few new truncations are possible on the longest evidence prompts; note which edges look odd.

**4. Quiz for the graph's concepts (qwen).** About one call per concept, 5–10 min.

Step 4 first keeps only the concepts that appear in the demo graph, then generates quiz items for them:

```bash
ollama stop llama3.1:8b; .venv/bin/python -c "import json; g=json.load(open('outputs/ds101/validated_graph.json')); ids={x for e in g['edges'] for x in (e['source'], e['target'])}; c=json.load(open('outputs/ds101/concepts.json')); c['concepts']=[k for k in c['concepts'] if k['id'] in ids]; json.dump(c, open('outputs/ds101/demo_graph_concepts.json','w'), indent=2); print(len(c['concepts']), 'concepts in the demo graph')" && caffeinate -i .venv/bin/python -m cdlp.learning_path.quiz --concepts outputs/ds101/demo_graph_concepts.json --chunks outputs/ds101/chunks.jsonl --course-id ds101 --out outputs/ds101/quiz_items.json 2>&1 | tee outputs/ds101_quiz.log
```

Progress at any time (calls made in the last 3 hours, by step; prompt versions: `extract_v1`, `discover_v3`, `evidence_v1` + `semantic_v2`, `quiz_v1`):

```bash
cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && for v in extract_v1 discover_v3 evidence_v1 semantic_v2 quiz_v1; do echo "$v: $(find .cache/llm -name '*.json' -mmin -180 -exec grep -l "\"prompt_version\": \"$v\"" {} + 2>/dev/null | wc -l)"; done
```

### Check every page on outputs/ds101

1. Automated (no LLM; run only when no LLM step is running): renders every page on `outputs/ds101` and prints `ok` or `ERROR` per page.
   ```bash
   .venv/bin/python -c "import sys; sys.path.insert(0, 'website'); from pathlib import Path; from streamlit.testing.v1 import AppTest; [print(p.name, 'ERROR' if AppTest.from_file(str(p), default_timeout=120).run().exception else 'ok') for p in sorted(Path('website/pages').glob('*.py'))]"
   ```
2. By eye: `.venv/bin/streamlit run website/Home.py`, pick **Data Structures & Algorithms** on Home, then open each page:
   - **Home:** the demo notice in plain words (no "sample topics" notice), the 4 steps.
   - **2 See your topics:** says how many topics were found, most-used first, 10 at a time. Each card has a one-line meaning and **Where to read**; **Read this part** opens the source text. **Next: Quick check** is at the end of the list.
   - **3 Quick check:** says **Topics ready for the quick check: 8 of 259**, then lists those 8. Type `zzz` and press Enter: it says the topic is not ready yet. Clear the box, tap **AVL Tree**. There is one question per screen, **Question 1** with a bar and no total. A wrong answer shows a kind message and the right answer, with no score. Keep answering: the plan opens by itself at the end.
   - **4 My study plan:** starts with **Study this next: [topic]** and **Read: file, page**, then the numbered list with Done / Next / Later. Tap **Mark as done**: the next topic moves up.
   - **Topic map:** says **Topics ready on the map: 8 of 259**. Learn before → this topic → Learn next, as cards; tap a card to move to it. Tap **See full map**: the map draws. Open a link under **Where these links come from** to see its evidence.
   - **For teachers → AI suggestions:** suggested links with quotes.
   - **For teachers → AI checks and review:** Accepted / Rejected / Needs your review counts, **Topics students can use** (with the list of topics not ready yet), then the links that need review, then **All links**; "Trial: really needed" (necessity) shows ➖ (skipped); no "Trial check" table (it only appears for graphs that ran it).
3. **Start the website after the runs finish.** If a page looks out of date, stop the website (Ctrl+C) and start it again.

### Test upload with a tiny notes file (tonight, about 5–10 min)

> **Not tested yet: the upload has not been run with a real LLM since the page was redesigned.** The automated tests use fake job files and no model. Treat the steps below as the first real test: do not rely on the live upload in the demo until they have worked on this laptop.

1. Create `~/Desktop/demo_notes.md` with three short paragraphs, e.g. one each on *Stacks*, *Queues* and *Breadth-first search (uses a queue)*.
2. **1 Add your notes** → drop the file in the upload area → name it `Notes101`. The file saves by itself and appears under **Your files**. To take out a wrong file, tap **Remove** next to it.
3. Check the time estimate, then tap **Read my notes**. Progress shows in plain words ("Checking links…"); the stage names and log are on **For teachers → AI checks and review**. Website builds skip the report-only necessity test to stay quick; the time estimate is a rough range (only the validator speed, ≈48 s per call on this laptop, is measured).
4. When it finishes, tap **Next: See your topics**, then look at each page.

### Backups (after everything works)

```bash
mkdir -p ~/Desktop/demo_backup && cp -R outputs/ds101 outputs/notes101 ~/Desktop/demo_backup/ && cp ~/Desktop/demo_notes.md ~/Desktop/demo_backup/
```

Also take one screenshot of each page (⇧⌘4) into `~/Desktop/demo_backup/screens/`.

## Before you present (5 min)

1. Close other apps. `ollama stop qwen2.5:7b-instruct; ollama stop llama3.1:8b`.
2. `cd` to the repo and run `PYTHONHASHSEED=6 .venv/bin/streamlit run website/Home.py`. On Home, pick **Data Structures & Algorithms**. The seed keeps the question order the same as in the 3:30 slot below: without it, the order of topics that tie can change each time the website starts (the order always respects the links).
3. Open each page once, so nothing loads for the first time on stage.
4. Answers are saved to `outputs/ds101/student_answers.json`. After rehearsing and after the demo, move that file out of `outputs/ds101/`, so demo answers don't get mixed in with real student answers.

## The 5-minute demo

| Time | Click | Say |
|---|---|---|
| 0:00 | **Home** | The problem: "I don't understand AVL trees." One course graph, a different path per student. The yellow notice says this is a demo: only 28 of the 64 links were checked, picked by a written rule (shown on the teacher pages). |
| 0:40 | **2 See your topics** | Concepts extracted from the real ds101 textbook chapters, most-used first, each with where to read it. Search "binary search tree", then tap **Read this part**. |
| 1:20 | **1 Add your notes** | (Optional, live: only if the upload test above worked with the real LLM. It is untested until then.) Drop `demo_notes.md`, name it `Notes101 live`, tap **Read my notes**. It runs in the background; come back at 4:30. |
| 1:40 | **For teachers → AI suggestions** | The discovery model (qwen) proposes prerequisite edges only for candidate pairs, with an evidence quote for each. |
| 2:20 | **For teachers → AI checks and review** | A *different* model (llama) checks every edge: evidence in the material, teaching sense, graph consistency (cycles, redundant shortcuts) → Accepted / Rejected / Needs your review (technical terms in small text). Under **All links**, show Rejected and open one link and read its reason. Say that some edges were picked because they looked wrong, to show rejections, so these counts are not an accuracy figure. Necessity is ➖: an experimental check, skipped here. |
| 3:00 | **Topic map** (opens on **AVL Tree**). Tap **See full map**, then open a link under **Where these links come from**. | Students see accepted links only. The line says 8 of 259 topics are ready: the other topics are still in the list on See your topics, but this demo subset has no accepted link for them, and the teacher page names them. Before AVL Tree: Binary Search Tree, Binary Tree and Rotation. Then read the quote and page behind one link. |
| 3:30 | **3 Quick check:** tap **AVL Tree**. **Question 1 (Traversal):** tap "By starting at the root and visiting each node's left child, then its right child, and finally the node itself." **Question 2 (Binary Search Tree):** tap the first answer ("...left subtree are greater..."). Tap **Keep going**. On **Question 3**, tap **See my study plan**. On the plan, tap **Mark as done**. | The student picks what they want to learn, and the questions come from the topics leading up to it. No timer, no score: a wrong answer gets a kind message and the right answer. Read the "possible reason" line aloud; if it says "our best guess", say it did not come from the AI helper. The plan starts with **Study this next: Rotation**, with the file and page to read. Traversal is not on the list because this student answered it right; other answers give a different list. Say the questions are AI-written and not yet checked by a teacher, and that this is one short check, so the plan is an estimate. Do not say it is accurate or saves time: we have not measured that here. |
| 4:30 | **1 Add your notes** (if started) | Show the progress, or pick the finished course on Home. |
| 4:50 | **Home** | Recap: upload → graph → validation → adaptive quiz → personalized path. Every number shown comes from the files in `outputs/ds101/`. |

## Backup plan

| If this fails live | Do this |
|---|---|
| Before the demo: a chain link is missing, or nothing was rejected | Don't add or edit edges by hand. On stage, use a target whose path is in the graph, and say that discovery missed that link, which is why the pipeline is evaluated stage by stage. `outputs/ds101/validated_graph.demo_subset.json` lists what was chosen and what is missing. |
| A page shows an error or odd data | Stop the website (Ctrl+C), start it again, reload. Still broken: `rm -rf outputs/ds101 && cp -R ~/Desktop/demo_backup/ds101 outputs/ds101`, then reload. |
| The live upload is slow or fails | Don't wait: on Home, pick **Notes101** (built and backed up tonight, if the upload test worked). If that is missing too: `cp -R ~/Desktop/demo_backup/notes101 outputs/notes101`. |
| Ollama is down or slow | Skip the live upload. **1 Add your notes** says the AI helper is off and offers **Try the sample course**. See your topics, Topic map and the teacher pages read saved files and need no model. In the Quick check, a wrong answer asks the AI helper for a reason, so with a slow model it can wait on "Looking at your answer...". With Ollama off it answers at once and labels the reason "our best guess, the AI helper was off". |
| Question 1 is not about Traversal | The website was started without the seed. Any order is fine: answer one question right and one wrong, then tap **See my study plan**. The topic names on the plan may differ from the talking points. |
| The website will not start | Show the screenshots in `~/Desktop/demo_backup/screens/`, in page order. |
| `outputs/ds101` is gone and there is no backup | The pages fall back to the shared example data and show a blue notice, "These are sample topics". Say clearly that it is example data. |
