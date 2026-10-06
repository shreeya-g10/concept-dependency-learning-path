# Website

A multi-page Streamlit site, free to host on Streamlit Community Cloud.

```bash
streamlit run website/Home.py
```

Every page reads pipeline outputs from `outputs/`. When those don't exist yet, it falls back to `cdlp/shared/examples/`, so each page works from day one.

## Each page has one owner, so nobody edits the same file

| File | Owner | Shows |
|---|---|---|
| `Home.py`, `common.py`, `requirements.txt`, `.streamlit/` | Vaidehi | Shell, navigation, styling, deployment |
| `pages/1_Course_Material.py` | Vaidehi | Concepts + source pages |
| `pages/2_Proposed_Dependencies.py` | Sneha | LLM-proposed edges |
| `pages/3_Validation_Agent.py` | Shreeya | Decisions, checks, evidence, necessity gap |
| `pages/4_Knowledge_Graph.py` | Shrestha | Interactive validated graph |
| `pages/5_My_Learning_Path.py` | Shrestha | Adaptive quiz + personal path |

## Rules

- Pages read contract files through `common.load("<file>.json")`, never by running pipeline code.
- The only module code a page may import is `cdlp/learning_path/api.py`, for the live quiz on page 5.
- Need a new helper in `common.py`? Ask Vaidehi. Until then, keep it inside your own page.
- CI renders every page on example data (`website/test_pages.py`), so keep your page working before you open a PR.
