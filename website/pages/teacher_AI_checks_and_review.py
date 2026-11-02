"""For teachers: what the AI checks decided for each link, and the teacher review.

Sections, the links that need the teacher first: counts per decision, teacher review of
HUMAN_REVIEW links (Accept / Reject, blocking links first, then by impact; applied through
cdlp.validation.apply_review), the four checks and quotes for every link, trial-check details
(control / without A / gap), RQ1 results from cdlp/validation/results/ when those files
exist, and the stages and log of the last website build.

Labels are plain words first; the technical term follows in smaller text.
"""

from __future__ import annotations

import json
import subprocess
import sys

import jobs
import networkx as nx
import streamlit as st
import ui
from common import OUTPUTS, ROOT, concept_names, get_active_course, load, resolve_path

from cdlp.learning_path import api

ui.page_header(
    "AI checks and review",
    "What the AI checks decided for each link between topics, and the links that need you.",
    source_file="validated_graph.json",
    teacher=True,
)

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
graph_data = load("validated_graph.json")
edges = graph_data["edges"]


DECISION_WORDS = {"ACCEPT": "Accepted", "REJECT": "Rejected", "HUMAN_REVIEW": "Needs your review"}
CHECK_WORDS = {
    "evidence": "Found in the notes",
    "semantic": "Makes teaching sense",
    "necessity": "Trial: really needed",
    "graph": "Fits the topic map",
}
STRENGTH_WORDS = {"hard": "Must learn first", "soft": "Helps to learn first"}


def label(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def decision_word(decision: str) -> str:
    return DECISION_WORDS.get(decision, decision)


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
st.metric(decision_word("ACCEPT"), counts["ACCEPT"])
st.metric(decision_word("REJECT"), counts["REJECT"])
st.metric(decision_word("HUMAN_REVIEW"), counts["HUMAN_REVIEW"])
st.metric(
    "Share that needs your review", f"{counts['HUMAN_REVIEW'] / len(edges):.0%}" if edges else "—"
)
st.caption(
    "Every suggested link is kept with its decision. Students only see accepted links. "
    "Technical terms: ACCEPT, REJECT, HUMAN_REVIEW; the share is the human-review rate."
)

# ---- Which topics students can use -------------------------------------------
# The Quick check and the Topic map list only ready topics. This is where the rest are named;
# they all stay in concepts.json and on See your topics.
st.subheader("Topics students can use")
on_map = {e[end] for e in edges if e["decision"] == "ACCEPT" for end in ("source", "target")}
quiz_items = load("quiz_items.json")
in_quick_check = {
    c for c in names if c in on_map and api.next_question(graph_data, quiz_items, {}, c) is not None
}
st.write(
    f"Quick check: **{len(in_quick_check)} of {len(names)}** topics. "
    f"Topic map: **{len(on_map & set(names))} of {len(names)}** topics."
)
not_ready = sorted((c for c in names if c not in in_quick_check), key=lambda c: names[c].lower())
with st.expander(f"Topics not ready for students yet ({len(not_ready)})"):
    for concept_id in not_ready:
        reason = "No questions yet" if concept_id in on_map else "No accepted link yet"
        st.markdown(f"- {label(concept_id)}: {reason}")
st.caption(
    "These topics are kept and still show on See your topics. Accepting a link or adding "
    "questions makes them ready. Technical terms: in the ACCEPT graph, with quiz items."
)

# ---- Teacher review ---------------------------------------------------------
# Every decision goes through `python -m cdlp.validation.apply_review` (a module CLI, not
# an import): it records the decision in review_decisions.json, applies all decisions to
# validated_graph.json (never accepting an edge that closes a cycle) and, when
# sim_students.json exists, rebuilds review_queue.json on the updated graph.
st.subheader(decision_word("HUMAN_REVIEW"))
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
        st.cache_data.clear()  # the topic map and study plan read the updated graph


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
        "This page shows example data, so review is off. To review real links, add the course "
        "files on the Add your notes page first. Decisions are never saved to the examples."
    )
if not pending:
    st.success("No links are waiting for you.")


def review_order(edge: dict) -> tuple:
    """Blocking edges first, then by impact (highest first; unknown last), then by id."""
    impact = (queue_rows.get(edge["id"]) or {}).get("impact_score")
    return (not blocking_now(edge), impact is None, -(impact or 0.0), edge["id"])


pending.sort(key=review_order)
n_blocking = sum(blocking_now(e) for e in pending)
if n_blocking:
    st.error(
        f"{n_blocking} blocking link(s): accepting one would make topics depend on each other in "
        "a circle. Reject it, or reject another link in that circle. They come first."
    )
if pending and not queue_rows:
    st.caption("Not ranked by effect on study plans yet. Blocking links come first.")
for edge in pending:
    blocking = blocking_now(edge)
    row = queue_rows.get(edge["id"]) or {}
    with st.container(border=True):
        st.markdown(
            f"**{label(edge['source'])} → {label(edge['target'])}**"
            + (" · ⛔ makes a circle" if blocking else "")
        )
        st.write(edge["reason"])
        st.caption(
            ("blocking · " if blocking else f"impact score {fmt(row.get('impact_score'))} · ")
            + f"AI confidence {edge['confidence']:.2f} · edge {edge['id']}"
        )
        if row.get("paths_affected") is not None:
            st.caption(f"Accepting changes {row['paths_affected']} simulated learning path(s).")
        review = edge.get("review") or {}
        if review.get("status") == "refused_cycle":
            st.warning(
                "Your Accept was refused: it would make this circle of topics: "
                + " → ".join(label(c) for c in review.get("cycle", []))
            )
        st.text_input("Comment (optional)", key=f"comment_{edge['id']}")
        st.button(
            "✅ Accept",
            key=f"accept_{edge['id']}",
            disabled=not live or blocking,
            on_click=decide,
            args=(edge["id"], "ACCEPT"),
            help="Off: accepting would make a circle of topics." if blocking else None,
            width="stretch",
        )
        st.button(
            "❌ Reject",
            key=f"reject_{edge['id']}",
            disabled=not live,
            on_click=decide,
            args=(edge["id"], "REJECT"),
            width="stretch",
        )

if by_teacher:
    with st.expander(f"Decided by teacher ({len(by_teacher)})"):
        for edge in by_teacher:
            review = edge["review"]
            other = "REJECT" if review["decision"] == "ACCEPT" else "ACCEPT"
            st.markdown(
                f"**{label(edge['source'])} → {label(edge['target'])}** · "
                f"{decision_word(review['decision'])} by {review['decided_by']} · "
                f"{review.get('decided_at', '')}"
                + (f" · “{review['comment']}”" if review.get("comment") else "")
            )
            st.button(
                f"Change to {decision_word(other)}",
                key=f"change_{edge['id']}",
                disabled=not live,
                on_click=decide,
                args=(edge["id"], other, review.get("comment", "")),
            )

# ---- Every link: its checks, reason and quotes ------------------------------
st.subheader("All links")
choice = st.radio(
    "Show",
    DECISIONS,
    format_func=lambda d: f"{decision_word(d)} ({counts[d]})",
    horizontal=True,
)
links_box = st.container()  # filled after the trial check: the details use its rows

# ---- Necessity details ------------------------------------------------------
# validated_graph.json carries only necessity_gap. The control and "without A" scores
# come from the necessity-test results file (cdlp/validation/results/necessity_*.json).
# Shown only when this graph ran the necessity test and every edge of the run is an edge
# of this graph: results files are tagged only by course id, so an experiment on the
# shared example edges must never be shown as if it belonged to a live course.
graph_pairs = {(e["source"], e["target"]) for e in edges}
graph_ran_necessity = any(
    e.get("checks", {}).get("necessity") not in (None, "skipped") for e in edges
)
necessity_runs = {
    name: data
    for name, data in read_results("necessity_*.json").items()
    if graph_ran_necessity
    and data.get("course_id", course) == course
    and isinstance(data.get("results"), list)
    and data["results"]
    and {(r.get("source"), r.get("target")) for r in data["results"]} <= graph_pairs
}
necessity_rows: dict[str, dict] = {}
if necessity_runs:
    st.subheader("Trial check: can a learner manage without topic A?")
    run_name = st.selectbox("Trial run", sorted(necessity_runs, reverse=True))
    run = necessity_runs[run_name]
    st.write(
        "A pretend learner answers questions about the later topic without topic A. A second "
        "one is kept from an unrelated topic C instead, to compare. A big difference means A "
        "is really needed. This check is on trial: it does not change any decision."
    )
    st.caption(
        f"Necessity test. model `{run.get('model', '?')}` · "
        f"temperature {run.get('temperature', '?')} · seed {run.get('seed', '?')} · "
        f"leakage rate {run.get('leakage_rate', '?')}. Difference = necessity gap = control "
        "score − score without A."
    )
    for row in run["results"]:
        necessity_rows[f"{row['source']}->{row['target']}"] = row  # by pair, never by id
    st.dataframe(
        [
            {
                "Link": f"{label(r.get('source', ''))} → {label(r.get('target', ''))}",
                "Unrelated topic C": (r.get("control_concept") or {}).get("name"),
                "Score without C (control)": r.get("score_control"),
                "Score without A": r.get("score_without"),
                "Difference (gap)": r.get("necessity_gap"),
                "Grade": r.get("necessity"),
                "Score with A (diagnostic)": r.get("score_with"),
                "Status": r.get("status"),
            }
            for r in run["results"]
        ],
        width="stretch",
        hide_index=True,
    )

# ---- Link table and details (drawn in links_box above) -----------------------
shown = [e for e in edges if e["decision"] == choice]
with links_box:
    st.dataframe(
        [
            {
                "Link": f"{label(e['source'])} → {label(e['target'])}",
                "Decision": decision_word(e["decision"]),
                "Kind": STRENGTH_WORDS.get(e.get("strength"), e.get("strength")),
                "How sure the AI is": e["confidence"],
                **{CHECK_WORDS[check]: grade(e["checks"][check]) for check in CHECKS},
                "Trial difference": e.get("necessity_gap"),
            }
            for e in shown
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Technical terms: How sure the AI is = confidence · Must learn first = hard, Helps to "
        "learn first = soft · "
        + " · ".join(f"{word} = {check} check" for check, word in CHECK_WORDS.items())
        + " · Trial difference = necessity gap."
    )
    for e in shown:
        by = " · decided by teacher" if (e.get("review") or {}).get("status") == "applied" else ""
        with st.expander(f"{label(e['source'])} → {label(e['target'])}{by}"):
            st.write(e["reason"])
            st.markdown(" · ".join(f"**{CHECK_WORDS[c]}** {grade(e['checks'][c])}" for c in CHECKS))
            st.caption(f"AI confidence {e['confidence']:.2f} · edge {e['id']}")
            row = necessity_rows.get(f"{e['source']}->{e['target']}")
            if row:
                control = (row.get("control_concept") or {}).get("name", "?")
                st.markdown(
                    f"Trial check: without *{control}* {fmt(row.get('score_control'))} · "
                    f"without A {fmt(row.get('score_without'))} · "
                    f"difference **{fmt(row.get('necessity_gap'))}**"
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
                                    graded.get("grade", graded)
                                    if isinstance(graded, dict)
                                    else graded
                                )
                                st.caption(f"{side}: {answers[i]} → {graded}")
            else:
                st.caption(
                    f"Trial difference: {fmt(e.get('necessity_gap'))} (no trial-run details)"
                )
            if not e["evidence"]:
                st.caption("No quote.")
            for ev in e["evidence"]:
                st.markdown(f"> {ev.get('quote') or '(no quote)'}")
                st.caption(f"{ev.get('doc', '?')} p.{ev.get('page', '?')}")

# ---- RQ1 results ------------------------------------------------------------
rq1 = {
    name: data
    for name, data in read_results("rq1_*.json").items()
    if isinstance(data.get("rows"), list) and data["rows"]
}
st.subheader("Test results for the AI checks")
if not rq1:
    st.info(
        "No test results yet. They appear here after you run `python -m cdlp.validation.evaluate`."
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
                "Setting": r["setting"],
                "Right when it accepts (precision)": r.get("precision"),
                "True links it keeps (recall)": r.get("recall"),
                "Overall (F1)": r.get("f1"),
                "Share needing review": r.get("human_review_rate"),
                "AI calls / link": r.get("llm_calls_per_edge"),
                "new calls / link": r.get("real_llm_calls_per_edge"),
            }
            for r in rows
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "AI calls / link = (new calls + saved answers) / links: the calls a setting needs, the "
        "same on a re-run. New calls / link counts only requests the model answered in that "
        "run. Both include the calls that first suggested the links."
    )
    with st.expander("Config"):
        st.json(config)

# ---- Last website build -------------------------------------------------------
# The stage names and log stay here: step 1 tells students about progress in plain words.
build = jobs.read_status(course)
if build["state"] != "none":
    st.subheader("Last time the notes were read")
    st.dataframe(
        [
            {"Stage": s["label"], "Status": s["status"], "Module": s["stage"]}
            for s in build["stages"]
        ],
        width="stretch",
        hide_index=True,
    )
    if build["error"]:
        st.caption(build["error"])
    with st.expander("Log"):
        st.code(build["log"] or "(empty)", language="text")
