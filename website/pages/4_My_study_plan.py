"""Step 4: the personal study plan, from the answers given in step 3.

Reads the answers from session state (pages/3_Quick_check.py writes them) and the path from
cdlp/learning_path/api.py, reasons included.

When the question limit stopped the quick check, topics the student was not asked count as
unknown, so they stay on the plan even if a right answer elsewhere suggested they are known.

What a student marks as done stays in session state only. It does not change what we think
they know, and it is not written to the answer log.
"""

from __future__ import annotations

import common
import streamlit as st
import strings as S
import ui

from cdlp.learning_path import api

course = common.get_active_course()
names = common.concept_names()
concepts = {c["id"]: c for c in common.load("concepts.json")["concepts"]}
graph_data = common.load("validated_graph.json")
target = st.session_state.get("study_target")
accepted = [e for e in graph_data.get("edges", []) if e.get("decision") == "ACCEPT"]
in_graph = {node["id"] for node in graph_data.get("nodes", [])} | {
    end for edge in accepted for end in (edge["source"], edge["target"])
}


def header(intro: str | None = None) -> None:
    ui.page_header(S.PLAN_TITLE, intro, step=4, source_file="validated_graph.json")


if (
    not st.session_state.get("quiz_answers")
    or st.session_state.get("quiz_course") != course
    or target not in names
    or target not in in_graph
):
    header(S.PLAN_INTRO)
    ui.empty_state(S.PLAN_EMPTY, S.PLAN_EMPTY_NEXT, action=S.PLAN_TO_QUIZ, page="quiz", icon="✏️")
    st.stop()

mastery = st.session_state.quiz_mastery
more_questions = api.next_question(
    graph_data,
    common.load("quiz_items.json"),
    {**mastery, "__asked__": list(st.session_state.get("quiz_asked", []))},
    target,
)
asked_for_target = st.session_state.get("quiz_topic_counts", {}).get(target, 0)
limit_stopped = more_questions is not None and asked_for_target >= api.MAX_QUESTIONS_PER_TOPIC
steps = api.personalized_path(
    graph_data, api.only_answered(mastery) if limit_stopped else mastery, target
)
plan_order = [step["concept_id"] for step in steps]
done = st.session_state.setdefault("plan_done", {}).setdefault(course, [])
next_up = next((c for c in plan_order if c not in done), None)


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def where_to_read(step: dict) -> str:
    """Where the topic itself is in the notes.

    The topic's own source comes first: the path's evidence belongs to the links into a
    topic, so the very first topic of a plan, the one to read first, has none.
    """
    sources = concepts.get(step["concept_id"], {}).get("sources", [])
    places = [*sources, *step.get("evidence", [])]
    if not places:
        return S.PLAN_NO_SOURCE
    where = common.citation(places[0].get("doc", ""), places[0].get("page", ""))
    return S.PLAN_READ.format(where=where)


def other_topic_button(*, primary: bool) -> None:
    if ui.action_button(S.PLAN_OTHER_TOPIC, icon="🔍", primary=primary, key="plan_other_topic"):
        st.session_state.quiz_picking = True
        st.switch_page(ui.PAGES["quiz"].path)


def render_personalized_graph() -> None:
    # Build personalized study path starting from where the student needs to begin
    # (next_up / start topic) through to their target goal topic
    display_nodes = list(plan_order) if plan_order else [target]
    full_order = api.prerequisite_order(graph_data, target)

    # If an immediate prerequisite before next_up is known, include it as a foundation checkpoint
    if next_up and next_up in display_nodes and next_up in full_order:
        full_idx = full_order.index(next_up)
        if full_idx > 0:
            prev_cid = full_order[full_idx - 1]
            if prev_cid not in display_nodes and api.is_mastered(mastery.get(prev_cid, 0.5)):
                display_nodes.insert(0, prev_cid)

    path_nodes = set(display_nodes)
    path_edges = [e for e in accepted if e["source"] in path_nodes and e["target"] in path_nodes]

    try:
        import streamlit.components.v1 as components
        from pyvis.network import Network
    except ImportError:
        return

    net = Network(
        height="320px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#1F1B3D",
        cdn_resources="in_line",
    )

    for c in display_nodes:
        c_name = name(c)
        is_known = api.is_mastered(mastery.get(c, 0.5))
        is_start = (c == next_up) or (next_up is None and c == target)
        is_target = c == target

        if is_start:
            label = f"👉 {c_name}\n★ START HERE ★"
            bg_color = "#FEF3C7"
            border_color = "#D97706"
            border_w = 3.5
            title = f"{c_name}: Your starting point to study"
        elif is_known:
            label = f"✓ {c_name}\n(Known)"
            bg_color = "#D1FAE5"
            border_color = "#059669"
            border_w = 2.0
            title = f"{c_name}: Known from quick check"
        elif is_target:
            label = f"🎯 {c_name}\n(Goal Topic)"
            bg_color = "#E0E7FF"
            border_color = "#4338CA"
            border_w = 2.5
            title = f"{c_name}: Your study goal"
        else:
            label = f"⏳ {c_name}\n(Next Step)"
            bg_color = "#F3F4F6"
            border_color = "#6B7280"
            border_w = 1.5
            title = f"{c_name}: Follows earlier topics"

        net.add_node(
            c,
            label=label,
            title=title,
            shape="box",
            margin=10,
            borderWidth=border_w,
            borderWidthSelected=4.0,
            color={
                "background": bg_color,
                "border": border_color,
                "highlight": {"background": bg_color, "border": "#1F1B3D"},
            },
            font={"size": 13, "color": "#1F1B3D", "face": "system-ui, sans-serif"},
            shadow={"enabled": True, "color": "rgba(0,0,0,0.08)", "size": 5, "x": 1, "y": 2},
        )

    for edge in path_edges:
        is_active = edge["source"] == next_up or edge["target"] == next_up
        net.add_edge(
            edge["source"],
            edge["target"],
            arrows={"to": {"enabled": True, "scaleFactor": 0.9}},
            color="#4338CA" if is_active else "#6B7280",
            width=2.5 if is_active else 1.8,
            dashes=edge.get("strength", "hard") != "hard",
        )

    net.set_options("""
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "LR",
          "sortMethod": "directed",
          "nodeSpacing": 200,
          "levelSeparation": 180
        }
      },
      "physics": {
        "enabled": false
      },
      "interaction": {
        "dragNodes": true,
        "zoomView": true,
        "hover": true
      }
    }
    """)
    components.html(net.generate_html(), height=340)


if not steps:
    header()
    st.success(S.PLAN_ALL_KNOWN.format(topic=name(target)))
    with st.container(border=True):
        st.markdown("### Your Learning Path Map")
        st.caption(f"All foundational topics for **{name(target)}** are mastered.")
        render_personalized_graph()
    other_topic_button(primary=True)
    st.stop()

# The first thing on screen, above the page title, so a phone shows it without scrolling.
step_by_id = {step["concept_id"]: step for step in steps}
if next_up:
    with st.container(border=True):
        st.markdown(S.PLAN_NEXT_TITLE.format(topic=name(next_up)))
        st.markdown(where_to_read(step_by_id[next_up]))
else:
    st.success(S.PLAN_ALL_DONE.format(topic=name(target)))

header()
st.markdown(S.PLAN_FOR.format(topic=name(target)))
if limit_stopped:
    st.info(S.PLAN_LIMIT_NOTE.format(n=api.MAX_QUESTIONS_PER_TOPIC), icon="ℹ️")

with st.container(border=True):
    st.markdown("### Your Learning Path Map")
    if next_up:
        st.caption(f"Based on your check answers, start studying at **{name(next_up)}**.")
    else:
        st.caption(f"You are ready to study **{name(target)}**.")
    render_personalized_graph()

STATUS = {"done": S.PLAN_STATUS_DONE, "next": S.PLAN_STATUS_NEXT, "later": S.PLAN_STATUS_LATER}
for number, step in enumerate(steps, start=1):
    concept_id = step["concept_id"]
    status = "done" if concept_id in done else "next" if concept_id == next_up else "later"
    with st.container(border=True):
        title = S.PLAN_STEP.format(number=number, topic=name(concept_id))
        st.markdown(f"**{title}** · {STATUS[status]}")
        st.write(step["why"])
        st.caption(where_to_read(step))
        if status == "next" and ui.action_button(
            S.PLAN_MARK_DONE, icon="✅", key=f"done_{concept_id}"
        ):
            done.append(concept_id)
            st.rerun()

if (
    more_questions
    and not limit_stopped
    and ui.action_button(S.PLAN_MORE_QUESTIONS, icon="✏️", primary=False, key="plan_more")
):
    st.session_state.quiz_picking = False
    st.switch_page(ui.PAGES["quiz"].path)
other_topic_button(primary=False)
ui.action_button(
    "Continue to Next Step: Topic Map", page="map", icon="🔗", primary=True, key="plan_to_map"
)
