"""RQ2 fairness: one estimator, one scored set, direct answers never erased."""

import random

from cdlp.learning_path import api, evaluate
from cdlp.learning_path.graph import is_mastered
from cdlp.learning_path.sim_students import (
    generate_independent_students,
    generate_simulated_students,
)
from cdlp.shared.io import EXAMPLES, read_json

GRAPH = read_json(EXAMPLES / "validated_graph.json")
QUIZ = read_json(EXAMPLES / "quiz_items.json")["items"]


def test_wrong_answer_does_not_erase_a_direct_correct_answer():
    m = api.update_mastery(GRAPH, {}, "binary_tree", True)
    m = api.update_mastery(GRAPH, m, "binary_search_tree", False)
    assert m["binary_tree"] == 0.9  # was reset to 0.5 before the fix
    assert m["trees"] == 0.5  # inferred only, so it becomes uncertain again
    assert m["__observed__"] == {"binary_tree": True, "binary_search_tree": False}


def test_correct_answer_does_not_lift_a_direct_wrong_answer():
    m = api.update_mastery(GRAPH, {}, "trees", False)
    m = api.update_mastery(GRAPH, m, "binary_tree", True)
    assert m["trees"] == 0.1  # was lifted to 0.85 before the fix
    assert m["recursion"] == 0.85


def test_latest_direct_answer_wins_and_asked_is_kept():
    m = api.update_mastery(GRAPH, {"__asked__": ["q1"]}, "trees", False)
    m = api.update_mastery(GRAPH, m, "trees", True)
    assert m["trees"] == 0.9 and m["__asked__"] == ["q1"]


def test_ask_all_is_perfect_without_answer_noise(monkeypatch):
    """With noiseless answers, asking every concept must recover the truth exactly."""
    monkeypatch.setattr(evaluate, "simulate_student_answer", lambda rng, m, **kw: is_mastered(m))
    students = generate_independent_students(GRAPH, num_students=30, seed=1)["students"]
    res = evaluate.evaluate_rq2_and_rq4(GRAPH, QUIZ, students, target="avl_tree")
    assert res["rq2_diagnosis"]["ask_all"]["accuracy"] == 1.0


def test_same_scored_set_for_every_strategy():
    path = ["recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"]
    truth = {c: 0.9 for c in path}
    # an estimate that covers only one concept is scored on all five (others at 0.5)
    assert evaluate.evaluate_accuracy({"trees": 0.9}, truth, path) == 0.2


def test_results_do_not_depend_on_strategy_order():
    students = generate_simulated_students(GRAPH, num_students=20, seed=3)["students"]
    a = evaluate.evaluate_rq2_and_rq4(GRAPH, QUIZ, students, target="avl_tree")
    random.seed(999)  # global RNG state must not matter either
    b = evaluate.evaluate_rq2_and_rq4(GRAPH, QUIZ, students, target="avl_tree")
    assert a == b


def test_independent_students_violate_the_graph_far_more_often():
    path = ["recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"]
    graph_students = generate_simulated_students(GRAPH, num_students=200, seed=4)["students"]
    free_students = generate_independent_students(GRAPH, num_students=200, seed=4)["students"]
    assert evaluate.closure_violations(GRAPH, free_students, path) > 0.6
    assert evaluate.closure_violations(GRAPH, graph_students, path) < 0.3
