"""Accepted prerequisite graph and baseline traversal.

Owner: Vaidehi (inherited from Shrestha).
"""

from __future__ import annotations

from typing import Any

try:
    import networkx as nx
except ImportError:
    nx = None


class _EdgeView:
    """Edge view mimicking NetworkX's G.edges supporting iteration, calling, and indexing."""

    def __init__(self, graph: DiGraph) -> None:
        self._graph = graph

    def __iter__(self):
        for u, nbrs in self._graph._succ.items():
            for v in nbrs:
                yield (u, v)

    def __call__(self, data: bool = False) -> list[Any]:
        res = []
        for u, nbrs in self._graph._succ.items():
            for v, dat in nbrs.items():
                if data:
                    res.append((u, v, dat))
                else:
                    res.append((u, v))
        return res

    def __getitem__(self, edge: tuple[str, str]) -> dict[str, Any]:
        u, v = edge
        if u in self._graph._succ and v in self._graph._succ[u]:
            return self._graph._succ[u][v]
        raise KeyError(edge)

    def __contains__(self, edge: tuple[str, str]) -> bool:
        u, v = edge
        return u in self._graph._succ and v in self._graph._succ[u]

    def __len__(self) -> int:
        return sum(len(nbrs) for nbrs in self._graph._succ.values())


class DiGraph:
    """Lightweight pure-Python directed graph fallback for environments without networkx."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._succ: dict[str, dict[str, dict[str, Any]]] = {}
        self._pred: dict[str, dict[str, dict[str, Any]]] = {}

    def add_node(self, node_for_adding: str, **attr: Any) -> None:
        if node_for_adding not in self._nodes:
            self._nodes[node_for_adding] = {}
            self._succ[node_for_adding] = {}
            self._pred[node_for_adding] = {}
        self._nodes[node_for_adding].update(attr)

    def add_edge(self, u_of_edge: str, v_of_edge: str, **attr: Any) -> None:
        self.add_node(u_of_edge)
        self.add_node(v_of_edge)
        self._succ[u_of_edge][v_of_edge] = attr
        self._pred[v_of_edge][u_of_edge] = attr

    @property
    def nodes(self) -> dict[str, dict[str, Any]]:
        return self._nodes

    @property
    def edges(self) -> _EdgeView:
        return _EdgeView(self)

    def predecessors(self, n: str):
        if n in self._pred:
            return iter(list(self._pred[n].keys()))
        return iter([])

    def successors(self, n: str):
        if n in self._succ:
            return iter(list(self._succ[n].keys()))
        return iter([])

    def neighbors(self, n: str):
        return self.successors(n)

    def has_edge(self, u: str, v: str) -> bool:
        return u in self._succ and v in self._succ[u]

    def has_node(self, n: str) -> bool:
        return n in self._nodes

    def in_edges(self, n: str, data: bool = False) -> list[Any]:
        res = []
        if n in self._pred:
            for u, dat in self._pred[n].items():
                if data:
                    res.append((u, n, dat))
                else:
                    res.append((u, n))
        return res

    def out_edges(self, n: str, data: bool = False) -> list[Any]:
        res = []
        if n in self._succ:
            for v, dat in self._succ[n].items():
                if data:
                    res.append((n, v, dat))
                else:
                    res.append((n, v))
        return res

    def subgraph(self, nodes: Any) -> DiGraph:
        sub = DiGraph()
        nodes_set = set(nodes)
        for n in nodes_set:
            if n in self._nodes:
                sub.add_node(n, **self._nodes[n])
        for u in nodes_set:
            if u in self._succ:
                for v, dat in self._succ[u].items():
                    if v in nodes_set:
                        sub.add_edge(u, v, **dat)
        return sub

    def __getitem__(self, n: str) -> dict[str, dict[str, Any]]:
        return self._succ[n]

    def __contains__(self, n: str) -> bool:
        return n in self._nodes

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)


def is_dag(graph: Any) -> bool:
    """Check if graph is a directed acyclic graph."""
    if (
        nx is not None
        and hasattr(graph, "__class__")
        and graph.__class__.__module__.startswith("networkx")
    ):
        return nx.is_directed_acyclic_graph(graph)
    if not hasattr(graph, "_pred") or not hasattr(graph, "_succ"):
        return True
    in_degree = {n: len(graph._pred[n]) for n in graph._nodes}
    queue = [n for n, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in graph._succ[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    return visited == len(graph._nodes)


def topological_sort(graph: Any) -> list[str]:
    """Return topological ordering of nodes in the graph."""
    if (
        nx is not None
        and hasattr(graph, "__class__")
        and graph.__class__.__module__.startswith("networkx")
    ):
        return list(nx.topological_sort(graph))
    if not hasattr(graph, "_pred") or not hasattr(graph, "_succ"):
        return list(getattr(graph, "nodes", []))
    in_degree = {n: len(graph._pred[n]) for n in graph._nodes}
    queue = sorted([n for n, deg in in_degree.items() if deg == 0])
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in sorted(graph._succ[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()
    if len(order) != len(graph._nodes):
        raise ValueError("Graph contains a cycle")
    return order


def ancestors(graph: Any, source: str) -> set[str]:
    """Return all ancestors of a node."""
    if (
        nx is not None
        and hasattr(graph, "__class__")
        and graph.__class__.__module__.startswith("networkx")
    ):
        return nx.ancestors(graph, source)
    visited: set[str] = set()
    stack = list(graph._pred.get(source, {}).keys())
    while stack:
        curr = stack.pop()
        if curr not in visited:
            visited.add(curr)
            stack.extend(graph._pred.get(curr, {}).keys())
    return visited


def descendants(graph: Any, source: str) -> set[str]:
    """Return all descendants of a node."""
    if (
        nx is not None
        and hasattr(graph, "__class__")
        and graph.__class__.__module__.startswith("networkx")
    ):
        return nx.descendants(graph, source)
    visited: set[str] = set()
    stack = list(graph._succ.get(source, {}).keys())
    while stack:
        curr = stack.pop()
        if curr not in visited:
            visited.add(curr)
            stack.extend(graph._succ.get(curr, {}).keys())
    return visited


def load_graph(validated_graph: dict) -> Any:
    """Create a graph using only ACCEPT relationships."""
    graph = nx.DiGraph() if nx is not None else DiGraph()

    for node in validated_graph.get("nodes", []):
        graph.add_node(
            node["id"],
            **{k: v for k, v in node.items() if k != "id"},
        )

    for edge in validated_graph.get("edges", []):
        if edge.get("decision") == "ACCEPT":
            graph.add_edge(
                edge["source"],
                edge["target"],
                **edge,
            )

    if not is_dag(graph):
        raise ValueError("Accepted prerequisite relationships contain a cycle")

    return graph


def prerequisites(graph: Any, concept: str) -> set[str]:
    """Return all prerequisites of a concept."""
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")

    return ancestors(graph, concept)


def dependents(graph: Any, concept: str) -> set[str]:
    """Return all concepts that depend on this one."""
    if concept not in graph:
        raise ValueError(f"Unknown concept: {concept}")

    return descendants(graph, concept)


def generic_path(graph: Any, target: str) -> list[str]:
    """Baseline learning path for a student who knows nothing."""
    prereqs = prerequisites(graph, target) | {target}
    subgraph = graph.subgraph(prereqs)
    return topological_sort(subgraph)
