"""Step 3: the adaptive quiz, one question per screen.

Talks to the learning-path module only through cdlp/learning_path/api.py, and to root-cause
tracing only through cdlp/root_cause/api.py. Every answer is logged anonymously to
outputs/<course>/student_answers.json (common.log_answer). Answers stay in session state
for step 4 (pages/4_My_study_plan.py), which this page opens by itself when it runs out of
questions.

The screens: pick a topic -> question -> (after a wrong answer) a kind message -> question ...
The number of questions depends on the answers, so no total is ever shown.
"""

from __future__ import annotations

import re

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
NO_EXPLANATION = "(no explanation given)"  # what the tracer says when the LLM gave none


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
    st.session_state.quiz_picking = True  # on the pick-a-topic screen
    st.session_state.quiz_first_answer = 0  # questions are numbered per topic
    st.session_state.quiz_progress = 0.0
    st.session_state.quiz_feedback = None  # the kind message waiting to be read
    st.session_state.quiz_just_right = False
    st.session_state.quiz_not_saved = False
    st.session_state.quiz_no_questions = False


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

# The API raises on a topic that is not in the graph, and most topics may not be in it yet.
in_graph = {node["id"] for node in graph_data.get("nodes", [])} | {
    end
    for edge in graph_data.get("edges", [])
    if edge.get("decision") == "ACCEPT"
    for end in (edge["source"], edge["target"])
}

# Answers belong to one course: another course starts a new quick check.
if "quiz_mastery" not in st.session_state or st.session_state.get("quiz_course") != course:
    reset_quiz()
    st.session_state.quiz_course = course


def next_item(target: str) -> dict | None:
    return api.next_question(
        graph_data,
        valid_items,
        {**st.session_state.quiz_mastery, "__asked__": list(st.session_state.quiz_asked)},
        target,
    )


def finish() -> None:
    """Out of questions: open the plan by itself, unless there is nothing to base it on."""
    st.session_state.quiz_picking = True  # coming back here starts with a new topic
    if st.session_state.quiz_answers:
        st.switch_page(ui.PAGES["plan"].path)
    st.session_state.quiz_no_questions = True
    st.rerun()


def go_on(target: str) -> None:
    if next_item(target) is None:
        finish()
    st.rerun()


def progress_so_far(target: str) -> float:
    """How far along, for the bar only: an estimate, so no number is ever shown with it.

    Answered / (answered + topics that could still be asked). A wrong answer can make earlier
    topics uncertain again, so the estimate can drop; the bar keeps its highest value.
    """
    mastery = st.session_state.quiz_mastery
    with_question = {q.get("concept_id") for q in valid_items}
    left = [
        step
        for step in api.personalized_path(graph_data, mastery, target)
        if step["concept_id"] in with_question
        and step["concept_id"] not in mastery.get("__observed__", {})
    ]
    answered = len(st.session_state.quiz_answers) - st.session_state.quiz_first_answer
    value = answered / (answered + max(len(left), 1))
    st.session_state.quiz_progress = max(st.session_state.quiz_progress, value)
    return st.session_state.quiz_progress


def plain_text(text: str) -> str:
    """Topic names instead of raw ids in the text of a root-cause explanation."""
    for concept_id in sorted(names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(concept_id)}\b", names[concept_id], text)
    return text


def root_cause_line(info: dict, concept_id: str) -> str | None:
    """The explanation in plain words, always saying when it did not come from the AI helper.

    The tracer's own fallback sentences use raw ids and research terms, so they are worded
    here from the topic it points to.
    """
    label, text = split_explanation(info.get("explanation"))
    topic = names.get(info.get("traced_concept"))
    guess = S.QUIZ_GUESS_TOPIC.format(topic=topic) if topic else None
    if label:
        why = guess or (plain_text(text) if text else None)
        return S.QUIZ_WHY_GUESS.format(label=label, why=why) if why else None
    if concept_id in in_graph and api.prerequisite_order(graph_data, concept_id) == [concept_id]:
        return S.QUIZ_WHY_NO_EARLIER  # no earlier topic to trace to: the AI helper was not asked
    why = guess if text in (None, NO_EXPLANATION) else plain_text(text)
    return S.QUIZ_WHY_AI.format(why=why) if why else None


def record_answer(question: dict, choice: str) -> None:
    """Log and score first: a second tap during the slow step below must not lose this answer."""
    concept_id = question.get("concept_id", "")
    q_id = question.get("id", question.get("item_id", f"q_{len(st.session_state.quiz_asked)}"))
    correct_answer = question.get("answer", question.get("correct_answer", question.get("correct")))
    is_correct = str(choice).strip().lower() == str(correct_answer).strip().lower()
    mastery_before = dict(st.session_state.quiz_mastery)

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
        st.session_state.quiz_not_saved = True

    st.session_state.quiz_mastery = api.update_mastery(
        graph_data, mastery_before, concept_id, is_correct
    )
    st.session_state.quiz_asked.append(q_id)
    answer = {
        "item_id": q_id,
        "concept_id": concept_id,
        "selected": choice,
        "correct": is_correct,
        "root_cause": None,
    }
    st.session_state.quiz_answers.append(answer)
    st.session_state.quiz_just_right = is_correct
    if is_correct:
        return

    feedback = {"answer": str(correct_answer), "why": None}
    st.session_state.quiz_feedback = feedback
    with st.spinner(S.QUIZ_THINKING):
        try:
            from cdlp.root_cause import api as root_cause_api

            info = root_cause_api.trace(
                graph_data, question, str(choice), mastery_before, allow_fallback=True
            )
        except Exception:  # the kind message and the plan still work without a reason
            return
    answer["root_cause"] = info.get("explanation")
    feedback["why"] = root_cause_line(info, concept_id)


def show_not_saved() -> None:
    if st.session_state.quiz_not_saved:
        st.warning(S.QUIZ_NOT_SAVED, icon="⚠️")
        st.session_state.quiz_not_saved = False


def pick_topic_screen() -> None:
    ui.page_header(S.QUIZ_TITLE, S.QUIZ_INTRO, step=3, source_file="quiz_items.json")
    concept_ids = sorted(names, key=lambda c: names[c].lower())
    if not concept_ids:
        ui.empty_state(
            S.QUIZ_NO_TOPICS, S.QUIZ_NO_TOPICS_NEXT, action=S.TOPICS_ADD, page="add", icon="📄"
        )
        st.stop()

    remembered = st.session_state.get("study_target")
    # A selectbox filters as you type, in the browser: no wait on weak internet.
    target = st.selectbox(
        S.QUIZ_TARGET,
        concept_ids,
        index=concept_ids.index(remembered) if remembered in names else None,
        placeholder=S.QUIZ_SEARCH_HINT,
        format_func=lambda c: names.get(c, c),
    )
    ready = target in in_graph
    if target and not ready:
        st.info(S.QUIZ_NOT_READY, icon="ℹ️")
    if st.session_state.quiz_no_questions and ready:
        st.info(S.QUIZ_NO_QUESTIONS, icon="ℹ️")

    if ui.action_button(S.QUIZ_START, icon="✏️", key="quiz_start", disabled=not ready):
        st.session_state.study_target = target  # a plain key: widgets do not survive other pages
        st.session_state.quiz_picking = False
        st.session_state.quiz_no_questions = False
        st.session_state.quiz_first_answer = len(st.session_state.quiz_answers)
        st.session_state.quiz_progress = 0.0
        go_on(target)
    if st.session_state.quiz_answers:
        ui.action_button(S.QUIZ_TO_PLAN, page="plan", icon="🗺️", primary=False)


def feedback_screen(target: str) -> None:
    ui.page_header(S.QUIZ_TITLE, source_file="quiz_items.json")
    show_not_saved()
    feedback = st.session_state.quiz_feedback
    st.info(S.QUIZ_KIND, icon="💛")
    st.markdown(S.QUIZ_THE_ANSWER.format(answer=feedback["answer"]))
    if feedback["why"]:
        st.caption(feedback["why"])
    if ui.action_button(S.QUIZ_CONTINUE, icon="➡️", key="quiz_continue"):
        st.session_state.quiz_feedback = None
        go_on(target)


def question_screen(target: str, question: dict) -> None:
    ui.page_header(S.QUIZ_TITLE, source_file="quiz_items.json")
    show_not_saved()
    if st.session_state.quiz_just_right:
        st.success(S.QUIZ_RIGHT_NOTE)
        st.session_state.quiz_just_right = False

    answered = len(st.session_state.quiz_answers) - st.session_state.quiz_first_answer
    concept_id = question.get("concept_id", "")
    st.markdown(S.QUIZ_QUESTION.format(number=answered + 1))
    st.progress(progress_so_far(target))
    st.caption(S.QUIZ_ABOUT.format(topic=names.get(concept_id, concept_id)))
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

    q_id = question.get("id", question.get("item_id", answered))
    for index, option in enumerate(options):
        # A button label is Markdown: without this, "a * b * c" would lose its stars.
        label = re.sub(r"([\\`*_~$\[\]:])", r"\\\1", option)
        if ui.action_button(label, key=f"answer_{q_id}_{index}", primary=False):
            record_answer(question, option)
            if st.session_state.quiz_just_right:
                go_on(target)
            st.rerun()

    st.divider()
    if st.session_state.quiz_answers:
        ui.action_button(S.QUIZ_TO_PLAN, page="plan", icon="🗺️", primary=False)
    if ui.action_button(S.QUIZ_OTHER_TOPIC, icon="🔍", primary=False, key="quiz_other_topic"):
        st.session_state.quiz_picking = True
        st.rerun()


active_target = st.session_state.get("study_target")
if st.session_state.quiz_picking or active_target not in in_graph:
    pick_topic_screen()
elif st.session_state.quiz_feedback:
    feedback_screen(active_target)
else:
    current = next_item(active_target)
    if current is None:
        finish()
    question_screen(active_target, current)
