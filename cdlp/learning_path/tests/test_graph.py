"""Tests for the CDLP knowledge graph module.

Owner: Vaidehi (inherited from Shrestha).
"""

from __future__ import annotations

import pytest

from cdlp.learning_path.graph import (
    dependents,
    generic_path,
    is_dag,
    load_graph,
    prerequisites,
)
from cdlp.shared.io import EXAMPLES, read_json

try:
    import networkx as nx
except ImportError:
    nx = None


@pytest.fixture
def graph():
    data = read_json(EXAMPLES / "validated_graph.json")
    return load_graph(data)


def test_graph_is_directed(graph):
    if nx is not None and isinstance(graph, nx.DiGraph):
        assert isinstance(graph, nx.DiGraph)
    assert hasattr(graph, "add_edge")
    assert is_dag(graph)


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


def test_unknown_concept(graph):
    with pytest.raises(ValueError, match="Unknown concept"):
        prerequisites(graph, "quantum_computing")


def test_evaluate_rq2_and_rq4():
    from cdlp.discovery.quiz import get_quiz_items
    from cdlp.discovery.sim_students import generate_simulated_students
    from cdlp.learning_path.evaluate import evaluate_rq2_and_rq4

    data = read_json(EXAMPLES / "validated_graph.json")
    sim = generate_simulated_students(data, num_students=10, seed=123)
    quiz = get_quiz_items(course_id="ds101")

    res = evaluate_rq2_and_rq4(data, quiz["items"], sim["students"], target="avl_tree")
    assert res["num_students"] == 10
    assert "rq2_diagnosis" in res
    assert "rq4_learning_path" in res
    assert res["rq4_learning_path"]["total_order_mistakes"] == 0
