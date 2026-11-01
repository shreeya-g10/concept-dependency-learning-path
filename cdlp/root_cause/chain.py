"""Prerequisite chain of a quiz item's concept over ACCEPT edges, nearest first.

The chain is the set of concepts a wrong answer can be blamed on: the item's own
concept (distance 0) plus every ancestor in the validated graph. Only ACCEPT edges
count (REJECT and HUMAN_REVIEW edges are not part of the course graph downstream).
"""

from __future__ import annotations

import networkx as nx

UNKNOWN_MASTERY = 0.5  # used for ranking only, when the student's mastery is not known


def accept_graph(graph: dict) -> nx.DiGraph:
    g = nx.DiGraph()
    for node in graph.get("nodes", []):
        g.add_node(node["id"], name=node.get("name", node["id"]))
    for edge in graph.get("edges", []):
        if edge.get("decision") == "ACCEPT":
            g.add_edge(edge["source"], edge["target"], strength=edge.get("strength", "hard"))
    return g


def prerequisite_chain(graph: dict, concept: str) -> list[dict]:
    """Return [{concept_id, name, distance, prerequisite_of: [{concept_id, strength}]}].

    Sorted by distance from `concept` (shortest path over ACCEPT edges), then id.
    `prerequisite_of` lists the chain concepts this one is a direct prerequisite of.
    """
    g = accept_graph(graph)
    if concept not in g:
        g.add_node(concept, name=concept)
    distance = nx.single_source_shortest_path_length(g.reverse(copy=False), concept)
    chain = []
    for cid, dist in distance.items():
        chain.append(
            {
                "concept_id": cid,
                "name": g.nodes[cid].get("name", cid),
                "distance": dist,
                "prerequisite_of": [
                    {"concept_id": t, "strength": g.edges[cid, t]["strength"]}
                    for t in sorted(g.successors(cid))
                    if t in distance
                ],
            }
        )
    return sorted(chain, key=lambda c: (c["distance"], c["concept_id"]))
