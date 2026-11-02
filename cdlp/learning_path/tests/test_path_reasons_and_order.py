"""The sorted tie-break in generic_path, the reasons in personalized_path, the question limit."""

import json
import os
import subprocess
import sys

import pytest

from cdlp.learning_path import api, evaluate, graph
from cdlp.shared.io import EXAMPLES, read_json

GRAPH = read_json(EXAMPLES / "validated_graph.json")
NODES = [
    {"id": "binary_tree", "name": "Binary Tree"},
    {"id": "hash_map", "name": "Hash Map"},
    {"id": "stack", "name": "Stack"},
    {"id": "goal", "name": "The Goal"},
]


def edge(source, target, strength="hard"):
    return {"source": source, "target": target, "decision": "ACCEPT", "strength": strength}


TIES = {
    "nodes": NODES,
    "edges": [edge("stack", "goal"), edge("hash_map", "goal"), edge("binary_tree", "goal")],
}
PRINT_ORDER = """
import json, sys
from cdlp.learning_path import api
print(json.dumps(api.prerequisite_order(json.loads(sys.argv[1]), "goal")))
"""


@pytest.mark.parametrize("seed", ["0", "1", "6", "12345"])
def test_ties_are_sorted_under_any_hash_seed(seed):
    env = {**os.environ, "PYTHONHASHSEED": seed}
    run = subprocess.run(
        [sys.executable, "-c", PRINT_ORDER, json.dumps(TIES)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert json.loads(run.stdout) == ["binary_tree", "hash_map", "stack", "goal"]


def test_a_link_still_beats_the_sorted_order():
    linked = {"nodes": NODES, "edges": [edge("stack", "binary_tree"), edge("binary_tree", "goal")]}
    assert api.prerequisite_order(linked, "goal") == ["stack", "binary_tree", "goal"]


def test_the_version_without_networkx_gives_the_same_order(monkeypatch):
    expected = api.prerequisite_order(TIES, "goal")
    monkeypatch.setattr(graph, "nx", None)
    assert graph.generic_path(graph.load_graph(TIES), "goal") == expected


def why(graph_data, mastery=None, target="goal"):
    steps = api.personalized_path(graph_data, mastery or {}, target)
    return {step["concept_id"]: step["why"] for step in steps}


def test_a_reason_names_what_the_topic_is_needed_for_not_what_it_needs():
    chain = {"nodes": NODES, "edges": [edge("stack", "binary_tree"), edge("binary_tree", "goal")]}
    assert why(chain) == {
        "stack": "You need this before Binary Tree.",
        "binary_tree": "You need this before The Goal.",
        "goal": "This is the topic you want to learn.",
    }


def test_a_soft_link_says_helps():
    soft = {"nodes": NODES, "edges": [edge("stack", "goal", "soft")]}
    assert why(soft)["stack"] == "This helps you learn The Goal."


def test_a_known_topic_in_between_is_not_named():
    chain = {"nodes": NODES, "edges": [edge("stack", "binary_tree"), edge("binary_tree", "goal")]}
    assert why(chain, {"binary_tree": 0.9})["stack"] == "This leads to The Goal."


def test_no_reason_shows_a_raw_id_even_without_a_name_in_the_graph():
    nameless = {"nodes": [], "edges": [edge("binary_tree", "avl_tree")]}
    assert why(nameless, target="avl_tree")["binary_tree"] == "You need this before Avl tree."
    for reason in why(GRAPH, target="avl_tree").values():
        assert "_" not in reason


def test_only_answered_keeps_direct_answers_and_forgets_inferred_ones():
    mastery = api.update_mastery(GRAPH, {}, "binary_search_tree", True)
    assert mastery["trees"] == 0.85  # inferred from the right answer
    kept = api.only_answered(mastery)
    assert kept["binary_search_tree"] == 0.9
    assert "trees" not in kept
    on_plan = {s["concept_id"] for s in api.personalized_path(GRAPH, kept, "binary_search_tree")}
    assert on_plan == {"trees", "binary_tree", "recursion"}


WIDE = {
    "nodes": [{"id": f"p{i:02}", "name": f"P {i}"} for i in range(15)],
    "edges": [edge(f"p{i:02}", "goal") for i in range(15)],
}
WIDE_ITEMS = [{"id": f"q{i:02}", "concept_id": f"p{i:02}"} for i in range(15)]


def test_adaptive_diagnosis_stops_at_the_limit():
    assert api.MAX_QUESTIONS_PER_TOPIC == 10
    truth = {f"p{i:02}": 0.9 for i in range(15)}
    _, asked = evaluate.run_adaptive_diagnosis(WIDE, WIDE_ITEMS, truth, "goal")
    assert asked == 10
