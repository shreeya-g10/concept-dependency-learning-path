"""Adaptive diagnosis for prerequisite-based learning.

Owner: Vaidehi (inherited from Shrestha).
"""

from __future__ import annotations

import networkx as nx

from cdlp.learning_path.graph import generic_path, load_graph


def initial_mastery(graph: nx.DiGraph) -> dict[str, float]:
    """Start every concept at 0.5 mastery (prior)."""
    return {concept: 0.5 for concept in graph.nodes}


def update_mastery(
    graph: nx.DiGraph,
    mastery: dict[str, float],
    concept_id: str,
    correct: bool,
) -> dict[str, float]:
    """Update mastery using the student's answer.

    Correct answer raises mastery of concept and its ancestors.
    Incorrect answer lowers concept mastery and marks prerequisites as uncertain.
    """
    if concept_id not in graph:
        raise ValueError(f"Unknown concept: {concept_id}")

    updated = dict(mastery)

    if correct:
        updated[concept_id] = 0.9
        for prerequisite in nx.ancestors(graph, concept_id):
            updated[prerequisite] = max(
                updated.get(prerequisite, 0.5),
                0.85,
            )
    else:
        updated[concept_id] = 0.1
        for prerequisite in nx.ancestors(graph, concept_id):
            # Prioritize prerequisites for diagnosis
            if prerequisite not in updated or updated[prerequisite] > 0.8:
                updated[prerequisite] = 0.5

    return updated


def next_question(
    graph: nx.DiGraph,
    quiz: dict | list,
    mastery: dict[str, float],
    target: str,
    asked_ids: list[str] | None = None,
) -> dict | None:
    """Select the next most informative question: middle of the uncertain chain."""
    asked = set(asked_ids or [])

    items = quiz if isinstance(quiz, list) else quiz.get("items", quiz.get("questions", []))

    order = generic_path(graph, target)

    uncertain = [concept for concept in order if 0.2 <= mastery.get(concept, 0.5) <= 0.8]

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

    # Binary search selection: concept in the middle of the uncertain chain
    selected = available[len(available) // 2]

    return next(
        (
            item
            for item in items
            if item.get("concept_id") == selected
            and item.get("id", item.get("item_id")) not in asked
        ),
        None,
    )


def diagnose_student(
    validated_graph: dict,
    quiz: dict | list,
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
        question = next_question(graph, quiz, mastery, target, asked_ids)
        if question is None:
            break

        q_id = question.get("id", question.get("item_id", f"q_{len(asked_ids)}"))
        concept = question["concept_id"]
        correct = true_mastery.get(concept, 0.5) > 0.5

        mastery = update_mastery(graph, mastery, concept, correct)
        asked_ids.append(q_id)
        answers.append(
            {
                "item_id": q_id,
                "correct": correct,
            }
        )

    return {
        "target": target,
        "mastery": mastery,
        "answers": answers,
        "questions_asked": len(answers),
    }
