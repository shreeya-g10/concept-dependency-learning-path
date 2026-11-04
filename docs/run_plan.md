# Run plan: every prompt, in order

Written 2026-11-04. Run one prompt at a time. Merge each PR with **Create a merge commit**, then start the next prompt. No prompt runs an AI model on the laptop: real runs happen in Colab.

All times are estimates. Claude times come from similar earlier prompts. Colab times are not measured: C1 measures them.

| Step | What | Where | Estimated time |
|---|---|---|---|
| P1 | Commit the paper and scripts | Claude | 5 min |
| P2 | Remove Fast Demo Mode's made-up results | Claude | 15–25 min |
| P3 | Finish the old-site features (T6) | Claude | 20–30 min |
| P4 | Quiz check v4, upload time estimate | Claude | 15–20 min |
| P5 | Teacher approval of questions | Claude | 25–40 min |
| P6 | Colab notebook for full builds | Claude | 25–35 min |
| C1 | Speed test | Colab | 10 min |
| C2 | AVL deck build | Colab | 15–45 min |
| C3 | ds101 discovery, both orders | Colab | 1–2.5 h |
| P7 | Review discovery counts | Claude | 5–10 min |
| C4 | ds101 validation and quiz | Colab | 0.5–2.5 h |
| P8 | Review links and questions | Claude and you | 30–60 min |
| C5 | ml101 full build | Colab | 1–2 h |
| C6 | Benchmarks | Colab | 1–2 h |
| P9 | Score RQ1, RQ3, RQ2 and RQ4 | Claude and Colab | 30–60 min |
| P10 | Final paper (T5) | Claude | 20–30 min |

Shortest route to a working demo: P2, P6, C1, C2.

## P1: commit the paper and scripts

```text
Run git status in the main folder. Create branch docs/paper-and-demo from origin/main. Commit only docs/paper/ieee/, docs/demo_material/, docs/run_plan.md and scripts/run_cpu_embed.py. Don't commit anything else. Run ruff on the changed Python files and the full test suite with LLM_BASE_URL=http://127.0.0.1:9 under set -o pipefail. Before the tests, check ollama ps: if a model is loaded, stop and ask me. Push, open the PR into main and report CI. No real LLM runs.
```

## P2: remove Fast Demo Mode's made-up results

```text
Work from the latest origin/main in a new worktree ../cdlp-t7 on branch website/honest-quick-preview, and copy CLAUDE.local.md and .env into it. No real LLM runs. Open the PR into main.

PR #77's Fast Demo Mode writes invented results: hard-coded ACCEPT, confidence 0.95, all checks "strong", necessity_gap 0.70, links made by chaining headings, and a fake stage log and "all contract files valid". Fix it as follows:

1. Remove the invented validated_graph, relationships, learning_path, student_state and quiz output, and the fake progress and contract-check lines. Remove the fallback that copies files from outputs/ into a new course.
2. Replace it with an honest Quick Preview, off by default: it reads the files and lists headings as "possible topics" with their page, and writes no contract files. It must say plainly: "Preview only. No AI was used. To get links, checks and a quiz, tap Read my notes." It must not appear as a finished course in the subject list.
3. Make the real pipeline the only way to build a course, and make the normal button start it with the real arguments. Remove the demo_subset default of 2, the TypeError fallbacks and the dead if False branch in ui.py.
4. CDLP_MAX_CHUNKS in parse.py: if a run truncates chunks, log it clearly and record it in the outputs, or remove the option. Tell me which you chose.
5. Fix the Start page wording so it doesn't promise "Fast Demo Mode".
6. Keep the Windows fixes, UTF-8 reading, sys.path fix, sample subject card, breadcrumbs and Continue button. Show teacher pages in the menu by default, and keep the toggle only if there's a clear reason.
7. Add tests: Quick Preview writes no contract files; nothing in website/ writes a decision or check result except through the real pipeline; a preview doesn't create a course. Also search the repo for any other hard-coded decision, confidence or check value outside tests and shared examples, and report what you find.

Check ollama ps first, and if a model is loaded, stop and ask me. Run ruff and the full test suite with the LLM unreachable. Report CI and list what you removed, then stop.
```

## P3: finish the old-site features (T6)

```text
Your uncommitted work is in ../cdlp-t6 on branch website/bring-back-features. Don't redo finished work. Merge the latest origin/main into the branch (never force-push), resolve conflicts, and keep P2's removal of Fast Demo Mode. Open the PR into main.

The 8 items are:
1. Study plan: result summary, worded gently.
2. "What we think you know": Know it, Not sure, Needs work, with no percentages, marking which topics were answered and which inferred.
3. "Review your answers", with the root-cause note and its existing label.
4. A Start over button with a confirmation.
5. Show the full map by default at 30 links or fewer, and keep the button above that, without loading the drawing library until asked.
6. "See everything before this topic".
7. Strength and a short plain reason on each link, with no raw validator text for students.
8. A teacher About page with the steps, what's new and live counts, showing no result numbers that aren't read from a results file.

You deleted test_topic_map_sends_the_heavy_picture_only_on_request. Add a test that a map over 30 links sends no iframe until the button is pressed, and tests for exactly 30 and 31 links. List every test you removed or weakened, with the reason.

Check the pages in the browser at phone and laptop width, using a port other than 8501 and 8502. Check ollama ps first, and if a model is loaded, stop and ask me. Run ruff and the full test suite with the LLM unreachable. Report CI, then stop. No real LLM runs.
```

## P4: quiz check v4 and upload time estimate

```text
Work from the latest origin/main in worktree ../cdlp-t4 on a new branch learning_path/quiz-check-v4. No real LLM runs. Open the PR into main.

1. Create quiz_check_v4 and keep v3 for the record. The subject check uses only canonical concept names and all-caps acronym aliases, with no hand-written list of generic aliases. Record in the report that this fix was prompted by the replay drafts. Make no other check or threshold changes.
2. Fix replay_quiz_check.py so --limit 0 makes no calls.
3. Update the website's upload time estimate for both-order discovery and the current validator speeds.
4. Replay on cached drafts only. Say how many drafts couldn't be replayed without a new call. Give no accuracy figure.

Check ollama ps first, and if a model is loaded, stop and ask me. Run ruff and the full test suite with the LLM unreachable. Report CI, then stop.
```

## P5: teacher approval of questions

```text
Work from the latest origin/main in a new worktree ../cdlp-t5 on branch website/quiz-approval. No real LLM runs. Open the PR into main.

1. Add an optional approved field to the quiz contract (additive, with a schema_version bump and a CHANGELOG entry).
2. Add a teacher screen on the AI checks page to approve, reject or edit a question. An edit keeps the original text and records that it was edited. A rejected question is never deleted.
3. Students see approved questions first. An uploaded course with no teacher review still works, but says clearly that its questions are AI-written and not yet checked.
4. Check it in the browser at phone width, using a port other than 8501 and 8502.

Check ollama ps first, and if a model is loaded, stop and ask me. Run ruff and the full test suite with the LLM unreachable. Report CI, then stop.
```

## P6: Colab notebook for full builds

```text
Work from the latest origin/main in a new worktree ../cdlp-t8 on branch validation/colab-full-build, and copy CLAUDE.local.md and .env into it. No real LLM runs on this laptop. Open the PR into main.

Extend notebooks/colab_validator.ipynb and scripts/colab_run.py so everything can run inside Colab, with no tunnel:
- stage speed: 10 short and 5 long calls for each model, printing seconds per call
- stage course --course <id> --steps extract,discover,validate,quiz,path: can run a chosen subset, so discovery can stop for review before validation
- stage night1: the benchmark discovery that scripts/rq1_night1.sh runs, alongside the existing night2 and night3

Requirements:
1. Stop if no GPU is found, and record the GPU and each model's digest. Use exactly qwen2.5:7b-instruct and llama3.1:8b, one loaded at a time unless both fit.
2. Keep outputs and the LLM cache in Drive, so a disconnect resumes without repeating finished calls. The existing cache and 85-concept ds101 files in ../cdlp-t4/outputs/ds101/ must be usable, with a documented upload step.
3. Course runs use both-order discovery under order_rule_v1. ds101 and ml101 use --necessity-sample 40. A demo course skips necessity.
4. Print measured seconds per call, per call type, and total time per stage.
5. Zip only the course's outputs, and tell me exactly where to put them so the website lists the course.
6. Update the pinned commit, and update docs/colab_steps.md with step-by-step clicks.
7. Check the website opens a downloaded course with Ollama fully stopped, including the wrong-answer fallback label. Report page load times.

Don't add a tunnel, a fake result or a demo shortcut. Check ollama ps first, and if a model is loaded, stop and ask me. Run ruff and the full test suite with the LLM unreachable. Report CI, then stop.
```

## C1 to C6: Colab runs, using docs/colab_steps.md

Choose **Runtime > Change runtime type > T4 GPU**, and keep the tab open. Free sessions last at most 12 hours and GPU access isn't guaranteed. If you're cut off, rerun the same stage: finished calls are saved.

- C1: stage `speed`. Paste the numbers into Claude, to replace the estimates above.
- C2: stage `course` for your AVL deck. It's demo material, so never use it in a result.
- C3: stage `course --course ds101 --steps discover`. Then do P7.
- C4: stage `course --course ds101 --steps validate,quiz,path`. Then do P8.
- C5: stage `course --course ml101` with all steps.
- C6: stages `night1`, `night2`, `night3`, then `real`.

## P7: review discovery counts

```text
Colab discovery for ds101 is finished, and I've put the downloaded outputs in <path>. Make no LLM calls. Report:
- the stable, unstable and reversed counts, and how many were proposed in hash order alone
- the A/B split, and the proposal rate compared with the 40% estimate
- graph labels computed twice: with reversed edges counted in the cycle check, and without them
- how many edges could still be auto-accepted, and how many would go to review, under each
- whether the chain from general_tree to binary_tree, binary_search_tree and avl_tree has a candidate at each step, and each one's agreement label
- a validator recount with and without calls on reversed edges, using measured Colab speeds
- confirmation that any change you'd suggest doesn't affect --pairs benchmark runs

Don't change order_rule_v1. If you recommend a change, write it up as a proposed order_rule_v2 with its reason, and make it clear the choice was made after seeing discovery counts. Then wait for my decision.
```

## P8: review links and questions

```text
Colab validation and quiz generation for ds101 are finished, and the outputs are in <path>. Make no LLM calls. Show the accepted, rejected and review links, the chain that starts nearest to Trees and leads to AVL Tree, every gap in that chain, and all quiz questions with their quotes. Don't add links by hand. Don't update the live course files until I approve. Keep results from before and after teacher review separate. Check the Ollama log, or the Colab output, for evidence prompts that overflowed.
```

## P9: score the research questions

```text
Colab runs for ds101, ml101 and the benchmarks are finished, and the outputs are in <path>. Using only those files:
1. Run python -m cdlp.validation.evaluate for RQ1 on each dataset. Compare single-order and both-order discovery on courses.
2. Calibrate thresholds only on the development split, then freeze them before scoring.
3. Tell me how many LLM calls RQ3 needs. It runs once on data/gold/root_cause_testset.json with the frozen tracer, in Colab.
4. Rerun RQ2 and RQ4 on the real graphs, which needs no LLM.
5. Run scripts/make_results.py.

Report each number with its source file, and any table cell still empty. Never tune on test data. Open the PR into main, report CI, then stop.
```

## P10: final paper (T5)

```text
Update docs/paper/ieee/build_docx.py and make_figures.py from results files only. Every number needs its source file listed in a table in your report, and remove any claim without a result behind it.

Add the RQ1 and RQ3 results, the single-order vs both-order comparison, the order-sensitivity result on the full course, and the limits of the small gold set. No result may appear twice: use a table or a figure, not both. Keep IEEE format and aim for 6 pages. Don't invent citations: mark unverified ones and list them.

Add Sangeetha J's email, which I'll give you. Export through Word, check every page visually, commit the paper and give me the PR link.
```
