"""Step 4: the personal study plan, from the answers given in step 3.

Reads the answers from session state (pages/3_Quick_check.py writes them) and the path from
cdlp/learning_path/api.py. The reasons are worded here, from the graph: the path's own `why`
text carries raw concept ids and reads backwards.

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
steps = api.personalized_path(graph_data, mastery, target)
plan_order = [step["concept_id"] for step in steps]
done = st.session_state.setdefault("plan_done", {}).setdefault(course, [])
next_up = next((c for c in plan_order if c not in done), None)


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def why(concept_id: str) -> str:
    """One short sentence, about the nearest later topic in this student's plan."""
    if concept_id == target:
        return S.PLAN_WHY_TARGET
    later = plan_order[plan_order.index(concept_id) + 1 :]
    links = {e["target"]: e for e in accepted if e["source"] == concept_id}
    nearest = next((c for c in later if c in links), None)
    if nearest is None:  # the topic between them is already known: it still leads to the target
        return S.PLAN_WHY_LEADS.format(topic=name(target))
    needed = links[nearest].get("strength", "hard") == "hard"
    return (S.PLAN_WHY_NEED if needed else S.PLAN_WHY_HELPS).format(topic=name(nearest))


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


if not steps:
    header()
    st.success(S.PLAN_ALL_KNOWN.format(topic=name(target)))
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

STATUS = {"done": S.PLAN_STATUS_DONE, "next": S.PLAN_STATUS_NEXT, "later": S.PLAN_STATUS_LATER}
for number, step in enumerate(steps, start=1):
    concept_id = step["concept_id"]
    status = "done" if concept_id in done else "next" if concept_id == next_up else "later"
    with st.container(border=True):
        title = S.PLAN_STEP.format(number=number, topic=name(concept_id))
        st.markdown(f"**{title}** · {STATUS[status]}")
        st.write(why(concept_id))
        st.caption(where_to_read(step))
        if status == "next" and ui.action_button(
            S.PLAN_MARK_DONE, icon="✅", key=f"done_{concept_id}"
        ):
            done.append(concept_id)
            st.rerun()

more_questions = api.next_question(
    graph_data,
    common.load("quiz_items.json"),
    {**mastery, "__asked__": list(st.session_state.get("quiz_asked", []))},
    target,
)
if more_questions and ui.action_button(
    S.PLAN_MORE_QUESTIONS, icon="✏️", primary=False, key="plan_more"
):
    st.session_state.quiz_picking = False
    st.switch_page(ui.PAGES["quiz"].path)
other_topic_button(primary=next_up is None)
