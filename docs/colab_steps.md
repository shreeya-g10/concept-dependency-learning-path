# Running everything on Colab

All the LLM work runs on Colab's free GPU **inside** `notebooks/colab_validator.ipynb`, with no tunnel: extraction, discovery, validation, quiz generation and the benchmark nights. It uses exactly `qwen2.5:7b-instruct` and `llama3.1:8b`, one loaded at a time unless both fit on the GPU.

Colab's free tier gives at most 12 hours per session and no guaranteed GPU. Outputs and the LLM cache live on Google Drive, so after a disconnect finished steps are skipped and saved calls are read back. Drive saves in the background, so the last few seconds of calls can be lost and asked again.

## Which stage does what

| Stage | Needs first | It writes |
|---|---|---|
| `course` | course files in the repo, or in `My Drive/cdlp/raw/<course>/` | `outputs/<course>/`: `concepts.json`, `chunks.jsonl`, `relationships.json`, `validated_graph.json`, `quiz_items.json`, `learning_path.json` |
| `real` | `course` steps through `discover` for ds101 and ml101 | `outputs/<course>/validated_plus_necessity.json` as well (the same 40 edges at weight 1, for the paper) |
| `night1` | the benchmark samples (section 1b) | `outputs/rq1/<graph>/relationships.json`, `relationships_baseline.json` |
| `night2` | `night1` | `outputs/rq1/<graph>/validated_single_judge.json`, `validated_minus_evidence_necessity.json` |
| `night3` | `night2` | `outputs/rq1/<graph>/validated_self_consistency.json`, `validated_single_judge_subset.json` |

The `course` stage always:

- Asks each pair in both orders under `order_rule_v1`, and stops if `relationships.json` is not such a run.
- Writes questions with `quiz_v3`, and stops if `quiz_items.json` came from another prompt.
- Runs necessity on 40 edges for ds101 and ml101. Any other course skips necessity.
- Reports `drop_rate_by_level` and `concepts_missing_level`.

Every run records the GPU, both model digests and the embedding model's revision in `colab_environment.json`, and prints seconds per call for each call type and the total time. These are saved beside the run as `colab_calls.summary.json` (or `colab_calls_<stage>.summary.json`).

## 1. Upload (on your laptop)

### 1a. For ds101: the existing 85 concepts and saved replies

This keeps the 85-concept list and every saved reply, so those calls are not paid for again.

1. In the repo folder, make the upload zip. It stops if the concept list is not 85, or if a cited chunk is missing:
   ```bash
   .venv/bin/python scripts/colab_run.py pack --course ds101 \
     --concepts ../cdlp-t4/outputs/ds101/filtered/concepts.json \
     --chunks ../cdlp-t4/outputs/ds101/chunks.jsonl \
     --extra ../cdlp-t4/outputs/ds101/filtered/concept_filter_report.json \
     --cache ../cdlp-t4/.cache/llm \
     --expect-concepts 85 --zip ~/Desktop/ds101_start.zip
   ```
   Use `filtered/concepts.json`. The `concepts.json` beside it is the unfiltered 259-concept list.
2. Open <https://drive.google.com> → **My Drive** → **New** → **New folder** → name it `cdlp`.
3. Open `cdlp` → **New** → **File upload** → choose `ds101_start.zip` from your Desktop.

Step 4 of the notebook unpacks it and never overwrites a file already on Drive. Because `concepts.json` and `chunks.jsonl` are then there, the `extract` step counts as done and is skipped.

### 1b. For night1: the benchmark samples

Nothing here calls a model. `data/benchmarks/` must already hold the downloads described in `cdlp/benchmarks/README.md`.

```bash
.venv/bin/python -m cdlp.benchmarks --dataset al_cpl
.venv/bin/python -m cdlp.benchmarks --dataset university_course
.venv/bin/python -m cdlp.benchmarks.sample
zip -qr ~/Desktop/outputs.zip outputs/benchmarks
```

Upload `outputs.zip` to `My Drive/cdlp`, as in 1a. To continue a night started on the laptop, zip `outputs/rq1` into it as well.

### 1c. For a course that is not in the repo

In Drive, open `cdlp` → **New** → **New folder** → name it `raw`. Inside it make a folder with the course id (lower case letters, digits and `_`, for example `avl_notes`), and upload the course files there. This course skips necessity.

## 2. Open the notebook (in Colab)

1. Open this link: <https://colab.research.google.com/github/shreeya-g10/concept-dependency-learning-path/blob/integration/real-pipeline/notebooks/colab_validator.ipynb>

   This needs the pull request merged into `integration/real-pipeline`. Colab's GitHub tab opens `main` by default, which does not have this notebook.
2. **Runtime** → **Change runtime type** → **T4 GPU** → **Save**.
3. In the first cell set `STAGE`, and for a course also `COURSE` and `STEPS`. Leave `COMMIT` as it is.

## 3. Run (in Colab)

1. Click each cell's ▶ in order, from step 0 to step 6. Step 3 downloads the pinned embedding model and prints `embedding model ready, revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 dimension: 384`. Step 4 asks to connect Google Drive: click **Connect to Google Drive** and allow it.
2. Step 5 prints seconds per call: 10 short and 5 long calls for each model. Use them to estimate the stage before step 6.
3. Step 6 runs the stage and prints one line per step, then the measured time.
4. Keep the browser tab open: an idle tab disconnects.
5. Check progress at any time with step 7.
6. **After a disconnect:** **Runtime** → **Run all**, or run steps 0–4 and then step 6 again. Colab's disk is wiped between sessions, so step 3 downloads the embedding model again.

### The pinned embedding model

The model is pinned to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, the one that produced the existing 85-concept ds101 list. Embeddings decide which concepts merge and which pairs become candidates, so another revision could change results. To keep this true:

- Step 3 downloads that revision by commit, and points the cache's `refs/main` at it, because every module loads through `refs/main`.
- A stage stops if the model is at any other revision.
- Stages run with `HF_HUB_OFFLINE=1`, so no step can fetch a newer revision. Stages only reach Hugging Face through step 3.

To move to a new revision, change it in `scripts/colab_run.py` and in step 3, and update the pinned `COMMIT`. Treat that as a change to the results: the 85-concept list was not made with it.

### If a stage says the embedding model is not downloaded or is at another revision

Step 5 or 6 stops with `The embedding model sentence-transformers/all-MiniLM-L6-v2 is not downloaded`, or `is at revision ..., but this project is pinned to ...`. Extraction needs this model and does not fall back to anything else, so the stage stops before it starts.

1. Run step 3 again and check that it prints `embedding model ready, revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 dimension: 384`.
2. Run the stage again. Nothing is lost, because finished steps are skipped.

If the message also says `HF_HOME` is set, the model was saved somewhere extraction does not look. Extraction only looks in `~/.cache/huggingface/hub`. To fix it:

1. **Runtime** → **Restart session**. The setting is read when the library first loads, so changing it later has no effect.
2. Click **+ Code** above step 0, type `import os; os.environ.pop("HF_HOME", None)`, and click ▶.
3. Run the notebook from step 0.

### Stopping discovery for review

1. Set `STEPS = "extract,discover"` and run through step 6.
2. In Drive, open `cdlp/outputs/<course>/relationships.json` and review it.
3. Set `STEPS = "validate,quiz,path"`, run step 0, and run step 6 again.

A step that needs an earlier step's file stops and says which file is missing. To redo a finished step, delete its file on Drive. Saved replies are still reused.

### For the paper: ds101 and ml101 with necessity at weight 1

After a course's `validate` step, set `STAGE = "real"` and run step 6. Its first step for each course is the course's own graph, so it counts as done, and the rest comes mostly from saved replies. If ml101 has no `relationships.json` yet, its steps are skipped and listed.

## 4. Download (back on your laptop)

1. In Colab, run step 8. For a course it writes `course_<id>_<date>.zip`, which holds **only that course's outputs**, in `My Drive/cdlp`, and prints the steps below with the real file name. It refuses a course that is not finished.
2. In Drive, open `cdlp`, right-click the zip → **Download**.
3. In the repo folder, keep any older copy out of the way (a name starting with `_` is hidden from the website), then unzip:
   ```bash
   mv outputs/<id> outputs/_old_<id>
   unzip -o ~/Downloads/course_<id>_<date>.zip -d .
   ```
   The files land in `outputs/<id>/`. The folder name must stay `<id>`.
4. Start or reload the website and pick the course on Home. The website lists a course once `outputs/<id>/` holds `concepts.json` and `validated_graph.json`. Ollama can stay off.

For a night stage, step 8 writes `results_<stage>_<date>.zip`. Unzip it the same way. For local scoring, `cache_<date>.zip` holds the saved replies: `unzip -o ~/Downloads/cache_<date>.zip -d .cache`.

## What the website does with Ollama off

It opens a downloaded course and works normally, except that the reason after a wrong answer is labelled "our best guess, the AI helper was off". Reading new notes needs the AI, but Quick Preview still works.

## Record in the results and the paper

From `colab_environment.json`: the GPU, the Ollama version, both model digests and the embedding model's revision. Compare the `llama3.1:8b` digest with the local model's ID (`ollama list`: `46e0c10c039e`) so the paper can say whether Colab ran the same weights. The embedding revision is pinned to the laptop's, so it should be `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` in every run's entry. From `colab_calls.summary.json`: seconds per call for each call type. From the course report: `drop_rate_by_level` and `concepts_missing_level`.
