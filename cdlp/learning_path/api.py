
"""Public API for adaptive diagnosis and personalized learning paths.

Owner: Shrestha.
Keep the three public function signatures stable.
"""

import networkx as nx


def _build_graph(graph: dict) -> nx.DiGraph:
    """Build a directed prerequisite graph from accepted relationships."""
    G = nx.DiGraph()

    for node in graph.get("nodes", []):
        G.add_node(node["id"], **node)

    for edge in graph.get("edges", []):
        if edge.get("decision", "ACCEPT") != "ACCEPT":
            continue

        source = edge.get("source")
        target = edge.get("target")

        if source and target:
            G.add_edge(source, target, **edge)

    return G


def prerequisite_order(graph: dict, target: str) -> list[str]:
    """Return prerequisites followed by the target in learning order."""
    G = _build_graph(graph)

    if target not in G:
        return [target]

    required = nx.ancestors(G, target) | {target}
    subgraph = G.subgraph(required)

    if not nx.is_directed_acyclic_graph(subgraph):
        raise ValueError("Prerequisite graph contains a cycle.")

    return list(nx.topological_sort(subgraph))


def _quiz_items(quiz: dict) -> list[dict]:
    """Support quiz items stored as either a list or a dictionary."""
    if isinstance(quiz, list):
        return quiz

    return quiz.get("items", quiz.get("questions", []))


def next_question(
    graph: dict,
    quiz: dict,
    mastery: dict[str, float],
    target: str,
) -> dict | None:
    """Select a question near the middle of the uncertain learning chain."""
    order = prerequisite_order(graph, target)
    asked = set(mastery.get("__asked__", []))

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
            for item in _quiz_items(quiz)
        )
    ]

    if not available:
        return None

    concept = available[len(available) // 2]

    return next(
        (
            item
            for item in _quiz_items(quiz)
            if item.get("concept_id") == concept
            and item.get("id") not in asked
        ),
        None,
    )


def update_mastery(
    graph: dict,
    mastery: dict[str, float],
    concept_id: str,
    correct: bool,
) -> dict[str, float]:
    """Update mastery after an answer, including prerequisite knowledge."""
    G = _build_graph(graph)
    updated = dict(mastery)

    if correct:
        updated[concept_id] = 0.9

        if concept_id in G:
            for prerequisite in nx.ancestors(G, concept_id):
                updated[prerequisite] = max(
                    updated.get(prerequisite, 0.5),
                    0.8,
                )
    else:
        updated[concept_id] = 0.1

        if concept_id in G:
            for prerequisite in nx.ancestors(G, concept_id):
                if prerequisite not in updated:
                    updated[prerequisite] = 0.5

    return updated


def personalized_path(
    graph: dict,
    mastery: dict[str, float],
    target: str,
) -> list[dict]:
    """Generate an ordered learning path excluding mastered concepts."""
    G = _build_graph(graph)
    order = prerequisite_order(graph, target)
    steps = []

    for concept in order:
        if mastery.get(concept, 0.5) > 0.8:
            continue

        evidence = []
        prerequisites = []

        if concept in G:
            for source in G.predecessors(concept):
                prerequisites.append(source)
                edge = G.edges[source, concept]
                raw_evidence = edge.get("evidence", [])

                if isinstance(raw_evidence, list):
                    evidence.extend(raw_evidence)

        if concept == target:
            why = "This is your target learning concept."
        elif prerequisites:
            why = (
                "This prerequisite supports later concepts: "
                + ", ".join(prerequisites)
                + "."
            )
        else:
            why = "Build foundational knowledge before progressing."

        steps.append(
            {
                "concept_id": concept,
                "why": why,
                "evidence": evidence,
            }
        )

    return steps
