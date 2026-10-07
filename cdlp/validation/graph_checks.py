"""Graph-consistency check: label every relationship with one `checks.graph` value
from validated_graph.schema.json.

Labels, in order of precedence (an edge gets the first that applies):

    self_loop      A -> A
    duplicate      a later copy of an (A, B) pair already seen; the first copy is checked normally
    contradiction  A -> B and B -> A are both proposed (both edges get the label)
    cycle          the edge lies on a directed cycle of length >= 3
    redundant      A -> C where A -> ... -> C exists through other edges (transitive edge)
    ok             none of the above

Redundancy is computed only on the acyclic part of the graph (edges labelled ok so far),
because a transitive reduction is only unique for a DAG. Cycle and contradiction edges are
left for the validator / HUMAN_REVIEW to resolve, so they never count as a path for
redundancy (they do count when looking for cycles).

The check is purely structural: it uses every proposed relationship regardless of the
discovery confidence, and it does not decide ACCEPT / REJECT itself.
"""

import networkx as nx

OK = "ok"
SELF_LOOP = "self_loop"
DUPLICATE = "duplicate"
CONTRADICTION = "contradiction"
CYCLE = "cycle"
REDUNDANT = "redundant"


def graph_labels(relationships: list[dict]) -> list[str]:
    """Return one graph label per relationship, in the same order as the input."""
    labels: list[str | None] = [None] * len(relationships)
    first_index: dict[tuple[str, str], int] = {}

    for i, rel in enumerate(relationships):
        pair = (rel["source"], rel["target"])
        if pair[0] == pair[1]:
            labels[i] = SELF_LOOP
        elif pair in first_index:
            labels[i] = DUPLICATE
        else:
            first_index[pair] = i

    for (source, target), i in first_index.items():
        if (target, source) in first_index:
            labels[i] = CONTRADICTION

    # Contradiction edges stay in this graph so a longer cycle through them is still found.
    graph = nx.DiGraph(list(first_index))
    component = {
        node: n for n, nodes in enumerate(nx.strongly_connected_components(graph)) for node in nodes
    }
    remaining = {pair: i for pair, i in first_index.items() if labels[i] is None}
    for (source, target), i in remaining.items():
        if component[source] == component[target]:
            labels[i] = CYCLE

    dag = nx.DiGraph([pair for pair, i in remaining.items() if labels[i] is None])
    reduced = nx.transitive_reduction(dag)
    for (source, target), i in remaining.items():
        if labels[i] is None:
            labels[i] = OK if reduced.has_edge(source, target) else REDUNDANT

    return labels


def graph_labels_by_id(relationships: list[dict]) -> dict[str, str]:
    """Same as graph_labels, keyed by relationship id."""
    return {
        rel["id"]: label
        for rel, label in zip(relationships, graph_labels(relationships), strict=True)
    }
