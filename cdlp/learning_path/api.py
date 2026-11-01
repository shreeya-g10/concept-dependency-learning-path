"""Public API for adaptive diagnosis and personalized learning paths.

Owner: Vaidehi (inherited from Shrestha).
Keep the three public function signatures stable:
    next_question(graph, quiz, mastery, target) -> dict | None
    update_mastery(graph, mastery, concept_id, correct) -> dict
    personalized_path(graph, mastery, target) -> list[dict]
"""

from __future__ import annotations

from cdlp.learning_path.graph import ancestors, generic_path, load_graph


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
    """Update mastery after a student answer, propagating upstream through the graph."""
    G = load_graph(graph)
    updated = {k: v for k, v in mastery.items() if not k.startswith("__")}

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
                if prerequisite not in updated or updated[prerequisite] > 0.8:
                    updated[prerequisite] = 0.5

    # Retain __asked__ tracker if present
    if "__asked__" in mastery:
        updated["__asked__"] = mastery["__asked__"]

    return updated


def personalized_path(
    graph: dict,
    mastery: dict[str, float],
    target: str,
) -> list[dict]:
    """Generate an ordered learning path excluding mastered concepts.

    1. All ancestors of target in DAG.
    2. Remove concepts with mastery > 0.8.
    3. Topological ordering.
    4. Attach evidence citations (doc, page) and rationale.
    """
    G = load_graph(graph)
    order = generic_path(G, target)
    steps = []

    for concept in order:
        # Skip concepts student already mastered
        if mastery.get(concept, 0.5) > 0.8:
            continue

        evidence = []
        direct_prereqs = []

        if concept in G:
            for source in G.predecessors(concept):
                direct_prereqs.append(source)
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

        if concept == target:
            why = "This is your target learning concept."
        elif direct_prereqs:
            why = f"Essential foundation required for: {', '.join(direct_prereqs)}."
        else:
            why = "Build foundational knowledge before advancing."

        steps.append(
            {
                "concept_id": concept,
                "why": why,
                "evidence": evidence,
            }
        )

    return steps
