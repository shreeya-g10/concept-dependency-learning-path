"""The second-question strategy in evaluate.py."""

import random

from cdlp.learning_path import evaluate
from cdlp.shared.io import EXAMPLES, read_json

GRAPH = read_json(EXAMPLES / "validated_graph.json")
ITEMS = read_json(EXAMPLES / "quiz_items.json")["items"]
PATH = ["recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"]


def test_with_one_item_per_concept_it_is_plain_adaptive():
    truth = {c: 0.9 for c in PATH[:2]}
    plain = evaluate.run_adaptive_diagnosis(GRAPH, ITEMS, truth, "avl_tree", rng=random.Random(3))
    second = evaluate.run_second_question_diagnosis(
        GRAPH, ITEMS, truth, "avl_tree", rng=random.Random(3)
    )
    assert plain == second


def test_right_then_wrong_ends_as_not_known(monkeypatch):
    answers = iter([True, False])
    monkeypatch.setattr(evaluate, "simulate_student_answer", lambda rng, m: next(answers, False))
    items = evaluate.with_second_items(ITEMS)
    estimate, _ = evaluate.run_second_question_diagnosis(GRAPH, items, {}, "avl_tree")
    assert estimate["__observed__"]["binary_tree"] is False  # the middle of the chain, asked first


def test_the_limit_also_stops_a_second_question():
    items = evaluate.with_second_items(ITEMS)
    truth = {c: 0.9 for c in PATH}
    _, asked = evaluate.run_second_question_diagnosis(
        GRAPH, items, truth, "avl_tree", max_questions=1
    )
    assert asked == 1
