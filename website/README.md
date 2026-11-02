# Website

A multi-page Streamlit site, free to host on Streamlit Community Cloud.

```bash
streamlit run website/Home.py
```

Every page reads pipeline outputs from `outputs/`. When those don't exist yet, it falls back to `cdlp/shared/examples/`, so each page works from day one.

**Answer log (page 5).** Every quiz answer is appended to `outputs/<course>/student_answers.json` under a random per-session id (`anon_<hex>`); no name, login or IP is stored. The file feeds root-cause tracing (`pipeline.py`) and the real-student study. Writes are atomic but not locked across sessions, and Streamlit Community Cloud's disk is wiped on redeploy, so download the file after each study session. A root cause that comes from a fallback (LLM unreachable or unusable) is labelled "offline estimate" / "baseline estimate", never shown as an LLM explanation.

## Pages

Maintainer: Shreeya. Shell and pages 1, 4, 5 were built by Vaidehi (pages 4 and 5 from Shrestha's initial code); page 2 started from Sneha's code.

| File | Shows |
|---|---|
| `Home.py`, `common.py`, `requirements.txt`, `.streamlit/` | Shell, navigation, styling, deployment |
| `pages/1_Course_Material.py` | Concepts + source pages |
| `pages/2_Proposed_Dependencies.py` | LLM-proposed edges |
| `pages/3_Validation_Agent.py` | Decisions, checks, evidence, necessity gap |
| `pages/4_Knowledge_Graph.py` | Interactive validated graph |
| `pages/5_My_Learning_Path.py` | Adaptive quiz + personal path |

## Rules

- Pages read contract files through `common.load("<file>.json")`, never by running pipeline code.
- The only module code a page may import is `cdlp/learning_path/api.py` (live quiz on page 5) and `cdlp/root_cause/api.py`.
- Shared page helpers go in `common.py`.
- CI renders every page on example data (`website/test_pages.py`), so keep every page working before you open a PR.
