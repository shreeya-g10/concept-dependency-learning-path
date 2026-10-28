
"""Adaptive diagnosis for prerequisite-based learning.

Owner: Shrestha
"""

import networkx as nx

from cdlp.learning_path.graph import generic_path, load_graph


def initial_mastery(graph: nx.DiGraph) -> dict[str, float]:
    """Start every concept at 0.5 mastery."""
    return {concept: 0.5 for concept in graph.nodes}


def update_mastery(
    graph: nx.DiGraph,
    mastery: dict[str, float],
    concept_id: str,
    correct: bool,
) -> dict[str, float]:
    """Update mastery using the student's answer."""
    if concept_id not in graph:
        raise ValueError(f"Unknown concept: {concept_id}")

    updated = dict(mastery)

    if correct:
        updated[concept_id] = 0.9

        for prerequisite in nx.ancestors(graph, concept_id):
            updated[prerequisite] = max(
                updated.get(prerequisite, 0.5),
                0.8,
            )
    else:
        updated[concept_id] = 0.1

        for prerequisite in nx.ancestors(graph, concept_id):
            updated.setdefault(prerequisite, 0.5)

    return updated


def next_question(
    graph: nx.DiGraph,
    quiz: dict,
    mastery: dict[str, float],
    target: str,
    asked_ids: list[str] | None = None,
) -> dict | None:
    """Ask about the middle uncertain concept in the learning chain."""
    asked = set(asked_ids or [])

    items = quiz if isinstance(quiz, list) else quiz.get(
        "items", quiz.get("questions", [])
    )

    order = generic_path(graph, target)

    uncertain = [
        concept
        for concept in order
        if 0.2 <= mastery.get(concept, 0.5) <= 0.8
    ]

    available = [
        concept
        for concept in uncertain
        if any(
            item.get("concept_id") == concept
            and item.get("id") not in asked
            for item in items
        )
    ]

    if not available:
        return None

    selected = available[len(available) // 2]

    return next(
        (
            item
            for item in items
            if item.get("concept_id") == selected
            and item.get("id") not in asked
        ),
        None,
    )


def diagnose_student(
    validated_graph: dict,
    quiz: dict,
    true_mastery: dict[str, float],
    target: str,
    max_questions: int = 10,
) -> dict:
    """Simulate an adaptive diagnosis using known student mastery."""
    graph = load_graph(validated_graph)
    mastery = initial_mastery(graph)
    asked_ids = []
    answers = []

    for _ in range(max_questions):
        question = next_question(
            graph, quiz, mastery, target, asked_ids
        )

        if question is None:
            break

        concept = question["concept_id"]
        correct = true_mastery.get(concept, 0.5) > 0.5

        mastery = update_mastery(
            graph, mastery, concept, correct
        )

        asked_ids.append(question["id"])
        answers.append(
            {
                "item_id": question["id"],
                "concept_id": concept,
                "correct": correct,
            }
        )

    return {
        "target": target,
        "mastery": mastery,
        "answers": answers,
        "questions_asked": len(answers),
    }
