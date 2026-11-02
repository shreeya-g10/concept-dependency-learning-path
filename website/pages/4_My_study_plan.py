"""Step 4: the personal study plan, from the answers given in step 3.

Reads the answers from session state (pages/3_Quick_check.py writes them) and the path from
cdlp/learning_path/api.py. The reasons are worded here, from the graph: the path's own `why`
text carries raw concept ids.
"""

from __future__ import annotations

import common
import pandas as pd
import streamlit as st
import strings as S
import ui

from cdlp.learning_path import api

ui.page_header(S.PLAN_TITLE, S.PLAN_INTRO, step=4, source_file="validated_graph.json")

course = common.get_active_course()
names = common.concept_names()
graph_data = common.load("validated_graph.json")
target = st.session_state.get("study_target")

if (
    not st.session_state.get("quiz_answers")
    or st.session_state.get("quiz_course") != course
    or target not in names
):
    ui.empty_state(S.PLAN_EMPTY, S.PLAN_EMPTY_NEXT, action=S.PLAN_TO_QUIZ, page="quiz", icon="✏️")
    st.stop()

mastery = st.session_state.quiz_mastery


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def why(concept_id: str, in_plan: set[str]) -> str:
    if concept_id == target:
        return S.PLAN_WHY_TARGET
    next_topics = [
        name(e["target"])
        for e in graph_data.get("edges", [])
        if e.get("decision") == "ACCEPT" and e["source"] == concept_id and e["target"] in in_plan
    ]
    return S.PLAN_WHY_BEFORE.format(topics=", ".join(next_topics or [name(target)]))


st.markdown(S.PLAN_FOR.format(topic=name(target)))
steps = api.personalized_path(graph_data, mastery, target)
if not steps:
    st.balloons()
    st.success(S.PLAN_ALL_KNOWN)

in_plan = {step["concept_id"] for step in steps}
for number, step in enumerate(steps, start=1):
    concept_id = step["concept_id"]
    with st.expander(
        S.PLAN_STEP.format(number=number, topic=name(concept_id)), expanded=number == 1
    ):
        st.write(why(concept_id, in_plan))
        if concept_id in mastery:
            st.caption(S.PLAN_STEP_KNOWN.format(percent=round(mastery[concept_id] * 100)))
        else:
            st.caption(S.PLAN_STEP_UNCHECKED)
        places = list(
            dict.fromkeys(
                common.citation(ev.get("doc", ""), ev.get("page", ""))
                for ev in step.get("evidence", [])
            )
        )
        st.caption(f"{S.PLAN_WHERE}: " + " · ".join(places) if places else S.PLAN_NO_SOURCE)

ui.action_button(S.PLAN_MORE_QUESTIONS, page="quiz", icon="✏️")

st.markdown(S.PLAN_CHART_TITLE)
st.caption(S.PLAN_CHART_NOTE)
order = api.prerequisite_order(graph_data, target)
chart = pd.DataFrame(
    {
        S.PLAN_CHART_TOPIC: [name(c) for c in order],
        S.PLAN_CHART_KNOW: [mastery.get(c, 0.5) for c in order],
    }
)
st.bar_chart(chart.set_index(S.PLAN_CHART_TOPIC))
