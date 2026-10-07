"""Unit tests for the graph-consistency check, on small hand-made graphs."""

import json
from pathlib import Path

from cdlp.validation.graph_checks import graph_labels, graph_labels_by_id

SCHEMA = Path("cdlp/shared/schemas/validated_graph.schema.json")
EXAMPLE = Path("cdlp/shared/examples/relationships.json")


def rels(*pairs: str) -> list[dict]:
    """rels("a>b", "b>c") -> relationships with ids r1, r2, ..."""
    out = []
    for n, pair in enumerate(pairs, start=1):
        source, target = pair.split(">")
        out.append({"id": f"r{n}", "source": source, "target": target})
    return out


def test_empty():
    assert graph_labels([]) == []


def test_chain_is_ok():
    assert graph_labels(rels("trees>bt", "bt>bst", "bst>avl")) == ["ok", "ok", "ok"]


def test_self_loop():
    assert graph_labels(rels("a>a", "a>b")) == ["self_loop", "ok"]


def test_duplicate_keeps_first_copy():
    assert graph_labels(rels("a>b", "b>c", "a>b")) == ["ok", "ok", "duplicate"]


def test_contradiction_labels_both_edges():
    assert graph_labels(rels("a>b", "b>a", "b>c")) == ["contradiction", "contradiction", "ok"]


def test_duplicate_of_contradiction_edge():
    assert graph_labels(rels("a>b", "a>b", "b>a")) == [
        "contradiction",
        "duplicate",
        "contradiction",
    ]


def test_cycle_of_three():
    assert graph_labels(rels("a>b", "b>c", "c>a", "c>d")) == ["cycle", "cycle", "cycle", "ok"]


def test_cycle_through_contradiction_pair():
    # b>c and c>a only close a cycle by going through the a<->b contradiction.
    labels = graph_labels(rels("a>b", "b>a", "b>c", "c>a"))
    assert labels == ["contradiction", "contradiction", "cycle", "cycle"]


def test_redundant_shortcut():
    # trees>avl is implied by trees>bt>bst>avl.
    labels = graph_labels(rels("trees>bt", "bt>bst", "bst>avl", "trees>avl"))
    assert labels == ["ok", "ok", "ok", "redundant"]


def test_redundant_via_branching_paths():
    # a>d is implied by a>b>d (and a>c>d); the diamond edges themselves are needed.
    labels = graph_labels(rels("a>b", "a>c", "b>d", "c>d", "a>d"))
    assert labels == ["ok", "ok", "ok", "ok", "redundant"]


def test_cycle_edges_do_not_make_others_redundant():
    # x>z would be implied by x>y>z only if the y<->z contradiction were trusted.
    labels = graph_labels(rels("x>y", "y>z", "z>y", "x>z"))
    assert labels == ["ok", "contradiction", "contradiction", "ok"]


def test_duplicate_does_not_make_edge_redundant():
    assert graph_labels(rels("a>b", "a>b")) == ["ok", "duplicate"]


def test_shared_example_has_no_structural_problem():
    # The planted bad edge (graphs -> avl_tree) is a semantic error, not a structural one,
    # so the graph check alone must not catch it.
    relationships = json.loads(EXAMPLE.read_text())["relationships"]
    assert set(graph_labels_by_id(relationships).values()) == {"ok"}


def test_labels_are_allowed_by_schema():
    schema = json.loads(SCHEMA.read_text())
    allowed = set(
        schema["properties"]["edges"]["items"]["properties"]["checks"]["properties"]["graph"][
            "enum"
        ]
    )
    labels = graph_labels(
        rels("a>a", "a>b", "a>b", "b>a", "c>d", "d>e", "e>c", "f>g", "g>h", "f>h")
    )
    assert set(labels) == allowed


def test_by_id():
    assert graph_labels_by_id(rels("a>b", "b>c", "a>c")) == {
        "r1": "ok",
        "r2": "ok",
        "r3": "redundant",
    }
