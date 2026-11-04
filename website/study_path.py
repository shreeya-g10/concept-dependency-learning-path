"""What the study plan and the topic map both say about a student's topics.

Both pages read this, so the plan and the map cannot disagree on the first topic or on the
word for a topic's state. It only reads session state and the learning-path api.
"""

from __future__ import annotations

import common  # noqa: F401  (puts the repository root on sys.path, for cdlp)
import streamlit as st
import strings as S

from cdlp.learning_path import api

STATUS = {"done": S.PLAN_STATUS_DONE, "next": S.PLAN_STATUS_NEXT, "later": S.PLAN_STATUS_LATER}


def answered(course: str) -> bool:
    """The student has answers for this course, so a plan can be worked out."""
    return bool(st.session_state.get("quiz_answers")) and (
        st.session_state.get("quiz_course") == course
    )


def plan_state(course: str, graph: dict, quiz: dict, target: str) -> dict:
    """The plan for this student: steps in order, the ladder summary (or None), and what is next.

    When the question limit stopped an old-style check, topics the student was not asked count
    as unknown, so they stay on the plan even if a right answer elsewhere suggested they are
    known. A ladder plan never holds a topic that was only inferred.
    """
    mastery = st.session_state.quiz_mastery
    with_asked = {**mastery, "__asked__": list(st.session_state.get("quiz_asked", []))}
    ladder = api.ladder_summary(graph, quiz, with_asked, target) if api.uses_ladder(quiz) else None
    if ladder:
        more_questions = api.ladder_next(graph, quiz, with_asked, target)
        limit_stopped = ladder["limit_reached"]
        steps = api.personalized_path(graph, mastery, target)
    else:
        more_questions = api.next_question(graph, quiz, with_asked, target)
        asked_for_target = st.session_state.get("quiz_topic_counts", {}).get(target, 0)
        limit_stopped = (
            more_questions is not None and asked_for_target >= api.MAX_QUESTIONS_PER_TOPIC
        )
        steps = api.personalized_path(
            graph, api.only_answered(mastery) if limit_stopped else mastery, target
        )
    order = [step["concept_id"] for step in steps]
    done = st.session_state.setdefault("plan_done", {}).setdefault(course, [])
    return {
        "ladder": ladder,
        "rows": {row["concept_id"]: row for row in ladder["rows"]} if ladder else {},
        "more_questions": more_questions,
        "limit_stopped": limit_stopped,
        "steps": steps,
        "order": order,
        "done": done,
        "next_up": next((c for c in order if c not in done), None),
    }


def status_of(plan: dict, concept_id: str) -> str | None:
    """done, next or later for a topic on the plan; None for a topic that is not on it."""
    if concept_id not in plan["order"]:
        return None
    if concept_id in plan["done"]:
        return "done"
    return "next" if concept_id == plan["next_up"] else "later"


def result_words(row: dict) -> str:
    return S.PLAN_RESULT_THINK_KNOWN if row["inferred"] else S.PLAN_RESULTS[row["result"]]


def state_of(plan: dict, concept_id: str) -> str:
    """One word for how the map colours a topic. The words a student reads: topic_words()."""
    status = status_of(plan, concept_id)
    if status in ("next", "done"):
        return status
    row = plan["rows"].get(concept_id)
    if row:
        return row["result"]
    return status or "know_it"


def topic_words(plan: dict, concept_id: str) -> list[str]:
    """The lines the map shows for a topic, in the words the plan uses for the same state.

    With levels: the result, with Next or Done first when the plan shows that too. Without
    levels: the plan's Done, Next or Later. A topic left off the plan was only suggested by the
    answers, so it never reads as more certain than that.
    """
    status = status_of(plan, concept_id)
    row = plan["rows"].get(concept_id)
    if row:
        lines = [STATUS[status]] if status in ("next", "done") else []
        return [*lines, result_words(row)]
    return [STATUS[status]] if status else [S.PLAN_RESULT_THINK_KNOWN]
