
"""Owner: Shrestha. Adaptive quiz and personalized learning path."""

import streamlit as st
import pandas as pd
import networkx as nx

from common import load, concept_names, page_header
from cdlp.learning_path.graph import load_graph


page_header("My Learning Path", "Shrestha", "quiz_items.json")

# Load project data
names = concept_names()
graph_data = load("validated_graph.json")
quiz_data = load("quiz_items.json")
graph = load_graph(graph_data)

# Read quiz questions
if isinstance(quiz_data, list):
    quiz_items = quiz_data
else:
    quiz_items = quiz_data.get(
        "items",
        quiz_data.get("questions", [])
    )

# Group questions by concept
questions_by_concept = {}

for index, item in enumerate(quiz_items):
    concept_id = item.get("concept_id")

    if concept_id not in graph:
        continue

    question = dict(item)
    question.setdefault("id", f"question_{index}")

    questions_by_concept.setdefault(
        concept_id, []
    ).append(question)


def get_order(target):
    """Get prerequisites followed by the learning target."""
    required = nx.ancestors(graph, target) | {target}
    subgraph = graph.subgraph(required)

    return list(nx.topological_sort(subgraph))


def initial_mastery():
    """Start every concept at 50% mastery."""
    return {
        concept: 0.5
        for concept in graph.nodes
    }


def update_mastery(mastery, concept, correct):
    """Update mastery after a student answers."""
    updated = dict(mastery)

    if correct:
        updated[concept] = 0.9

        for prerequisite in nx.ancestors(graph, concept):
            updated[prerequisite] = max(
                updated.get(prerequisite, 0.5),
                0.8
            )

    else:
        updated[concept] = 0.1

        for prerequisite in nx.ancestors(graph, concept):
            updated.setdefault(prerequisite, 0.5)

    return updated


def next_question(target, mastery, asked):
    """Select an unused question from an uncertain concept."""
    order = get_order(target)
    candidates = []

    for concept in order:
        score = mastery.get(concept, 0.5)

        if not (0.2 <= score <= 0.8):
            continue

        unused = [
            item
            for item in questions_by_concept.get(concept, [])
            if item["id"] not in asked
        ]

        if unused:
            candidates.append(unused[0])

    if not candidates:
        return None

    # Ask the middle uncertain concept
    return candidates[len(candidates) // 2]


def fallback_question(target, asked):
    """Find any unused question in the target's prerequisite chain."""
    for concept in get_order(target):
        for item in questions_by_concept.get(concept, []):
            if item["id"] not in asked:
                return item

    return None


def extract_options(question):
    """Support string and dictionary answer options."""
    options = question.get(
        "options",
        question.get("choices", [])
    )

    if isinstance(options, dict):
        return [
            (key, str(value))
            for key, value in options.items()
        ]

    if isinstance(options, list):
        result = []

        for index, option in enumerate(options):
            if isinstance(option, dict):
                value = option.get(
                    "value",
                    option.get("id", index)
                )
                label = option.get(
                    "label",
                    option.get("text", str(value))
                )
            else:
                value = option
                label = str(option)

            result.append((value, str(label)))

        return result

    return []


def is_correct(question, selected_answer):
    """Compare the selected answer with the quiz answer key."""
    correct_answer = question.get(
        "correct_answer",
        question.get(
            "answer",
            question.get("correct")
        )
    )

    if correct_answer is None:
        return False

    if isinstance(correct_answer, list):
        return str(selected_answer) in {
            str(value) for value in correct_answer
        }

    return str(selected_answer) == str(correct_answer)


def reset_diagnosis():
    """Clear the current student diagnosis."""
    st.session_state.cdlp_mastery = initial_mastery()
    st.session_state.cdlp_asked = []
    st.session_state.cdlp_answers = []


# --------------------------------------------------
# PAGE INTERFACE
# --------------------------------------------------

st.title("Personalized Learning Path")

st.write(
    "Choose a learning goal, answer adaptive quiz questions, "
    "and receive a personalized learning path."
)

concept_ids = sorted(
    graph.nodes,
    key=lambda concept: names.get(concept, concept)
)

if not concept_ids:
    st.error("No concepts found in validated_graph.json.")
    st.stop()

target = st.selectbox(
    "What would you like to learn?",
    concept_ids,
    format_func=lambda concept: names.get(concept, concept)
)

max_questions = st.slider(
    "Maximum quiz questions",
    min_value=1,
    max_value=10,
    value=7
)

# Initialize session
if "cdlp_mastery" not in st.session_state:
    reset_diagnosis()

if st.session_state.get("cdlp_target") != target:
    reset_diagnosis()
    st.session_state.cdlp_target = target

if st.button("Restart Diagnosis"):
    reset_diagnosis()
    st.rerun()

mastery = st.session_state.cdlp_mastery
asked = st.session_state.cdlp_asked
answers = st.session_state.cdlp_answers

# --------------------------------------------------
# QUIZ
# --------------------------------------------------

st.subheader("Adaptive Diagnosis")

st.write(
    f"**Questions answered: {len(answers)} / {max_questions}**"
)

st.progress(
    min(len(answers) / max_questions, 1.0)
)

question = None

if len(answers) < max_questions:
    question = next_question(target, mastery, asked)

    # Fallback for the first question
    if question is None and not answers:
        question = fallback_question(target, asked)

if question is not None:

    concept = question["concept_id"]

    st.info(
        f"Current concept: {names.get(concept, concept)}"
    )

    st.markdown(
        f"### {question.get('question', 'Question')}"
    )

    options = extract_options(question)

    if options:
        with st.form(
            key=f"quiz_{question['id']}"
        ):
            selected = st.radio(
                "Select your answer:",
                options,
                format_func=lambda option: option[1],
                index=None
            )

            submitted = st.form_submit_button(
                "Submit Answer"
            )

        if submitted:
            if selected is None:
                st.warning("Please select an answer.")

            else:
                selected_answer = selected[0]
                correct = is_correct(
                    question,
                    selected_answer
                )

                st.session_state.cdlp_mastery = update_mastery(
                    mastery,
                    concept,
                    correct
                )

                st.session_state.cdlp_asked.append(
                    question["id"]
                )

                st.session_state.cdlp_answers.append(
                    {
                        "question_id": question["id"],
                        "concept_id": concept,
                        "selected_answer": selected_answer,
                        "correct": correct
                    }
                )

                st.rerun()

    else:
        st.error(
            "This question has no answer options."
        )

elif not answers:
    st.warning(
        "No matching quiz questions were found. "
        "Check that quiz_items.json contains questions "
        "for concepts in validated_graph.json."
    )

else:
    st.success("Diagnosis Complete!")

# --------------------------------------------------
# PERSONALIZED LEARNING PATH
# --------------------------------------------------

if answers and question is None:

    st.divider()
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
            "Study these concepts in the recommended order:"
        )

        for index, concept in enumerate(
            learning_path,
            start=1
        ):
            with st.expander(
                f"Step {index}: "
                f"{names.get(concept, concept)}",
                expanded=(index == 1)
            ):
                st.write(
                    "**Estimated mastery:**",
                    f"{mastery.get(concept, 0.5):.0%}"
                )

                prerequisites = list(
                    graph.predecessors(concept)
                )

                if prerequisites:
                    st.write("**Direct prerequisites:**")

                    for prerequisite in prerequisites:
                        st.write(
                            "-",
                            names.get(
                                prerequisite,
                                prerequisite
                            )
                        )

                st.write(
                    "**Why learn this?**"
                )

                st.write(
                    "This concept is part of the "
                    "prerequisite chain for your target."
                )

# --------------------------------------------------
# MASTERY VISUALIZATION
# --------------------------------------------------

st.divider()
st.subheader("Estimated Concept Mastery")

order = get_order(target)

chart_data = pd.DataFrame(
    {
        "Concept": [
            names.get(concept, concept)
            for concept in order
        ],
        "Mastery": [
            mastery.get(concept, 0.5)
            for concept in order
        ]
    }
)

st.bar_chart(
    chart_data.set_index("Concept")
)

# --------------------------------------------------
# QUIZ SUMMARY
# --------------------------------------------------

if answers:

    st.divider()
    st.subheader("Quiz Summary")

    correct_count = sum(
        item["correct"]
        for item in answers
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Questions Answered",
            len(answers)
        )

    with col2:
        st.metric(
            "Correct Answers",
            f"{correct_count}/{len(answers)}"
        )

    with st.expander("View Your Answers"):
        for item in answers:
            concept_name = names.get(
                item["concept_id"],
                item["concept_id"]
            )

            status = (
                "Correct"
                if item["correct"]
                else "Incorrect"
            )

            st.write(
                f"**{concept_name}:** {status}"
            )
