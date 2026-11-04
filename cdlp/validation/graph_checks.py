"""Graph-consistency check: label every relationship with one `checks.graph` value
from validated_graph.schema.json.

Labels, in order of precedence (an edge gets the first that applies):

    self_loop      A -> A
    duplicate      a later copy of an (A, B) pair already seen; the first copy is checked normally
    contradiction  A -> B and B -> A are both proposed (both edges get the label)
    cycle          the edge lies on a directed cycle of length >= 3
    redundant      A -> C where A -> ... -> C exists through other edges (transitive edge)
    ok             none of the above

Only some links count when another link is checked (cdlp/discovery/configs/order_rule_v2.json).
These never count: both links of a pair proposed in both directions, a link flagged
bidirectional, and any link in `not_counted` (the validator passes those rejected on score).
A reversed pair cannot have both links true, so counting it would report the model's
disagreement rather than a cycle in the course. A link that is left out still gets a label,
read against the counted links, but it cannot affect another link.

Redundancy is computed only on the acyclic part of the counted links (edges labelled ok so
far), because a transitive reduction is only unique for a DAG. Only an ok link can be
accepted, and ok links never form a cycle, so the accepted graph stays a DAG.

The check is purely structural: it ignores the discovery confidence, and it does not decide
ACCEPT / REJECT itself.
"""

from collections.abc import Collection

import networkx as nx

OK = "ok"
SELF_LOOP = "self_loop"
DUPLICATE = "duplicate"
CONTRADICTION = "contradiction"
CYCLE = "cycle"
REDUNDANT = "redundant"


def graph_labels(relationships: list[dict], not_counted: Collection[int] = ()) -> list[str]:
    """Return one graph label per relationship, in the same order as the input.

    not_counted holds input positions of links that must not affect any other link.
    """
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

    left_out = {
        pair: i
        for pair, i in first_index.items()
        if labels[i] is None and (i in not_counted or relationships[i].get("bidirectional"))
    }
    remaining = {
        pair: i for pair, i in first_index.items() if labels[i] is None and pair not in left_out
    }
    graph = nx.DiGraph(list(remaining))
    component = {
        node: n for n, nodes in enumerate(nx.strongly_connected_components(graph)) for node in nodes
    }
    for (source, target), i in remaining.items():
        if component[source] == component[target]:
            labels[i] = CYCLE

    dag = nx.DiGraph([pair for pair, i in remaining.items() if labels[i] is None])
    reduced = nx.transitive_reduction(dag)
    for (source, target), i in remaining.items():
        if labels[i] is None:
            labels[i] = OK if reduced.has_edge(source, target) else REDUNDANT

    for (source, target), i in left_out.items():
        labels[i] = _label_against(source, target, graph, dag)
    return labels


def _label_against(source: str, target: str, graph: nx.DiGraph, dag: nx.DiGraph) -> str:
    """What a left-out link would be, given the counted links. It changes nothing else."""

    def reaches(g: nx.DiGraph, start: str, end: str) -> bool:
        return start in g and end in g and nx.has_path(g, start, end)

    if reaches(graph, target, source):
        return CYCLE
    return REDUNDANT if reaches(dag, source, target) else OK


def graph_labels_by_id(
    relationships: list[dict], not_counted: Collection[str] = ()
) -> dict[str, str]:
    """Same as graph_labels, keyed by relationship id; not_counted holds ids here."""
    positions = {i for i, rel in enumerate(relationships) if rel["id"] in not_counted}
    return {
        rel["id"]: label
        for rel, label in zip(relationships, graph_labels(relationships, positions), strict=True)
    }
