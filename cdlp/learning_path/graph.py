"""Accepted prerequisite graph and baseline traversal (owner: Shrestha)."""

import networkx as nx


def load_graph(validated_graph: dict) -> nx.DiGraph:
    """Create a DAG from ACCEPT edges, preserving strength and evidence."""
    graph = nx.DiGraph()
    for node in validated_graph["nodes"]:
        graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in validated_graph["edges"]:
        if edge.get("decision") == "ACCEPT":
            graph.add_edge(edge["source"], edge["target"], **edge)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Accepted prerequisite relationships contain a cycle")
    return graph


def prerequisites(graph: nx.DiGraph, concept: str) -> set[str]:
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")
    return nx.ancestors(graph, concept)


def dependents(graph: nx.DiGraph, concept: str) -> set[str]:
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")
    return nx.descendants(graph, concept)


def generic_path(graph: nx.DiGraph, target: str) -> list[str]:
    """Non-adaptive baseline: every prerequisite followed by the target."""
    return list(nx.topological_sort(graph.subgraph(prerequisites(graph, target) | {target})))
