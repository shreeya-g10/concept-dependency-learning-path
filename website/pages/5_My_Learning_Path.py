
"""Owner: Shrestha. Adaptive quiz and personalized learning path."""

import streamlit as st
import pandas as pd
import networkx as nx

from common import load, concept_names, page_header
from cdlp.learning_path.graph import load_graph


page_header("My Learning Path", "Shrestha", "quiz_items.json")

names = concept_names()
graph_data = load("validated_graph.json")
quiz_data = load("quiz_items.json")
graph = load_graph(graph_data)

# Support quiz data stored as a list or dictionary
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
    """Return prerequisites followed by target."""
    required = nx.ancestors(graph, target) | {target}
    subgraph = graph.subgraph(required)
    return list(nx.topological_sort(subgraph))


def update_mastery(mastery, concept, correct):
    """Update mastery after an answer."""
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
    """Select the middle uncertain concept with an unused question."""
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
            candidates.append((concept, unused[0]))

    if not candidates:
        return None

    return candidates[len(candidates) // 2][1]


def reset_diagnosis():
    st.session_state.cdlp_mastery = {
        concept: 0.5 for concept in graph.nodes
    }
    st.session_state.cdlp_asked = []
    st.session_state.cdlp_answers = []
    st.session_state.cdlp_target = None


def extract_options(question):
    """Read common multiple-choice option formats."""
    options = question.get(
        "options",
        question.get("choices", [])
    )

    if isinstance(options, dict):
        return list(options.items())

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


def is_correct(question, answer):
    """Compare the selected answer with the answer key."""
    correct = question.get(
        "correct_answer",
        question.get(
            "answer",
            question.get("correct", None)
        )
    )

    if correct is None:
        return False

    if isinstance(correct, list):
        return str(answer) in {
            str(value) for value in correct
        }

    return str(answer) == str(correct)


st.title("Personalized Learning Path")

st.write(
    "Choose your learning goal, answer a short adaptive quiz, "
    "and receive a learning path based on your estimated mastery."
)

concept_ids = sorted(
    graph.nodes,
    key=lambda concept: names.get(concept, concept)
)

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

if "cdlp_mastery" not in st.session_state:
    reset_diagnosis()

if st.session_state.cdlp_target != target:
    reset_diagnosis()
    st.session_state.cdlp_target = target

if st.button("Restart diagnosis"):
    reset_diagnosis()
    st.session_state.cdlp_target = target
    st.rerun()

mastery = st.session_state.cdlp_mastery
asked = st.session_state.cdlp_asked
answers = st.session_state.cdlp_answers

st.write(
    f"**{len(answers)} of {max_questions} questions**"
)

st.progress(
    min(len(answers) / max_questions, 1.0)
)

question = None

if len(answers) < max_questions:
    question = next_question(target, mastery, asked)

if question is not None:
    st.subheader("Adaptive Diagnosis")

    concept = question["concept_id"]

    st.caption(
        f"Concept: {names.get(concept, concept)}"
    )

    st.write(
        question.get(
            "question",
            question.get(
                "text",
                question.get("prompt", "Question")
            )
        )
    )

    options = extract_options(question)

    if options:
        with st.form(
            key=f"quiz_{question['id']}"
        ):
            selected = st.radio(
                "Choose your answer",
                options,
                format_func=lambda option: option[1],
                index=None
            )

            submitted = st.form_submit_button(
                "Submit answer"
            )

        if submitted:
            if selected is None:
                st.warning("Please select an answer.")
            else:
                answer = selected[0]
                correct = is_correct(question, answer)

                st.session_state.cdlp_mastery = update_mastery(
                    mastery, concept, correct
                )

                st.session_state.cdlp_asked.append(
                    question["id"]
                )

                st.session_state.cdlp_answers.append(
                    {
                        "concept_id": concept,
                        "question_id": question["id"],
                        "correct": correct
                    }
                )

                st.rerun()
    else:
        st.warning(
            "This question has no supported answer options."
        )

elif len(answers) == 0:
    st.warning(
        "No matching quiz questions were found for this "
        "learning goal. Check quiz_items.json and the "
        "concept_id values."
    )

else:
    st.success(
        "Diagnosis complete. Here is your personalized path."
    )


# Learning path appears only after answering questions
if len(answers) > 0 and question is None:

    st.subheader("Your Personalized Learning Path")

    order = get_order(target)

    path = [
        concept
        for concept in order
        if mastery.get(concept, 0.5) <= 0.8
    ]

    if not path:
        st.success(
            "You have demonstrated mastery of all "
            "required concepts!"
        )

    for index, concept in enumerate(path, start=1):
        with st.expander(
            f"{index}. {names.get(concept, concept)}",
            expanded=(index == 1)
        ):
            prerequisites = list(
                graph.predecessors(concept)
            )

            if prerequisites:
                st.write(
                    "**Direct prerequisites:**",
                    ", ".join(
                        names.get(item, item)
                        for item in prerequisites
                    )
                )

            st.write(
                "**Estimated mastery:**",
                f"{mastery.get(concept, 0.5):.0%}"
            )

            st.write(
                "Learn or revise this concept before "
                "moving to the next step."
            )


st.subheader("Estimated Mastery")

chart_data = pd.DataFrame(
    {
        "Concept": [
            names.get(concept, concept)
            for concept in get_order(target)
        ],
        "Mastery": [
            mastery.get(concept, 0.5)
            for concept in get_order(target)
        ]
    }
)

st.bar_chart(
    chart_data.set_index("Concept")
)

if answers:
    st.subheader("Quiz Summary")

    correct_count = sum(
        item["correct"] for item in answers
    )

    st.metric(
        "Correct Answers",
        f"{correct_count}/{len(answers)}"
    )
