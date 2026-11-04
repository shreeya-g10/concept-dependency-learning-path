"""Public API for adaptive diagnosis and personalized learning paths.

Owner: Vaidehi (inherited from Shrestha).
Keep the three public function signatures stable:
    next_question(graph, quiz, mastery, target) -> dict | None
    update_mastery(graph, mastery, concept_id, correct) -> dict
    personalized_path(graph, mastery, target) -> list[dict]
"""

from __future__ import annotations

from cdlp.learning_path import ladder
from cdlp.learning_path.graph import (
    MASTERY_THRESHOLD,
    ancestors,
    generic_path,
    is_mastered,
    load_graph,
)

# At most this many quick-check questions per chosen topic. The caller counts per topic: the
# list of asked questions carries across topics in a session, so its length is not the count.
MAX_QUESTIONS_PER_TOPIC = 10


def prerequisite_order(graph: dict, target: str) -> list[str]:
    """Return prerequisites followed by the target in learning order."""
    G = load_graph(graph)
    return generic_path(G, target)


def _quiz_items(quiz: dict | list) -> list[dict]:
    """Normalize quiz items to a list of dicts."""
    if isinstance(quiz, list):
        return quiz
    return quiz.get("items", quiz.get("questions", []))


def next_question(
    graph: dict,
    quiz: dict | list,
    mastery: dict[str, float],
    target: str,
) -> dict | None:
    """Select the next question near the middle of the uncertain prerequisite chain."""
    G = load_graph(graph)
    order = generic_path(G, target)
    asked = set(mastery.get("__asked__", []))
    items = _quiz_items(quiz)

    uncertain = [
        concept for concept in order if 0.2 <= mastery.get(concept, 0.5) <= MASTERY_THRESHOLD
    ]

    available = [
        concept
        for concept in uncertain
        if any(
            item.get("concept_id") == concept and item.get("id", item.get("item_id")) not in asked
            for item in items
        )
    ]

    if not available:
        return None

    # Middle of the chain (binary search heuristic for highest information gain)
    concept = available[len(available) // 2]

    return next(
        (
            item
            for item in items
            if item.get("concept_id") == concept
            and item.get("id", item.get("item_id")) not in asked
        ),
        None,
    )


def update_mastery(
    graph: dict,
    mastery: dict[str, float],
    concept_id: str,
    correct: bool,
) -> dict[str, float]:
    """Update mastery after a student answer, propagating upstream through the graph.

    Correct: the concept -> 0.9, its ancestors -> at least 0.85. Wrong: the concept -> 0.1,
    its ancestors that looked mastered (or were unknown) -> 0.5, i.e. uncertain again.

    **A direct answer always beats propagation.** The latest answer per concept is kept
    under "__observed__" ({concept: correct}) and re-applied after propagating, so a wrong
    answer on BST no longer erases a correct answer the student just gave on binary
    trees (nor does a correct answer lift a concept the student got wrong). Before this
    rule, asking every concept in order destroyed its own evidence and scored below
    adaptive diagnosis in RQ2 (cdlp/learning_path/results/README.md).
    """
    G = load_graph(graph)
    updated = {k: v for k, v in mastery.items() if not k.startswith("__")}
    observed = {**mastery.get("__observed__", {}), concept_id: bool(correct)}

    if correct:
        updated[concept_id] = 0.9
        if concept_id in G:
            for prerequisite in ancestors(G, concept_id):
                updated[prerequisite] = max(
                    updated.get(prerequisite, 0.5),
                    0.85,
                )
    else:
        updated[concept_id] = 0.1
        if concept_id in G:
            for prerequisite in ancestors(G, concept_id):
                if prerequisite not in updated or is_mastered(updated[prerequisite]):
                    updated[prerequisite] = 0.5

    for concept, was_correct in observed.items():
        updated[concept] = 0.9 if was_correct else 0.1
    updated["__observed__"] = observed

    # Retain __asked__ tracker if present
    if "__asked__" in mastery:
        updated["__asked__"] = mastery["__asked__"]

    return updated


# ---- level ladder (ladder.py). Additive: the three functions above are unchanged. ---------


def uses_ladder(quiz: dict | list) -> bool:
    """The ladder runs when configured and the course has levels; else the old selection."""
    return ladder.configured_strategy() in ladder.STRATEGIES and ladder.has_levels(
        _quiz_items(quiz)
    )


def _ladder_strategy(strategy: str | None) -> str:
    return strategy or ladder.configured_strategy()


def ladder_next(
    graph: dict, quiz: dict | list, mastery: dict, target: str, strategy: str | None = None
) -> dict | None:
    """The next quiz item, or {"self_report": concept_id}, or None when finished."""
    return ladder.next_step(
        graph,
        _quiz_items(quiz),
        mastery,
        target,
        _ladder_strategy(strategy),
        MAX_QUESTIONS_PER_TOPIC,
    )


def ladder_self_report(mastery: dict, concept_id: str, answer: str) -> dict:
    """answer: yes, no or not_sure. Sets the starting level only; it never marks a topic known."""
    return ladder.self_report(mastery, concept_id, answer)


def ladder_record(
    graph: dict,
    quiz: dict | list,
    mastery: dict,
    target: str,
    item: dict,
    correct: bool,
    strategy: str | None = None,
) -> dict:
    """The mastery dict after one answer. personalized_path reads its results as usual."""
    return ladder.record_answer(
        graph, _quiz_items(quiz), mastery, target, item, correct, _ladder_strategy(strategy)
    )


def ladder_summary(
    graph: dict, quiz: dict | list, mastery: dict, target: str, strategy: str | None = None
) -> dict:
    """Each topic's result in graph order, plus known, first_to_study, limit_reached, stopped_at
    and not_checked_after_stop."""
    return ladder.summary(
        graph,
        _quiz_items(quiz),
        mastery,
        target,
        _ladder_strategy(strategy),
        MAX_QUESTIONS_PER_TOPIC,
    )


def only_answered(mastery: dict[str, float]) -> dict[str, float]:
    """Keep only what the student answered directly; every other topic goes back to unknown.

    For a quiz that the question limit stopped early: a topic that was never asked is unknown,
    even when a right answer elsewhere suggested it is known. personalized_path keeps unknown
    topics on the plan, so the mistake this can make is extra study, not a missed gap.
    """
    observed = mastery.get("__observed__", {})
    kept = {concept: value for concept, value in mastery.items() if concept in observed}
    return {**kept, "__observed__": dict(observed)}


def _display_name(G, concept: str) -> str:
    """The concept's name from the graph, or its id in words. Never a raw id."""
    name = G.nodes[concept].get("name") if concept in G else None
    return name or concept.replace("_", " ").capitalize()


def _why(G, concept: str, target: str, later: list[str]) -> str:
    """One sentence, about the nearest later topic in this student's own path."""
    if concept == target:
        return "This is the topic you want to learn."
    nearest = next((c for c in later if G.has_edge(concept, c)), None)
    if nearest is None:  # the topic between them is already known: it still leads to the target
        return f"This leads to {_display_name(G, target)}."
    if G.edges[concept, nearest].get("strength", "hard") == "hard":
        return f"You need this before {_display_name(G, nearest)}."
    return f"This helps you learn {_display_name(G, nearest)}."


def personalized_path(
    graph: dict,
    mastery: dict[str, float],
    target: str,
) -> list[dict]:
    """Generate an ordered learning path excluding mastered concepts.

    1. All ancestors of target in DAG.
    2. Remove mastered concepts (mastery > MASTERY_THRESHOLD = 0.8).
    3. Topological ordering, ties by sorted concept id.
    4. Attach evidence citations (doc, page) and a plain reason: what this topic is needed
       for later in the path, using topic names.
    """
    G = load_graph(graph)
    # Skip concepts student already mastered
    order = [c for c in generic_path(G, target) if not is_mastered(mastery.get(c, 0.5))]
    steps = []

    for index, concept in enumerate(order):
        evidence = []

        if concept in G:
            for source in G.predecessors(concept):
                edge_data = G.edges[source, concept]
                raw_ev = edge_data.get("evidence", [])
                if isinstance(raw_ev, list):
                    for ev in raw_ev:
                        if isinstance(ev, dict) and "doc" in ev and "page" in ev:
                            evidence.append(
                                {
                                    "doc": ev["doc"],
                                    "page": ev["page"],
                                    "chunk_id": ev.get("chunk_id", ""),
                                }
                            )

        steps.append(
            {
                "concept_id": concept,
                "why": _why(G, concept, target, order[index + 1 :]),
                "evidence": evidence,
            }
        )

    return steps
