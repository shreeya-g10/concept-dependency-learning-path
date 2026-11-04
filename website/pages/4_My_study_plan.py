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
import study_path
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

plan = study_path.plan_state(course, graph_data, common.load("quiz_items.json"), target)
ladder = plan["ladder"]
more_questions = plan["more_questions"]
limit_stopped = plan["limit_stopped"]
steps = plan["steps"]
done = plan["done"]
next_up = plan["next_up"]


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


def map_button() -> None:
    """The picture of this path is on the topic map. A topic with no links has no map to open."""
    has_links = any(target in (e["source"], e["target"]) for e in accepted)
    if has_links and ui.action_button(
        S.PLAN_SEE_ON_MAP, icon="🗺️", primary=False, key="plan_to_map"
    ):
        st.session_state.map_view_mode = S.MAP_VIEW_PATH
        st.switch_page(ui.PAGES["map"].path)


if not steps:
    header()
    st.success(S.PLAN_ALL_KNOWN.format(topic=name(target)))
    other_topic_button(primary=True)
    map_button()
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


result_of = plan["rows"]
result_words = study_path.result_words
if ladder:
    first = ladder["first_to_study"]
    if first:
        known = [name(c) for c in ladder["known"]]
        known_words = (
            ", ".join(known[:-1]) + S.PLAN_AND + known[-1] if len(known) > 1 else "".join(known)
        )
        line = S.PLAN_KNOWN_START if known else S.PLAN_JUST_START
        st.markdown(line.format(known=known_words, topic=name(first)))
    for stop in ladder["stops"]:
        if stop["not_checked"]:
            note = (
                S.PLAN_LADDER_STOPPED if stop["stops_everything_later"] else S.PLAN_LADDER_SKIPPED
            )
            st.info(note.format(topic=name(stop["concept_id"])), icon="ℹ️")
        if stop["still_asked"]:
            asked_names = S.PLAN_AND.join(name(c) for c in stop["still_asked"])
            st.info(
                S.PLAN_LADDER_STILL_ASKED.format(
                    topics=asked_names, topic=name(stop["concept_id"])
                ),
                icon="ℹ️",
            )
    for concept_id in ladder["known"]:
        st.caption(
            S.PLAN_RESULT_LINE.format(
                result=result_words(result_of[concept_id]), topic=name(concept_id)
            )
        )

for number, step in enumerate(steps, start=1):
    concept_id = step["concept_id"]
    status = study_path.status_of(plan, concept_id)
    with st.container(border=True):
        title = S.PLAN_STEP.format(number=number, topic=name(concept_id))
        st.markdown(f"**{title}** · {study_path.STATUS[status]}")
        if concept_id in result_of:
            st.markdown(result_words(result_of[concept_id]))
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
map_button()
