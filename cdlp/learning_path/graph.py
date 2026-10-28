
"""Accepted prerequisite graph and baseline traversal.

Owner: Shrestha
"""

import networkx as nx


def load_graph(validated_graph: dict) -> nx.DiGraph:
    """Create a graph using only ACCEPT relationships."""
    graph = nx.DiGraph()

    for node in validated_graph["nodes"]:
        graph.add_node(
            node["id"],
            **{k: v for k, v in node.items() if k != "id"}
        )

    for edge in validated_graph["edges"]:
        if edge.get("decision") == "ACCEPT":
            graph.add_edge(
                edge["source"],
                edge["target"],
                **edge
            )

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError(
            "Accepted prerequisite relationships contain a cycle"
        )

    return graph


def prerequisites(graph: nx.DiGraph, concept: str) -> set[str]:
    """Return all prerequisites of a concept."""
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")

    return nx.ancestors(graph, concept)


def dependents(graph: nx.DiGraph, concept: str) -> set[str]:
    """Return all concepts that depend on this concept."""
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")

    return nx.descendants(graph, concept)


def generic_path(graph: nx.DiGraph, target: str) -> list[str]:
    """Return prerequisites and target in topological order."""
    required = prerequisites(graph, target) | {target}
    subgraph = graph.subgraph(required)

    return list(nx.topological_sort(subgraph))
