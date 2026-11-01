"""Owner: Vaidehi (inherited from Shrestha). Adaptive quiz and personalized learning path.

Interacts with the learning path module exclusively via cdlp/learning_path/api.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from common import concept_names, load, page_header, render_sidebar

from cdlp.learning_path import api

page_header("My Learning Path", "Vaidehi", "quiz_items.json")
render_sidebar()

names = concept_names()
graph_data = load("validated_graph.json")
quiz_data = load("quiz_items.json")

# Extract questions list
if isinstance(quiz_data, list):
    quiz_items = quiz_data
else:
    quiz_items = quiz_data.get("items", quiz_data.get("questions", []))

valid_items = [
    q for q in quiz_items if isinstance(q, dict) and (q.get("question") or q.get("item_id"))
]


def reset_quiz():
    st.session_state.quiz_mastery = {}
    st.session_state.quiz_asked = []
    st.session_state.quiz_answers = []
    st.session_state.quiz_done = False


# Initialize session state
if "quiz_mastery" not in st.session_state:
    reset_quiz()

st.title("🎯 Personalized Learning Path")
st.write(
    "Select your target concept. Our graph-guided adaptive quiz will test key prerequisite "
    "concepts using binary chain diagnosis, identifying your exact knowledge gaps to recommend "
    "a personalized learning path."
)

concept_ids = list(names.keys())
if not concept_ids:
    st.error("No concepts found in graph.")
    st.stop()

col_target, col_reset = st.columns([3, 1])
with col_target:
    default_idx = concept_ids.index("avl_tree") if "avl_tree" in concept_ids else 0
    target = st.selectbox(
        "What would you like to master?",
        concept_ids,
        index=default_idx,
        format_func=lambda c: names.get(c, c),
    )

with col_reset:
    st.write("")
    st.write("")
    if st.button("🔄 Restart Quiz"):
        reset_quiz()
        st.rerun()

st.divider()

# Adaptive Quiz Execution
st.subheader("📝 Adaptive Diagnostic Quiz")

current_mastery = dict(st.session_state.quiz_mastery)
asked_ids = list(st.session_state.quiz_asked)
answers = list(st.session_state.quiz_answers)

# Query next question from api.py
question = api.next_question(
    graph_data,
    valid_items,
    {**current_mastery, "__asked__": asked_ids},
    target,
)

if question is not None and not st.session_state.get("quiz_done", False):
    concept_id = question.get("concept_id", "")
    concept_name = names.get(concept_id, concept_id)
    q_id = question.get("id", question.get("item_id", f"q_{len(asked_ids)}"))

    st.info(f"**Diagnostic Question #{len(answers) + 1}** · Testing concept: **{concept_name}**")
    st.markdown(f"### {question.get('question', '')}")

    raw_options = question.get("options", question.get("choices", []))
    if isinstance(raw_options, dict):
        options = list(raw_options.values())
    elif isinstance(raw_options, list):
        options = [
            opt["text"] if isinstance(opt, dict) and "text" in opt else str(opt)
            for opt in raw_options
        ]
    else:
        options = []

    if options:
        with st.form(key=f"form_{q_id}"):
            choice = st.radio("Choose your answer:", options, index=None)
            submitted = st.form_submit_button("Submit Answer")

            if submitted:
                if choice is None:
                    st.warning("Please select an answer before submitting.")
                else:
                    correct_answer = question.get(
                        "answer", question.get("correct_answer", question.get("correct"))
                    )
                    is_correct = str(choice).strip().lower() == str(correct_answer).strip().lower()

                    root_cause_info = None
                    if not is_correct:
                        try:
                            from cdlp.root_cause import api as root_cause_api

                            root_cause_info = root_cause_api.trace(
                                graph_data, question, str(choice), current_mastery
                            )
                        except Exception:
                            root_cause_info = None

                    # Update mastery through api.py
                    new_mastery = api.update_mastery(
                        graph_data, current_mastery, concept_id, is_correct
                    )
                    st.session_state.quiz_mastery = new_mastery
                    st.session_state.quiz_asked.append(q_id)
                    st.session_state.quiz_answers.append(
                        {
                            "item_id": q_id,
                            "concept_id": concept_id,
                            "selected": choice,
                            "correct": is_correct,
                            "root_cause": (
                                root_cause_info.get("explanation") if root_cause_info else None
                            ),
                        }
                    )
                    st.rerun()
    else:
        st.warning("No choices available for this question.")
else:
    st.session_state.quiz_done = True
    st.success("✅ Adaptive Diagnosis Complete!")

# --------------------------------------------------
# RESULTS & PERSONALIZED PATH
# --------------------------------------------------
if answers:
    st.divider()
    correct_count = sum(1 for a in answers if a["correct"])
    acc = (correct_count / len(answers)) * 100

    col1, col2, col3 = st.columns(3)
    col1.metric("Questions Asked", len(answers))
    col2.metric("Correct Answers", f"{correct_count} / {len(answers)}")
    col3.metric("Diagnosis Accuracy", f"{acc:.0f}%")

    with st.expander("🔍 View Question Responses"):
        for a in answers:
            c_name = names.get(a["concept_id"], a["concept_id"])
            status = "✅ Correct" if a["correct"] else "❌ Incorrect"
            st.markdown(f"- **{c_name}**: {status} (Answered: `{a['selected']}`)")
            if a.get("root_cause"):
                st.caption(f"  🔍 Root-cause diagnosis: {a['root_cause']}")

    # Generate Personalized Path via api.py
    st.divider()
    st.header(f"🛤️ Your Learning Path to {names.get(target, target)}")

    path_steps = api.personalized_path(graph_data, current_mastery, target)

    if not path_steps:
        st.balloons()
        st.success("🎉 You have demonstrated mastery of all required prerequisites!")
    else:
        st.write(
            "Based on your diagnosis, focus on these concepts in recommended dependency order:"
        )
        for idx, step in enumerate(path_steps, start=1):
            c_id = step["concept_id"]
            c_name = names.get(c_id, c_id)
            c_mastery = current_mastery.get(c_id, 0.5)

            with st.expander(
                f"Step {idx}: {c_name} (Mastery: {c_mastery:.0%})", expanded=(idx == 1)
            ):
                st.write(f"**Rationale:** {step['why']}")
                ev_list = step.get("evidence", [])
                if ev_list:
                    citations = [f"📄 {ev.get('doc', '')} p.{ev.get('page', '')}" for ev in ev_list]
                    st.caption("Lecture Citations: " + " · ".join(citations))
                else:
                    st.caption("Course lectures cover this prerequisite in introductory chapters.")

    # Mastery Bar Chart
    st.divider()
    st.subheader("📊 Estimated Knowledge State")
    order = api.prerequisite_order(graph_data, target)
    chart_df = pd.DataFrame(
        {
            "Concept": [names.get(c, c) for c in order],
            "Mastery": [current_mastery.get(c, 0.5) for c in order],
        }
    )
    st.bar_chart(chart_df.set_index("Concept"))
