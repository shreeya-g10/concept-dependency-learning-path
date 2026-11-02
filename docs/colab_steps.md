# Running the validator on Colab

The validator (`llama3.1:8b`) does not fit in this laptop's 8 GB of RAM (about 48 s per call, heavy swapping), so it runs on Colab's free GPU **inside** `notebooks/colab_validator.ipynb`, with no tunnel. Discovery and extraction stay local on `qwen2.5:7b-instruct`. Colab's free tier gives at most 12 hours per session and no guaranteed GPU; a disconnect loses nothing, because outputs and the LLM cache live on Google Drive.

## Which stage needs which local outputs

| Stage | Run it after (locally) | It writes |
|---|---|---|
| `night2` | night 1 (`scripts/rq1_night1.sh`) | `outputs/rq1/<graph>/validated_single_judge.json`, `validated_minus_evidence_necessity.json` |
| `night3` | night 2 on Colab | `outputs/rq1/<graph>/validated_self_consistency.json`, `validated_single_judge_subset.json` |
| `real` | local extraction + discovery of ds101 and ml101 | `outputs/<course>/validated_graph.json`, `validated_plus_necessity.json` (+ `*.necessity_sample.json`) |

Every stage also appends the GPU, Ollama version, model digest and repo commit to `outputs/colab_environment.json`.

## 1. Upload (on your laptop)

1. In the repo folder, zip the outputs:
   ```bash
   cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && zip -qr ~/Desktop/outputs.zip outputs
   ```
2. Open <https://drive.google.com> → **My Drive** → **New** → **New folder** → name it `cdlp`.
3. Open `cdlp` → **New** → **File upload** → choose `outputs.zip` from your Desktop.

Later stages: zip and upload `outputs.zip` again. The notebook adds the new files and never overwrites results already on Drive.

## 2. Open the notebook (in Colab)

1. Open <https://colab.research.google.com> → **File** → **Open notebook** → **GitHub** tab.
2. Paste `shreeya-g10/concept-dependency-learning-path`, press Enter, and click `notebooks/colab_validator.ipynb`.
3. **Runtime** → **Change runtime type** → **T4 GPU** → **Save**.
4. In the first cell, set `STAGE` to `"night2"`, `"night3"` or `"real"`. Leave `COMMIT` as it is.

## 3. Run (in Colab)

1. Click each cell's ▶ in order, from step 0 to step 6. Step 4 asks to connect Google Drive: click **Connect to Google Drive** and allow it.
2. Step 5 prints seconds per call. Step 6 runs the stage and prints one line per step.
3. Keep the browser tab open: an idle tab disconnects.
4. Check progress at any time with step 7.
5. **After a disconnect:** **Runtime** → **Run all**, or run steps 0–4 and then step 6 again. Finished steps are skipped and earlier calls come from the cache on Drive.

## 4. Download (back on your laptop)

1. In Colab, run step 8. It writes `results_<stage>_<date>.zip` and `cache_<stage>_<date>.zip` in `My Drive/cdlp`.
2. In Drive, open `cdlp`, right-click each zip → **Download**.
3. Unzip both into the repo folder (replace when asked):
   ```bash
   cd /Users/shreeyakhairnar/Desktop/PREP/projects/GenAI/concept-dependency-learning-path && unzip -o ~/Downloads/results_<stage>_<date>.zip && unzip -o ~/Downloads/cache_<stage>_<date>.zip -d .cache
   ```
   The cache zip holds `llm/`, so it lands in `.cache/llm/`. Local scoring can then re-read every validator call without calling a model.

## Record in the results and the paper

From `outputs/colab_environment.json`: the GPU, the Ollama version and the `llama3.1:8b` digest. Compare the digest with the local model's ID (`ollama list`: `46e0c10c039e`) so the paper can say whether Colab ran the same weights. Discovery and extraction: `qwen2.5:7b-instruct`, local.
