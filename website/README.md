# Website

A multi-page Streamlit site, free to host on Streamlit Community Cloud.

```bash
streamlit run website/Home.py
```

Every page reads pipeline outputs from `outputs/`. When those don't exist yet, it falls back to `cdlp/shared/examples/`, so each page works from day one.

**Answer log (Quick check).** Every quiz answer is appended to `outputs/<course>/student_answers.json` under a random per-session id (`anon_<hex>`); no name, login or IP is stored. The file feeds root-cause tracing (`pipeline.py`) and the real-student study. Writes are atomic but not locked across sessions. The real-student study runs **locally** (`streamlit run website/Home.py` on the maintainer's laptop), so the log stays on that disk and no hosted storage is needed; a hosted deployment (Streamlit Community Cloud wipes its disk on redeploy) is for demos only and its answers are not study data. A root cause that comes from a fallback (LLM unreachable or unusable) is labelled in plain words as "our best guess ... not from the AI helper", never shown as an LLM explanation.

## Pages

| File | Shows |
|---|---|
| `Home.py` | Entry point: page setup and the menu (`st.navigation`), then runs the current page |
| `ui.py`, `strings.py`, `common.py` | Shared page parts, all student-facing text, data helpers |
| `../.streamlit/config.toml` | Theme |
| `pages/0_Start_here.py` | Pick a subject, the 4 steps |
| `pages/1_Add_your_notes.py` | Upload + background build |
| `pages/2_See_your_topics.py` | Concepts + source pages |
| `pages/3_Quick_check.py` | Adaptive quiz |
| `pages/4_My_study_plan.py` | Personal path |
| `pages/5_Topic_map.py` | My Study Path and All Topics views, concept lists; picture shows by itself at 30 links or fewer |
| `pages/teacher_AI_checks_and_review.py` | For teachers: decisions, checks, evidence, necessity gap, review |
| `pages/teacher_AI_suggestions.py` | For teachers: LLM-proposed edges |

A new page must be added to `ui.PAGES`: `st.navigation` ignores files it is not told about.

## Rules

- Pages read contract files through `common.load("<file>.json")`, never by running pipeline code.
- The only module code a page may import is `cdlp/learning_path/api.py` (live quiz) and `cdlp/root_cause/api.py`.
- Shared page parts go in `ui.py`, data helpers in `common.py`.
- **Student pages:** one column; one main action per screen; plain words at about a 6th-grade level; an icon always with a word; no team names, research terms or course IDs; every error says what to do next (`ui.friendly_error`). All their text lives in `strings.py`.
- **Honesty:** `ui.page_header(source_file=...)` shows the sample and demo notices: one short line for students, the full notice and the written rule with `teacher=True`. Keep them. Never state anything we have not measured.
- CI renders every page on example data (`website/test_pages.py`), so keep every page working before you open a PR.
