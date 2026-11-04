"""The level ladder: how sure we are about each topic, from easy, medium and hard questions.

For a target, topics come from its prerequisites in graph order (graph.generic_path). A topic
starts with "Have you studied it?": Yes starts at medium, No or Not sure at easy. That answer
only sets the starting level. It never marks a topic as known.

    easy right -> medium        medium right -> hard        hard right -> know_it
    medium wrong after a Yes start -> easy
    medium right, hard wrong -> quick_revision
    easy right, medium wrong -> study_this
    easy wrong -> start_here: ladder_linear skips the topics that depend on it through hard
    links, which stay not_checked, and keeps asking the rest, soft-linked topics included. On a
    straight chain of hard links that ends the quiz.

State lives in the mastery dict under "__ladder__", beside "__asked__" and "__observed__". The
values update_mastery would write are not used here: its propagation lifts ancestors, which
would mark a topic already graded study_this as known after a later right answer.

ladder_linear asks the first unfinished topic. ladder_middle (evaluated, not shown) asks the
middle of what is still open: know_it also infers the topic's ancestors, and any other result
closes the topics that depend on it through hard links, so the search moves earlier.

No easy or medium question left for a slot: the nearest level stands in (the easier one on a tie)
and this is recorded under the topic's "stand_ins". No hard question left: nothing stands in,
because an easier question could not earn know_it. The topic ends at quick_revision without asking,
and "no_hard_question" is recorded. No question left at all: the topic ends at the result the
answers so far support, which never claims more than they showed. A difficulty label from the AI
is only a suggestion until a teacher approves it.

start_here is the stored name of the result students read as "Start from the basics".
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from cdlp.learning_path.graph import ancestors, generic_path, load_graph

LEVELS = ("easy", "medium", "hard")
SELF_REPORTS = ("yes", "no", "not_sure")
STRATEGIES = ("ladder_linear", "ladder_middle")
CONFIG = Path(__file__).parent / "configs" / "quick_check.json"

KNOW_IT, QUICK_REVISION, STUDY_THIS = "know_it", "quick_revision", "study_this"
START_HERE, NOT_CHECKED = "start_here", "not_checked"
# Only know_it is above the mastery threshold (0.8), so every other result stays on the plan.
# A design choice that fits the order of the results, not a calibrated probability.
RESULT_MASTERY = {KNOW_IT: 0.9, QUICK_REVISION: 0.7, STUDY_THIS: 0.4, START_HERE: 0.1}
INFERRED_MASTERY = 0.85  # the value update_mastery gives an ancestor after a right answer


def configured_strategy() -> str:
    """The one value that picks what the quick check uses: "adaptive" or a ladder strategy."""
    strategy = json.loads(CONFIG.read_text(encoding="utf-8"))["strategy"]
    if strategy != "adaptive" and strategy not in STRATEGIES:
        raise ValueError(f"{CONFIG.name}: unknown strategy {strategy!r}")
    return strategy


def hard_dependents(G: Any, concept: str) -> set[str]:
    """Topics reached from this one through hard links only. A soft link does not make a topic
    depend on this one, and neither does a hard link that comes after a soft one."""
    hard_next: dict[str, list[str]] = {}
    for source, target, data in G.edges(data=True):
        if data.get("strength", "hard") == "hard":
            hard_next.setdefault(source, []).append(target)
    found: set[str] = set()
    waiting = list(hard_next.get(concept, []))
    while waiting:
        current = waiting.pop()
        if current not in found:
            found.add(current)
            waiting.extend(hard_next.get(current, []))
    return found


def has_levels(items: list[dict]) -> bool:
    """A course whose items have no difficulty keeps the old selection."""
    return any(item.get("difficulty") in LEVELS for item in items)


def level_of(item: dict) -> str:
    """An unlabelled item counts as easy, and can stand in at any level like any other."""
    level = item.get("difficulty")
    return level if level in LEVELS else "easy"


def _item_id(item: dict) -> Any:
    return item.get("id", item.get("item_id"))


def _state(mastery: dict) -> dict:
    return mastery.get("__ladder__") or {"topics": {}, "asked_for_target": {}}


def _unasked(items: list[dict], mastery: dict, concept: str) -> list[dict]:
    asked = set(mastery.get("__asked__", []))
    return [i for i in items if i.get("concept_id") == concept and _item_id(i) not in asked]


def pick_item(items: list[dict], mastery: dict, concept: str, level: str) -> dict | None:
    """An unasked item at this level, else the nearest level; the easier one on a tie."""
    wanted = LEVELS.index(level)
    candidates = _unasked(items, mastery, concept)
    if not candidates:
        return None
    # min() keeps the first of equals, so file order decides within a level.
    return min(
        candidates,
        key=lambda i: (abs(LEVELS.index(level_of(i)) - wanted), LEVELS.index(level_of(i))),
    )


def _current_topic(graph: dict, items: list[dict], mastery: dict, target: str, strategy: str):
    """The topic to ask about now, or None when the ladder has nothing more to ask."""
    G = load_graph(graph)
    topics = _state(mastery)["topics"]
    order = generic_path(G, target)

    def result(concept: str) -> str | None:
        return topics.get(concept, {}).get("result")

    def can_ask(concept: str) -> bool:
        return result(concept) is None and (
            concept in topics or bool(_unasked(items, mastery, concept))
        )

    if strategy == "ladder_linear":
        skipped: set[str] = set()
        for concept in order:
            if result(concept) == START_HERE:
                skipped |= hard_dependents(G, concept)
            elif concept not in skipped and can_ask(concept):
                return concept
        return None

    # ladder_middle: a topic in progress first, then the middle of what is still open.
    in_progress = next((c for c in order if c in topics and result(c) is None), None)
    if in_progress:
        return in_progress
    closed: set[str] = set()
    for concept in order:
        if result(concept) not in (None, KNOW_IT):
            closed |= hard_dependents(G, concept)
    still_open = [c for c in order if c not in closed and can_ask(c)]
    return still_open[len(still_open) // 2] if still_open else None


def next_step(
    graph: dict,
    items: list[dict],
    mastery: dict,
    target: str,
    strategy: str,
    max_questions: int,
) -> dict | None:
    """The next quiz item, or {"self_report": concept}, or None when the ladder is finished."""
    if _state(mastery)["asked_for_target"].get(target, 0) >= max_questions:
        return None
    concept = _current_topic(graph, items, mastery, target, strategy)
    if concept is None:
        return None
    topic = _state(mastery)["topics"].get(concept)
    if topic is None:
        return {"self_report": concept}
    return pick_item(items, mastery, concept, topic["level"])


def self_report(mastery: dict, concept: str, answer: str) -> dict:
    """Sets the starting level only. No mastery value is written, so nothing becomes known."""
    if answer not in SELF_REPORTS:
        raise ValueError(f"unknown answer {answer!r}")
    updated = copy.deepcopy(mastery)
    state = updated.setdefault("__ladder__", _state(updated))
    state["topics"][concept] = {
        "self_report": answer,
        "level": "medium" if answer == "yes" else "easy",
        "answers": [],
        "stand_ins": [],
        "result": None,
    }
    return updated


def _finish(graph: dict, updated: dict, concept: str, result: str, strategy: str) -> None:
    state = updated["__ladder__"]
    state["topics"][concept]["result"] = result
    updated[concept] = RESULT_MASTERY[result]
    if strategy == "ladder_middle" and result == KNOW_IT:
        for ancestor in ancestors(load_graph(graph), concept):
            topic = state["topics"].setdefault(
                ancestor,
                {
                    "self_report": None,
                    "level": None,
                    "answers": [],
                    "stand_ins": [],
                    "result": None,
                },
            )
            if topic["result"] is None:
                topic.update(result=KNOW_IT, inferred=True)
                updated[ancestor] = INFERRED_MASTERY


def record_answer(
    graph: dict,
    items: list[dict],
    mastery: dict,
    target: str,
    item: dict,
    correct: bool,
    strategy: str,
) -> dict:
    """The mastery dict after one answer. The level moves as the ladder rules say."""
    updated = copy.deepcopy(mastery)
    state = updated.setdefault("__ladder__", _state(updated))
    concept = item["concept_id"]
    actual = level_of(item)
    topic = state["topics"].setdefault(
        concept,
        {"self_report": None, "level": actual, "answers": [], "stand_ins": [], "result": None},
    )
    wanted = topic["level"]
    went_down = any(a["wanted"] == "medium" and not a["correct"] for a in topic["answers"])
    topic["answers"].append({"item_id": _item_id(item), "wanted": wanted, "correct": bool(correct)})
    if actual != wanted:
        topic["stand_ins"].append({"wanted": wanted, "used": actual, "item_id": _item_id(item)})
    updated["__asked__"] = [*updated.get("__asked__", []), _item_id(item)]
    updated["__observed__"] = {**updated.get("__observed__", {}), concept: bool(correct)}
    counts = state["asked_for_target"]
    counts[target] = counts.get(target, 0) + 1

    # A level with no question left ends the topic at what the answers so far support.
    if_none_left = None
    if wanted == "easy":
        if not correct:
            result = START_HERE
        elif went_down:
            result = STUDY_THIS
        else:
            result, topic["level"], if_none_left = None, "medium", STUDY_THIS
    elif wanted == "medium":
        if correct:
            result, topic["level"], if_none_left = None, "hard", QUICK_REVISION
        elif topic["self_report"] == "yes":
            result, topic["level"], if_none_left = None, "easy", STUDY_THIS
        else:
            result = STUDY_THIS
    else:
        # A question standing in for hard cannot earn know_it, right or wrong.
        result = KNOW_IT if correct and actual == "hard" else QUICK_REVISION

    if result is None and topic["level"] == "hard":
        unasked = _unasked(items, updated, concept)
        if not any(level_of(i) == "hard" for i in unasked):  # nothing may stand in for hard
            topic["no_hard_question"] = True
            result = QUICK_REVISION
    if result is None and pick_item(items, updated, concept, topic["level"]) is None:
        result = if_none_left
    if result is not None:
        _finish(graph, updated, concept, result, strategy)
    return updated


def summary(
    graph: dict, items: list[dict], mastery: dict, target: str, strategy: str, max_questions: int
) -> dict:
    """Each topic's result in graph order, and why the ladder ended if it has."""
    state = _state(mastery)
    order = generic_path(load_graph(graph), target)
    rows = []
    for concept in order:
        topic = state["topics"].get(concept, {})
        rows.append(
            {
                "concept_id": concept,
                "result": topic.get("result") or NOT_CHECKED,
                "inferred": bool(topic.get("inferred")),
                "stand_ins": list(topic.get("stand_ins", [])),
                "no_hard_question": bool(topic.get("no_hard_question")),
                "questions": len(topic.get("answers", [])),
            }
        )
    at_limit = state["asked_for_target"].get(target, 0) >= max_questions
    more_without_limit = next_step(graph, items, mastery, target, strategy, 10**9) is not None
    stops = []
    if strategy == "ladder_linear":  # ladder_middle moves earlier after a wrong answer
        G = load_graph(graph)
        results = {r["concept_id"]: r["result"] for r in rows}
        for concept in (c for c in order if results[c] == START_HERE):
            depends = hard_dependents(G, concept)
            later = order[order.index(concept) + 1 :]
            helped = set(G.successors(concept)) - depends
            stops.append(
                {
                    "concept_id": concept,
                    "not_checked": [c for c in later if c in depends and results[c] == NOT_CHECKED],
                    "stops_everything_later": set(later) <= depends,
                    # Linked by a soft link, and really asked: another gap may have skipped one.
                    "still_asked": [c for c in later if c in helped and results[c] != NOT_CHECKED],
                }
            )
    return {
        "rows": rows,
        "known": [r["concept_id"] for r in rows if r["result"] == KNOW_IT],
        "first_to_study": next((r["concept_id"] for r in rows if r["result"] != KNOW_IT), None),
        "stops": stops,
        "limit_reached": at_limit and more_without_limit,
    }
