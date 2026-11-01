"""Adaptive diagnosis for prerequisite-based learning.

Owner: Vaidehi (inherited from Shrestha).
"""

from __future__ import annotations

from typing import Any

from cdlp.learning_path.graph import ancestors, generic_path, load_graph, prerequisites


def initial_mastery(graph: Any) -> dict[str, float]:
    """Start every concept at 0.5 mastery (prior)."""
    return {concept: 0.5 for concept in graph.nodes}


def update_mastery(
    graph: Any,
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
        for prerequisite in ancestors(graph, concept_id):
            updated[prerequisite] = max(
                updated.get(prerequisite, 0.5),
                0.85,
            )
    else:
        updated[concept_id] = 0.1
        for prerequisite in ancestors(graph, concept_id):
            # Prioritize prerequisites for diagnosis
            if prerequisite not in updated or updated[prerequisite] > 0.8:
                updated[prerequisite] = 0.5

    return updated


def next_question(
    graph: Any,
    quiz_items: list[dict],
    mastery: dict[str, float],
    target: str,
) -> dict | None:
    """Select the next question using graph-guided binary search.

    Focuses on the most informative concept: near the middle of
    the prerequisite chain for the target, restricted to concepts
    where mastery is still uncertain (around 0.5).
    """
    order = generic_path(graph, target)
    uncertain = [concept for concept in order if 0.2 <= mastery.get(concept, 0.5) <= 0.8]

    if not uncertain:
        return None

    # Binary search: pick concept in the middle of uncertain chain
    mid_index = len(uncertain) // 2
    selected_concept = uncertain[mid_index]

    for item in quiz_items:
        if item.get("concept_id") == selected_concept:
            return item

    for concept in uncertain:
        for item in quiz_items:
            if item.get("concept_id") == concept:
                return item

    return None


def personalized_path(
    graph: Any,
    mastery: dict[str, float],
    target: str,
) -> list[dict]:
    """Generate an adaptive path skipping already mastered concepts."""
    full_path = generic_path(graph, target)
    steps = []

    for concept in full_path:
        score = mastery.get(concept, 0.5)
        # Skip if student already mastered it (>= 0.8)
        if score >= 0.8:
            continue

        node_data = graph.nodes.get(concept, {}) if hasattr(graph, "nodes") else {}
        steps.append(
            {
                "concept_id": concept,
                "name": node_data.get("name", concept.replace("_", " ").title()),
                "status": "needs_review" if score < 0.4 else "unlearned",
                "mastery": score,
                "prerequisites": list(prerequisites(graph, concept)),
            }
        )

    return steps


def run_diagnosis(
    validated_graph_data: dict,
    quiz_items: list[dict],
    student_answers: list[dict],
    target: str,
) -> tuple[dict[str, float], list[dict]]:
    """Run simulated or batch diagnosis for a student given their answer history."""
    G = load_graph(validated_graph_data)
    mastery = initial_mastery(G)

    for ans in student_answers:
        concept = ans.get("concept_id")
        correct = bool(ans.get("correct"))
        if concept and concept in G:
            mastery = update_mastery(G, mastery, concept, correct)

    path = personalized_path(G, mastery, target)
    return mastery, path
