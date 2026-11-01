"""Impact-ranked review queue: which HUMAN_REVIEW edges matter most to students?

    from cdlp.validation.review_queue import build_review_queue, write_review_queue
    queue = build_review_queue(validated_graph, sim_students)  # dict in review_queue.json shape

For every HUMAN_REVIEW edge, flip it: compare each simulated student's personalized
path on the ACCEPT-only graph with the path on ACCEPT + that edge. `paths_affected` is
the number of (student, target) paths whose steps change (a different concept set or a
different order). `impact_score` = paths_affected / paths checked, in [0, 1].

Order: BLOCKING edges first, then the rest by impact, highest first. An edge is
blocking when accepting it as it is would break the graph: it closes a cycle with the
ACCEPT edges (or is a self-loop). Its flipped path is undefined, so `impact_score` and
`paths_affected` are null (not 0) and `blocking` is true. Every review strategy must
handle blocking edges before any impact-ranked edge, whatever it ranks the rest by.

The path rule is implemented here, not imported from cdlp/learning_path (modules talk
through files only), and it MUST match cdlp/learning_path/api.py personalized_path():
    path = (ancestors of target + target) - mastered concepts, in topological order,
with mastered = mastery > 0.8, the same strict threshold, and a concept missing from
the mastery dict counted as not mastered (api.py defaults it to 0.5, also <= 0.8). Soft
prerequisites are never skipped, as in api.py. One deliberate difference: api.py's
order among unordered concepts follows graph insertion order, while here ties go to the
smallest concept id, so a path is a function of the graph and not of file order.
tests/test_review_queue.py pins this against api.py; if api.py's rule changes (e.g. soft
prerequisites become skippable), that test fails and this function must follow.

Targets: the given list, or by default the concept with the most ancestors via ACCEPT
edges (ties: smallest id), the same default as pipeline.py.

No LLM call. No CLI wiring yet (planned: `python -m cdlp.validation --review-queue`).
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

SCHEMA_VERSION = "1.4"  # 1.1: review_queue.json; 1.4: blocking, null impact for blocking
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


def is_blocking(graph: nx.DiGraph, source: str, target: str) -> bool:
    """Accepting source -> target as it is would close a cycle with the ACCEPT edges."""
    return source == target or (target in graph and source in nx.descendants(graph, target))


# Keep in sync with cdlp/learning_path/api.py personalized_path() (see module docstring).
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
) -> tuple[int | None, int, bool]:
    """(paths affected, paths checked, blocking) when the edge is accepted.

    A blocking edge (self-loop or cycle with ACCEPT edges) has no flipped path, so its
    paths affected is None, never a made-up number.
    """
    checked = len(students) * len(targets)
    source, target = edge["source"], edge["target"]
    if is_blocking(graph, source, target):
        return None, checked, True
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


def _reason(edge: dict, affected: int | None, checked: int, cycle: bool, targets: list[str]) -> str:
    checks = edge.get("checks", {})
    head = (
        f"Validator unsure (confidence {edge.get('confidence', '?')}, "
        f"necessity {checks.get('necessity', '?')}): {edge.get('reason', '').strip()}"
    ).rstrip(": ")
    if cycle:
        return (
            f"{head} BLOCKING: accepting it would close a cycle with accepted edges, "
            "so it cannot be accepted as it is; resolve the cycle first."
        )
    goal = ", ".join(targets)
    return f"{head} Accepting it changes {affected} of {checked} learning paths (target: {goal})."


def queue_order(row: dict) -> tuple:
    """Blocking edges first (by id), then by impact, highest first, ties by id."""
    if row.get("blocking"):
        return (0, 0.0, 0, row["edge_id"])
    return (1, -(row["impact_score"] or 0.0), -(row["paths_affected"] or 0), row["edge_id"])


def build_review_queue(
    validated_graph: dict,
    sim_students: dict,
    targets: list[str] | None = None,
    mastered_above: float = MASTERED_ABOVE,
) -> dict:
    """review_queue.json content: one row per HUMAN_REVIEW edge, blocking edges first,
    then highest impact first."""
    graph = accepted_graph(validated_graph)
    students = sim_students["students"]
    targets = list(targets) if targets else [default_target(graph)]
    rows = []
    for edge in validated_graph["edges"]:
        if edge["decision"] != "HUMAN_REVIEW":
            continue
        affected, checked, blocking = edge_impact(graph, edge, students, targets, mastered_above)
        if blocking:
            impact = None
        else:
            impact = round(affected / checked, 4) if checked else 0.0
        rows.append(
            {
                "edge_id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "blocking": blocking,
                "impact_score": impact,
                "paths_affected": affected,
                "reason": _reason(edge, affected, checked, blocking, targets),
            }
        )
    rows.sort(key=queue_order)
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
