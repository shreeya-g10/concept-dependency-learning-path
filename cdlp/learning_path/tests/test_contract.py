
"""Tests for the CDLP knowledge graph module."""

import networkx as nx
import pytest

from cdlp.learning_path.graph import (
    dependents,
    generic_path,
    load_graph,
    prerequisites,
)
from cdlp.shared.io import EXAMPLES, read_json


@pytest.fixture
def graph():
    data = read_json(EXAMPLES / "validated_graph.json")
    return load_graph(data)


def test_graph_is_directed(graph):
    assert isinstance(graph, nx.DiGraph)
    assert nx.is_directed_acyclic_graph(graph)


def test_only_accepted_edges(graph):
    for _, _, data in graph.edges(data=True):
        assert data["decision"] == "ACCEPT"


def test_prerequisites(graph):
    result = prerequisites(graph, "avl_tree")
    assert "binary_search_tree" in result
    assert "binary_tree" in result


def test_dependents(graph):
    result = dependents(graph, "binary_tree")
    assert "avl_tree" in result


def test_generic_path(graph):
    path = generic_path(graph, "avl_tree")

    assert path[-1] == "avl_tree"

    assert set(path) == {
        "trees",
        "recursion",
        "binary_tree",
        "binary_search_tree",
        "avl_tree",
    }

    assert path.index("binary_tree") < path.index(
        "binary_search_tree"
    )
    assert path.index("binary_search_tree") < path.index(
        "avl_tree"
    )


def test_unknown_concept(graph):
    with pytest.raises(ValueError):
        prerequisites(graph, "unknown_concept")
