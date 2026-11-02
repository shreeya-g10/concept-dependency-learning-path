"""Step 3: the adaptive quiz.

Talks to the learning-path module only through cdlp/learning_path/api.py, and to root-cause
tracing only through cdlp/root_cause/api.py. Every answer is logged anonymously to
outputs/<course>/student_answers.json (common.log_answer). Answers stay in session state
for step 4 (pages/4_My_study_plan.py).
"""

from __future__ import annotations

import common
import streamlit as st
import strings as S
import ui

from cdlp.learning_path import api

# Prefixes cdlp/root_cause/tracer.py puts on a non-LLM explanation, and how we label them.
FALLBACK_LABELS = {
    "[fallback: offline estimate]": S.QUIZ_LABEL_OFFLINE,  # LLM unreachable
    "[fallback: nearest prerequisite]": S.QUIZ_LABEL_BASELINE,  # LLM reply unusable
}


def split_explanation(text: str | None) -> tuple[str | None, str | None]:
    """(label, explanation without the prefix); label is None for an LLM explanation."""
    if not text:
        return None, None
    for prefix, label in FALLBACK_LABELS.items():
        if text.startswith(prefix):
            return label, text[len(prefix) :].strip()
    return None, text


def reset_quiz() -> None:
    st.session_state.quiz_mastery = {}
    st.session_state.quiz_asked = []
    st.session_state.quiz_answers = []
    st.session_state.quiz_done = False


ui.page_header(S.QUIZ_TITLE, S.QUIZ_INTRO, step=3, source_file="quiz_items.json")

course = common.get_active_course()
names = common.concept_names()
graph_data = common.load("validated_graph.json")
quiz_data = common.load("quiz_items.json")

quiz_items = (
    quiz_data
    if isinstance(quiz_data, list)
    else quiz_data.get("items", quiz_data.get("questions", []))
)
valid_items = [
    q for q in quiz_items if isinstance(q, dict) and (q.get("question") or q.get("item_id"))
]

# Answers belong to one course: another course starts a new quick check.
if "quiz_mastery" not in st.session_state or st.session_state.get("quiz_course") != course:
    reset_quiz()
    st.session_state.quiz_course = course

concept_ids = list(names)
if not concept_ids:
    ui.empty_state(
        S.QUIZ_NO_TOPICS, S.QUIZ_NO_TOPICS_NEXT, action=S.TOPICS_ADD, page="add", icon="📄"
    )
    st.stop()

remembered = st.session_state.get("study_target")
default = remembered if remembered in names else "avl_tree"
target = st.selectbox(
    S.QUIZ_TARGET,
    concept_ids,
    index=concept_ids.index(default) if default in names else 0,
    format_func=lambda c: names.get(c, c),
)
st.session_state.study_target = target  # a plain key: widget state does not survive other pages

current_mastery = dict(st.session_state.quiz_mastery)
asked_ids = list(st.session_state.quiz_asked)
answers = list(st.session_state.quiz_answers)

question = api.next_question(
    graph_data, valid_items, {**current_mastery, "__asked__": asked_ids}, target
)

if question is not None and not st.session_state.get("quiz_done", False):
    concept_id = question.get("concept_id", "")
    q_id = question.get("id", question.get("item_id", f"q_{len(asked_ids)}"))

    st.info(
        S.QUIZ_QUESTION.format(number=len(answers) + 1, topic=names.get(concept_id, concept_id))
    )
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

    if not options:
        ui.friendly_error(S.QUIZ_NO_OPTIONS, S.QUIZ_NO_OPTIONS_NEXT)
    else:
        with st.form(key=f"form_{q_id}"):
            choice = st.radio(S.QUIZ_CHOOSE, options, index=None)
            submitted = st.form_submit_button(S.QUIZ_SUBMIT, type="primary", width="stretch")

        if submitted and choice is None:
            st.warning(S.QUIZ_PICK_FIRST, icon="ℹ️")
        elif submitted:
            correct_answer = question.get(
                "answer", question.get("correct_answer", question.get("correct"))
            )
            is_correct = str(choice).strip().lower() == str(correct_answer).strip().lower()

            root_cause_info = None
            if not is_correct:
                try:
                    from cdlp.root_cause import api as root_cause_api

                    root_cause_info = root_cause_api.trace(
                        graph_data, question, str(choice), current_mastery, allow_fallback=True
                    )
                except Exception:
                    root_cause_info = None

            try:
                common.log_answer(
                    course,
                    {
                        "student_id": common.session_id(),
                        "item_id": str(q_id),
                        "concept_id": concept_id,
                        "answer": str(choice),
                        "correct": is_correct,
                    },
                )
            except Exception:  # never block the quiz on logging
                st.warning(S.QUIZ_NOT_SAVED, icon="⚠️")

            st.session_state.quiz_mastery = api.update_mastery(
                graph_data, current_mastery, concept_id, is_correct
            )
            st.session_state.quiz_asked.append(q_id)
            st.session_state.quiz_answers.append(
                {
                    "item_id": q_id,
                    "concept_id": concept_id,
                    "selected": choice,
                    "correct": is_correct,
                    "root_cause": root_cause_info.get("explanation") if root_cause_info else None,
                }
            )
            st.rerun()
else:
    st.session_state.quiz_done = True
    st.success(S.QUIZ_DONE if answers else S.QUIZ_NO_QUESTIONS)

if answers:
    right = sum(1 for a in answers if a["correct"])
    st.markdown(S.QUIZ_SCORE.format(right=right, total=len(answers)))
    ui.action_button(
        S.QUIZ_TO_PLAN,
        page="plan",
        icon="🗺️",
        primary=bool(st.session_state.get("quiz_done")),
    )
    with st.expander(S.QUIZ_YOUR_ANSWERS):
        for a in answers:
            status = S.QUIZ_RIGHT if a["correct"] else S.QUIZ_WRONG
            topic = names.get(a["concept_id"], a["concept_id"])
            st.markdown(
                S.QUIZ_ANSWER_LINE.format(topic=topic, status=status, selected=a["selected"])
            )
            label, why = split_explanation(a.get("root_cause"))
            if why and label:
                st.caption(S.QUIZ_WHY_GUESS.format(label=label, why=why))
            elif why:
                st.caption(S.QUIZ_WHY_AI.format(why=why))
    if ui.action_button(S.QUIZ_RESTART, icon="🔄", primary=False, key="restart"):
        reset_quiz()
        st.rerun()
