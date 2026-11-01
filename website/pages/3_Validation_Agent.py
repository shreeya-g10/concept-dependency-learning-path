"""Owner: Shreeya. Shows each validation decision with its checks, evidence and reason.

Sections: counts per decision, the four checks for every edge, necessity-test details
(control / without A / gap), the impact-ranked review queue when it exists, and RQ1 and
necessity results from cdlp/validation/results/ when those files exist.
"""

from __future__ import annotations

import json

import streamlit as st
from common import (
    ROOT,
    concept_names,
    get_active_course,
    load,
    page_header,
    render_sidebar,
    resolve_path,
)

render_sidebar()
page_header("Validation Agent", "Shreeya", "validated_graph.json")

RESULTS = ROOT / "cdlp" / "validation" / "results"
DECISIONS = ["ACCEPT", "REJECT", "HUMAN_REVIEW"]
CHECKS = ["evidence", "semantic", "necessity", "graph"]
GRADE_ICON = {"strong": "🟢", "medium": "🟡", "weak": "🟠", "none": "⚪", "ok": "🟢"}

course = get_active_course()
names = concept_names()
edges = load("validated_graph.json")["edges"]


def label(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def grade(value: str) -> str:
    return f"{GRADE_ICON.get(value, '🔴')} {value}"


def read_results(pattern: str) -> dict[str, dict]:
    """Every readable JSON file in results/ matching pattern, by file name."""
    found = {}
    for path in sorted(RESULTS.glob(pattern)):
        try:
            found[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return found


def fmt(value) -> str:
    return "—" if value is None else f"{value:.2f}"


# ---- Counts per decision ----------------------------------------------------
st.subheader("Decisions")
counts = {d: sum(e["decision"] == d for e in edges) for d in DECISIONS}
cols = st.columns(4)
cols[0].metric("Accepted", counts["ACCEPT"])
cols[1].metric("Rejected", counts["REJECT"])
cols[2].metric("Human review", counts["HUMAN_REVIEW"])
cols[3].metric("Human-review rate", f"{counts['HUMAN_REVIEW'] / len(edges):.0%}" if edges else "—")
st.caption("Every proposed edge is kept with its decision; downstream pages use ACCEPT only.")

# ---- Four checks per edge ---------------------------------------------------
st.subheader("Checks per edge")
decision_filter = st.multiselect("Decision", DECISIONS, default=DECISIONS)
shown = [e for e in edges if e["decision"] in decision_filter]
st.dataframe(
    [
        {
            "id": e["id"],
            "edge": f"{label(e['source'])} → {label(e['target'])}",
            "decision": e["decision"],
            "confidence": e["confidence"],
            **{check: grade(e["checks"][check]) for check in CHECKS},
            "necessity gap": e.get("necessity_gap"),
        }
        for e in shown
    ],
    width="stretch",
    hide_index=True,
)

# ---- Necessity details ------------------------------------------------------
# validated_graph.json carries only necessity_gap. The control and "without A" scores
# come from the necessity-test results file (cdlp/validation/results/necessity_*.json).
necessity_runs = {
    name: data
    for name, data in read_results("necessity_*.json").items()
    if data.get("course_id", course) == course and isinstance(data.get("results"), list)
}
necessity_rows: dict[str, dict] = {}
if necessity_runs:
    st.subheader("Necessity test")
    run_name = st.selectbox("Necessity run", sorted(necessity_runs, reverse=True))
    run = necessity_runs[run_name]
    st.caption(
        f"model `{run.get('model', '?')}` · temperature {run.get('temperature', '?')} · "
        f"seed {run.get('seed', '?')} · leakage rate {run.get('leakage_rate', '?')}. "
        "Gap = control score − score without A. The control learner bans an unrelated "
        "concept C instead of A."
    )
    for row in run["results"]:
        necessity_rows[row.get("relationship_id") or f"{row['source']}->{row['target']}"] = row
    st.dataframe(
        [
            {
                "edge": f"{label(r.get('source', ''))} → {label(r.get('target', ''))}",
                "control C": (r.get("control_concept") or {}).get("name"),
                "control": r.get("score_control"),
                "without A": r.get("score_without"),
                "gap": r.get("necessity_gap"),
                "grade": r.get("necessity"),
                "with A (diag.)": r.get("score_with"),
                "status": r.get("status"),
            }
            for r in run["results"]
        ],
        width="stretch",
        hide_index=True,
    )

# ---- Edge details -----------------------------------------------------------
st.subheader("Edge details")
decision = st.radio("Show", DECISIONS, horizontal=True)
for e in edges:
    if e["decision"] != decision:
        continue
    with st.expander(f"{label(e['source'])} → {label(e['target'])} · {e['confidence']:.2f}"):
        st.write(e["reason"])
        st.markdown(" · ".join(f"**{check}** {grade(e['checks'][check])}" for check in CHECKS))
        row = necessity_rows.get(e["id"]) or necessity_rows.get(f"{e['source']}->{e['target']}")
        if row:
            control = (row.get("control_concept") or {}).get("name", "?")
            st.markdown(
                f"Necessity: control (bans *{control}*) {fmt(row.get('score_control'))} · "
                f"without A {fmt(row.get('score_without'))} · "
                f"gap **{fmt(row.get('necessity_gap'))}**"
            )
            with st.popover("Questions and answers"):
                for i, question in enumerate(row.get("questions", [])):
                    st.markdown(f"**Q{i + 1}.** {question.get('question', question)}")
                    for side in ("without", "control"):
                        answers = row.get(f"answers_{side}", [])
                        grades = row.get(f"grades_{side}", [])
                        if i < len(answers):
                            graded = grades[i] if i < len(grades) else "?"
                            graded = (
                                graded.get("grade", graded) if isinstance(graded, dict) else graded
                            )
                            st.caption(f"{side}: {answers[i]} → {graded}")
        else:
            st.caption(f"Necessity gap: {fmt(e.get('necessity_gap'))} (no necessity-run details)")
        if not e["evidence"]:
            st.caption("No evidence chunk.")
        for ev in e["evidence"]:
            st.markdown(f"> {ev.get('quote') or '(no quote)'}")
            st.caption(f"{ev.get('doc', '?')} p.{ev.get('page', '?')} · chunk `{ev['chunk_id']}`")

# ---- Review queue -----------------------------------------------------------
st.subheader("Human review queue")
if not resolve_path("review_queue.json").exists():
    st.info("No review_queue.json yet. Run validation with `--review-queue`.")
else:
    queue = load("review_queue.json")["queue"]
    if not queue:
        st.success("Nothing waits for review.")
    st.dataframe(
        [
            {
                "edge": f"{label(q['source'])} → {label(q['target'])}",
                "impact": q.get("impact_score"),
                "paths affected": q.get("paths_affected"),
                "reason": q.get("reason", ""),
            }
            for q in sorted(queue, key=lambda q: -(q.get("impact_score") or 0))
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption("Highest impact first: how many simulated students' paths change if the edge flips.")

# ---- RQ1 results ------------------------------------------------------------
rq1 = {
    name: data
    for name, data in read_results("rq1_*.json").items()
    if isinstance(data.get("rows"), list) and data["rows"]
}
st.subheader("RQ1 results")
if not rq1:
    st.info(
        "No RQ1 results yet. They appear here once "
        "`python -m cdlp.validation.evaluate` writes `cdlp/validation/results/rq1_*.json`."
    )
else:
    name = st.selectbox("Results file", sorted(rq1))
    data = rq1[name]
    rows = data["rows"]
    config = data.get("config", {})
    done = [r for r in rows if r.get("status", "ok") == "ok" and r.get("f1") is not None]
    missing = [r["setting"] for r in rows if r not in done]
    st.caption(
        f"dataset `{data.get('dataset', '?')}` · course `{data.get('course_id', '?')}` · "
        f"scoring `{data.get('scoring', config.get('scoring', '?'))}` · "
        f"{len(done)} of {len(rows)} settings run"
    )
    if missing:
        st.caption(f"Not run yet (left out of the chart): {', '.join(missing)}")
    if done:
        st.bar_chart(
            {
                metric: {r["setting"]: r[metric] for r in done}
                for metric in ("precision", "recall", "f1")
            },
            stack=False,
        )
    st.dataframe(
        [
            {
                "setting": r["setting"],
                "precision": r.get("precision"),
                "recall": r.get("recall"),
                "F1": r.get("f1"),
                "human review rate": r.get("human_review_rate"),
                "LLM calls / edge": r.get("llm_calls_per_edge"),
            }
            for r in rows
        ],
        width="stretch",
        hide_index=True,
    )
    with st.expander("Config"):
        st.json(config)
