"""Owner: Shreeya. Shows each validation decision with its checks, evidence and reason.

Sections: counts per decision, the four checks for every edge, necessity-test details
(control / without A / gap), teacher review of HUMAN_REVIEW edges (Accept / Reject,
blocking edges first, then by impact; applied through cdlp.validation.apply_review), and
RQ1 and necessity results from cdlp/validation/results/ when those files exist.
"""

from __future__ import annotations

import json
import subprocess
import sys

import networkx as nx
import streamlit as st
from common import (
    OUTPUTS,
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
GRADE_ICON = {
    "strong": "🟢",
    "medium": "🟡",
    "weak": "🟠",
    "none": "⚪",
    "ok": "🟢",
    "skipped": "➖",
}

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
    by = " · decided by teacher" if (e.get("review") or {}).get("status") == "applied" else ""
    with st.expander(f"{label(e['source'])} → {label(e['target'])} · {e['confidence']:.2f}{by}"):
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

# ---- Teacher review ---------------------------------------------------------
# Every decision goes through `python -m cdlp.validation.apply_review` (a module CLI, not
# an import): it records the decision in review_decisions.json, applies all decisions to
# validated_graph.json (never accepting an edge that closes a cycle) and, when
# sim_students.json exists, rebuilds review_queue.json on the updated graph.
st.subheader("Teacher review")
out_dir = OUTPUTS / course
graph_path = resolve_path("validated_graph.json")
live = graph_path == out_dir / "validated_graph.json"
students_path = out_dir / "sim_students.json"
queue_path = out_dir / "review_queue.json"


def run_apply(*extra: str) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "-m",
        "cdlp.validation.apply_review",
        *["--graph", str(graph_path), "--decisions", str(out_dir / "review_decisions.json")],
    ]
    if students_path.exists():
        command += ["--students", str(students_path), "--queue", str(queue_path)]
    return subprocess.run([*command, *extra], cwd=ROOT, capture_output=True, text=True, timeout=120)


def decide(edge_id: str, decision: str, comment: str | None = None) -> None:
    """Button callback. The comment is read now, not when the button was drawn, so text
    typed just before the click is kept."""
    if comment is None:
        comment = st.session_state.get(f"comment_{edge_id}", "")
    result = run_apply("--decide", edge_id, decision, "--comment", comment)
    if result.returncode != 0:
        st.session_state["review_error"] = (result.stderr or result.stdout).strip()
    else:
        st.session_state["review_note"] = result.stdout.strip()
        st.cache_data.clear()  # pages 4 and 5 read the updated graph


def blocking_now(edge: dict) -> bool:
    """Accepting the edge now would close a cycle with the current ACCEPT edges."""
    accepted = nx.DiGraph((e["source"], e["target"]) for e in edges if e["decision"] == "ACCEPT")
    source, target = edge["source"], edge["target"]
    return source == target or (
        source in accepted and target in accepted and nx.has_path(accepted, target, source)
    )


pending = [e for e in edges if e["decision"] == "HUMAN_REVIEW"]
by_teacher = [e for e in edges if (e.get("review") or {}).get("status") == "applied"]
if live and pending and students_path.exists():
    stale = not queue_path.exists() or queue_path.stat().st_mtime < graph_path.stat().st_mtime
    if stale and run_apply().returncode == 0:  # rank by impact on the current graph
        st.cache_data.clear()
queue_file = queue_path if live else resolve_path("review_queue.json")
queue_rows = {}
if queue_file.exists():
    queue_rows = {q["edge_id"]: q for q in json.loads(queue_file.read_text())["queue"]}

for key, show in (("review_error", st.error), ("review_note", st.success)):
    if key in st.session_state:
        show(st.session_state.pop(key))
if not live:
    st.info(
        f"This page shows example data. Build `{course}` on page 1 first: teacher decisions "
        f"are saved to `outputs/{course}/review_decisions.json`, never to the examples."
    )
if not pending:
    st.success("Nothing waits for review.")


def review_order(edge: dict) -> tuple:
    """Blocking edges first, then by impact (highest first; unknown last), then by id."""
    impact = (queue_rows.get(edge["id"]) or {}).get("impact_score")
    return (not blocking_now(edge), impact is None, -(impact or 0.0), edge["id"])


pending.sort(key=review_order)
n_blocking = sum(blocking_now(e) for e in pending)
if n_blocking:
    st.error(
        f"{n_blocking} blocking edge(s): accepting them would close a cycle, so they can only "
        "be rejected (or resolved by rejecting another edge in the cycle). They come first."
    )
if pending and not queue_rows:
    st.caption("No impact ranking yet (needs sim_students.json); ordered by blocking, then id.")
for edge in pending:
    blocking = blocking_now(edge)
    row = queue_rows.get(edge["id"]) or {}
    tag = "⛔ blocking" if blocking else f"impact {fmt(row.get('impact_score'))}"
    with st.container(border=True):
        st.markdown(
            f"**{label(edge['source'])} → {label(edge['target'])}** · `{edge['id']}` · {tag} · "
            f"validator confidence {edge['confidence']:.2f}"
        )
        st.caption(edge["reason"])
        if row.get("paths_affected") is not None:
            st.caption(f"Accepting changes {row['paths_affected']} simulated learning path(s).")
        review = edge.get("review") or {}
        if review.get("status") == "refused_cycle":
            st.warning(
                "A teacher ACCEPT was refused: it would close the cycle "
                + " → ".join(label(c) for c in review.get("cycle", []))
            )
        st.text_input("Comment (optional)", key=f"comment_{edge['id']}")
        c1, c2, _ = st.columns([1, 1, 4])
        c1.button(
            "✅ Accept",
            key=f"accept_{edge['id']}",
            disabled=not live or blocking,
            on_click=decide,
            args=(edge["id"], "ACCEPT"),
            help="Disabled: accepting would close a cycle." if blocking else None,
        )
        c2.button(
            "❌ Reject",
            key=f"reject_{edge['id']}",
            disabled=not live,
            on_click=decide,
            args=(edge["id"], "REJECT"),
        )

if by_teacher:
    with st.expander(f"Decided by teacher ({len(by_teacher)})"):
        for edge in by_teacher:
            review = edge["review"]
            other = "REJECT" if review["decision"] == "ACCEPT" else "ACCEPT"
            st.markdown(
                f"**{label(edge['source'])} → {label(edge['target'])}** · "
                f"{review['decision']} by {review['decided_by']} · {review.get('decided_at', '')}"
                + (f" · “{review['comment']}”" if review.get("comment") else "")
            )
            st.button(
                f"Change to {other}",
                key=f"change_{edge['id']}",
                disabled=not live,
                on_click=decide,
                args=(edge["id"], other, review.get("comment", "")),
            )

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
                "real calls / edge": r.get("real_llm_calls_per_edge"),
            }
            for r in rows
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "LLM calls / edge = (real calls + cache hits) / edges: the calls a setting needs, "
        "the same on a cached re-run. Real calls / edge counts only requests the model "
        "answered in that run. Both include discovery's calls for validator settings."
    )
    with st.expander("Config"):
        st.json(config)
