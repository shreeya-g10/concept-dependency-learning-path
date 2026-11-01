"""Impact-ranked review queue: which HUMAN_REVIEW edges matter most to students?

    from cdlp.validation.review_queue import build_review_queue, write_review_queue
    queue = build_review_queue(validated_graph, sim_students)  # dict in review_queue.json shape

For every HUMAN_REVIEW edge, flip it: compare each simulated student's personalized
path on the ACCEPT-only graph with the path on ACCEPT + that edge. `paths_affected` is
the number of (student, target) paths whose steps change (a different concept set or a
different order). `impact_score` = paths_affected / paths checked, in [0, 1]. Rows are
sorted by impact, highest first, so reviewers see the edges that change most paths.

The path rule is implemented here, not imported from cdlp/learning_path (modules talk
through files only). It follows the same rule:
    path = (ancestors of target + target) - mastered concepts, in topological order,
with mastered = TRUE mastery > 0.8 (`sim_students.json`), and ties in the topological
order broken by concept id so paths are deterministic.

Targets: the given list, or by default the concept with the most ancestors via ACCEPT
edges (ties: smallest id), the same default as pipeline.py.

An edge that would close a cycle with the ACCEPT edges cannot be accepted as it is.
It gets paths_affected 0 and impact_score 0, and its reason says why.

No LLM call. No CLI wiring yet (planned: `python -m cdlp.validation --review-queue`).
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

SCHEMA_VERSION = "1.1"  # review_queue.json is new in contract 1.1
MASTERED_ABOVE = 0.8  # same threshold as the learning-path rule


def accepted_graph(validated_graph: dict) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(node["id"] for node in validated_graph.get("nodes", []))
    for edge in validated_graph["edges"]:
        graph.add_nodes_from((edge["source"], edge["target"]))
        if edge["decision"] == "ACCEPT":
            graph.add_edge(edge["source"], edge["target"])
    return graph


def default_target(graph: nx.DiGraph) -> str:
    """Concept with the most ancestors via ACCEPT edges; ties go to the smallest id."""
    if graph.number_of_edges() == 0:
        raise ValueError("no ACCEPT edges: pass targets explicitly")
    return min(graph.nodes, key=lambda node: (-len(nx.ancestors(graph, node)), node))


def personalized_path(
    graph: nx.DiGraph,
    mastery: dict[str, float],
    target: str,
    mastered_above: float = MASTERED_ABOVE,
) -> list[str]:
    """(ancestors of target + target) minus mastered concepts, in topological order."""
    if target not in graph:
        return [] if mastery.get(target, 0.0) > mastered_above else [target]
    needed = nx.ancestors(graph, target) | {target}
    order = nx.lexicographical_topological_sort(graph.subgraph(needed))
    return [c for c in order if mastery.get(c, 0.0) <= mastered_above]


def edge_impact(
    graph: nx.DiGraph,
    edge: dict,
    students: list[dict],
    targets: list[str],
    mastered_above: float = MASTERED_ABOVE,
) -> tuple[int, int, bool]:
    """(paths affected, paths checked, creates a cycle) when the edge is accepted."""
    checked = len(students) * len(targets)
    source, target = edge["source"], edge["target"]
    if source == target or (target in graph and source in nx.descendants(graph, target)):
        return 0, checked, True
    flipped = graph.copy()
    flipped.add_edge(source, target)
    affected = 0
    for student in students:
        mastery = student.get("mastery", {})
        for goal in targets:
            before = personalized_path(graph, mastery, goal, mastered_above)
            after = personalized_path(flipped, mastery, goal, mastered_above)
            affected += before != after
    return affected, checked, False


def _reason(edge: dict, affected: int, checked: int, cycle: bool, targets: list[str]) -> str:
    checks = edge.get("checks", {})
    head = (
        f"Validator unsure (confidence {edge.get('confidence', '?')}, "
        f"necessity {checks.get('necessity', '?')}): {edge.get('reason', '').strip()}"
    ).rstrip(": ")
    if cycle:
        return (
            f"{head} Accepting it would close a cycle with accepted edges, "
            "so it cannot be accepted as it is."
        )
    goal = ", ".join(targets)
    return f"{head} Accepting it changes {affected} of {checked} learning paths (target: {goal})."


def build_review_queue(
    validated_graph: dict,
    sim_students: dict,
    targets: list[str] | None = None,
    mastered_above: float = MASTERED_ABOVE,
) -> dict:
    """review_queue.json content: one row per HUMAN_REVIEW edge, highest impact first."""
    graph = accepted_graph(validated_graph)
    students = sim_students["students"]
    targets = list(targets) if targets else [default_target(graph)]
    rows = []
    for edge in validated_graph["edges"]:
        if edge["decision"] != "HUMAN_REVIEW":
            continue
        affected, checked, cycle = edge_impact(graph, edge, students, targets, mastered_above)
        rows.append(
            {
                "edge_id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "impact_score": round(affected / checked, 4) if checked else 0.0,
                "paths_affected": affected,
                "reason": _reason(edge, affected, checked, cycle, targets),
            }
        )
    rows.sort(key=lambda row: (-row["impact_score"], -row["paths_affected"], row["edge_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": validated_graph["course_id"],
        "queue": rows,
    }


def write_review_queue(
    path: Path | str,
    validated_graph: dict,
    sim_students: dict,
    targets: list[str] | None = None,
) -> dict:
    """Build the queue and write it with cdlp.shared.io (validated against the schema)."""
    from cdlp.shared.io import write_json

    queue = build_review_queue(validated_graph, sim_students, targets)
    write_json(path, queue)
    return queue
