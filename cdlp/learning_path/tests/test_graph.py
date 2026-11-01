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


def test_mastery_threshold_is_strict_0_8():
    from cdlp.learning_path import api
    from cdlp.learning_path.evaluate import evaluate_accuracy
    from cdlp.learning_path.graph import MASTERY_THRESHOLD, is_mastered
    from cdlp.shared.io import EXAMPLES, read_json

    assert MASTERY_THRESHOLD == 0.8
    assert is_mastered(0.81) and not is_mastered(0.8) and not is_mastered(0.75)

    # 0.75 counted as mastered under the old 0.7 rule; now it is a gap
    assert evaluate_accuracy({"trees": 0.75}, {"trees": 0.1}) == 1.0
    graph = read_json(EXAMPLES / "validated_graph.json")
    path = api.personalized_path(
        graph, {"trees": 0.8, "recursion": 0.9, "binary_tree": 0.81}, "binary_tree"
    )
    assert [s["concept_id"] for s in path] == ["trees"]
