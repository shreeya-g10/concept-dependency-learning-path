
"""Owner: Shrestha. Quiz and personalized learning path."""

import streamlit as st
import pandas as pd
import networkx as nx

from common import load, concept_names, page_header
from cdlp.learning_path.graph import load_graph


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

page_header("My Learning Path", "Shrestha", "quiz_items.json")

names = concept_names()
graph_data = load("validated_graph.json")
quiz_data = load("quiz_items.json")
graph = load_graph(graph_data)

if isinstance(quiz_data, list):
    quiz_items = quiz_data
else:
    quiz_items = quiz_data.get("items", quiz_data.get("questions", []))

quiz_items = [
    q for q in quiz_items
    if isinstance(q, dict) and q.get("question")
]

# --------------------------------------------------
# FUNCTIONS
# --------------------------------------------------

def get_order(target):
    required = nx.ancestors(graph, target) | {target}
    return list(nx.topological_sort(graph.subgraph(required)))


def update_mastery(mastery, concept, correct):
    updated = dict(mastery)

    if correct:
        updated[concept] = 0.9

        if concept in graph:
            for prerequisite in nx.ancestors(graph, concept):
                updated[prerequisite] = max(
                    updated.get(prerequisite, 0.5), 0.8
                )
    else:
        updated[concept] = 0.1

    return updated


def reset_quiz():
    st.session_state.cdlp_answers = {}
    st.session_state.cdlp_mastery = {
        concept: 0.5 for concept in graph.nodes
    }
    st.session_state.cdlp_quiz_done = False


def submit_answer(question, selected):
    question_id = question["id"]
    correct_answer = question.get(
        "correct_answer",
        question.get("answer", question.get("correct"))
    )

    is_right = str(selected) == str(correct_answer)

    st.session_state.cdlp_answers[question_id] = {
        "concept_id": question.get("concept_id"),
        "selected": selected,
        "correct": is_right
    }

    concept = question.get("concept_id")

    if concept in graph:
        st.session_state.cdlp_mastery = update_mastery(
            st.session_state.cdlp_mastery,
            concept,
            is_right
        )


# --------------------------------------------------
# PAGE TITLE
# --------------------------------------------------

st.title("Personalized Learning Path")

st.write(
    "Answer the quiz questions below. "
    "Your answers will help generate a personalized "
    "learning path based on your concept mastery."
)

# --------------------------------------------------
# INITIALIZE SESSION
# --------------------------------------------------

if (
    "cdlp_answers" not in st.session_state
    or not isinstance(st.session_state.cdlp_answers, dict)
    or "cdlp_mastery" not in st.session_state
):
    reset_quiz()

# --------------------------------------------------
# SELECT LEARNING GOAL
# --------------------------------------------------

concept_ids = sorted(
    graph.nodes,
    key=lambda concept: names.get(concept, concept)
)

target = st.selectbox(
    "What would you like to learn?",
    concept_ids,
    format_func=lambda concept: names.get(concept, concept)
)

if st.button("Restart Quiz"):
    reset_quiz()
    st.rerun()

# --------------------------------------------------
# QUIZ SECTION - QUESTIONS ALWAYS VISIBLE
# --------------------------------------------------

st.divider()
st.header("Take Quiz")

st.write(f"**Questions loaded: {len(quiz_items)}**")

if not quiz_items:
    st.error(
        "No questions found in quiz_items.json. "
        "Check the quiz data file."
    )
    st.stop()

# Display questions directly from JSON.
# No adaptive filtering hides the questions.

total_questions = len(quiz_items)
answered_count = len(st.session_state.cdlp_answers)

st.write(
    f"**Questions answered: "
    f"{answered_count} / {total_questions}**"
)

st.progress(
    min(answered_count / total_questions, 1.0)
)

for index, question in enumerate(quiz_items, start=1):

    question_id = str(
        question.get("id", f"question_{index}")
    )

    question = dict(question)
    question["id"] = question_id

    concept_id = question.get("concept_id", "")
    concept_name = names.get(concept_id, concept_id)

    st.markdown(f"### Question {index}")

    st.caption(f"Concept: {concept_name}")

    st.write(question["question"])

    options = question.get(
        "options",
        question.get("choices", [])
    )

    if isinstance(options, dict):
        options = list(options.values())

    if not options:
        st.warning("No answer options available.")
        continue

    previous = st.session_state.cdlp_answers.get(
        question_id
    )

    if previous is not None:

        if previous["correct"]:
            st.success("Correct answer!")
        else:
            st.error("Incorrect answer.")

        st.write(
            "**Your answer:**",
            previous["selected"]
        )

    else:

        with st.form(key=f"form_{question_id}"):

            selected = st.radio(
                "Choose your answer:",
                options,
                index=None,
                key=f"option_{question_id}"
            )

            submitted = st.form_submit_button(
                "Submit Answer"
            )

        if submitted:

            if selected is None:
                st.warning("Please select an answer.")

            else:
                submit_answer(question, selected)
                st.rerun()

    st.divider()


# --------------------------------------------------
# QUIZ RESULTS
# --------------------------------------------------

answers = st.session_state.cdlp_answers
mastery = st.session_state.cdlp_mastery

if answers:

    st.header("Quiz Results")

    correct_count = sum(
        1 for item in answers.values()
        if item["correct"]
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Answered",
            len(answers)
        )

    with col2:
        st.metric(
            "Correct",
            correct_count
        )

    with col3:
        st.metric(
            "Accuracy",
            f"{correct_count / len(answers) * 100:.0f}%"
        )


# --------------------------------------------------
# PERSONALIZED LEARNING PATH
# --------------------------------------------------

if len(answers) == total_questions:

    st.success("Quiz Completed!")

    st.header("Your Personalized Learning Path")

    order = get_order(target)

    learning_path = [
        concept
        for concept in order
        if mastery.get(concept, 0.5) <= 0.8
    ]

    if not learning_path:

        st.success(
            "You have demonstrated mastery of all "
            "required concepts!"
        )

    else:

        st.write(
            "Based on your answers, study these "
            "concepts in the following order:"
        )

        for index, concept in enumerate(
            learning_path, start=1
        ):

            with st.expander(
                f"Step {index}: "
                f"{names.get(concept, concept)}",
                expanded=(index == 1)
            ):

                st.write(
                    "**Estimated Mastery:**",
                    f"{mastery.get(concept, 0.5):.0%}"
                )

                prerequisites = list(
                    graph.predecessors(concept)
                )

                if prerequisites:

                    st.write("**Prerequisites:**")

                    for prerequisite in prerequisites:
                        st.write(
                            "-",
                            names.get(
                                prerequisite,
                                prerequisite
                            )
                        )

                st.write(
                    "Study or revise this concept "
                    "before proceeding to the next."
                )


# --------------------------------------------------
# MASTERY CHART
# --------------------------------------------------

st.divider()
st.header("Estimated Concept Mastery")

order = get_order(target)

chart_data = pd.DataFrame({
    "Concept": [
        names.get(concept, concept)
        for concept in order
    ],
    "Mastery": [
        mastery.get(concept, 0.5)
        for concept in order
    ]
})

st.bar_chart(
    chart_data.set_index("Concept")
)
