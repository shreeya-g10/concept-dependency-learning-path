"""Impact-ranked review queue on hand-made graphs. No LLM call (llm.chat is made to fail)."""

import json
from pathlib import Path

import pytest

from cdlp.shared import llm
from cdlp.validation import review_queue as rq

EXAMPLES = Path(__file__).resolve().parents[2] / "shared" / "examples"


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the review queue must not call an LLM")

    monkeypatch.setattr(llm, "chat", fail)
    monkeypatch.setattr(llm, "chat_json", fail)


def edge(eid, source, target, decision="ACCEPT", **extra):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "decision": decision,
        "confidence": 0.5,
        "checks": {"evidence": "medium", "semantic": "medium", "necessity": "weak", "graph": "ok"},
        "evidence": [],
        "reason": "Unsure.",
        **extra,
    }


def graph(*edges):
    nodes = sorted({c for e in edges for c in (e["source"], e["target"])})
    return {
        "schema_version": "1.0",
        "course_id": "toy",
        "nodes": [{"id": n, "name": n.upper()} for n in nodes],
        "edges": list(edges),
    }


def students(*masteries):
    return {
        "schema_version": "1.0",
        "course_id": "toy",
        "students": [{"student_id": f"s{i}", "mastery": m} for i, m in enumerate(masteries)],
    }


# a -> b -> c accepted; target c by default (most ancestors)
CHAIN = [edge("e1", "a", "b"), edge("e2", "b", "c")]
NOBODY = {}
KNOWS_X = {"x": 0.9}
KNOWS_ALL = {"a": 0.95, "b": 0.95, "c": 0.95, "x": 0.95}


def test_path_rule_ancestors_minus_mastered_in_topological_order():
    g = rq.accepted_graph(graph(*CHAIN, edge("e3", "x", "c")))
    assert rq.personalized_path(g, {}, "c") == ["a", "b", "x", "c"]
    assert rq.personalized_path(g, {"a": 0.9, "x": 0.81}, "c") == ["b", "c"]
    # the threshold is strict: exactly 0.8 is not mastered
    assert rq.personalized_path(g, {"a": 0.8}, "c") == ["a", "b", "x", "c"]
    assert rq.personalized_path(g, {"c": 0.9, "a": 0.9, "b": 0.9, "x": 0.9}, "c") == []


def test_non_accepted_edges_are_not_in_the_base_graph():
    g = rq.accepted_graph(
        graph(*CHAIN, edge("r", "x", "b", "REJECT"), edge("h", "y", "b", "HUMAN_REVIEW"))
    )
    assert set(g.edges) == {("a", "b"), ("b", "c")}
    assert {"x", "y"} <= set(g.nodes)


def test_default_target_has_most_ancestors():
    assert rq.default_target(rq.accepted_graph(graph(*CHAIN))) == "c"
    with pytest.raises(ValueError):
        rq.default_target(rq.accepted_graph(graph(edge("h", "a", "b", "HUMAN_REVIEW"))))


def test_impact_counts_students_whose_path_changes():
    vg = graph(*CHAIN, edge("h1", "x", "b", "HUMAN_REVIEW"))
    queue = rq.build_review_queue(vg, students(NOBODY, KNOWS_X, KNOWS_ALL))["queue"]

    # only the student who doesn't know x gets a longer path
    assert queue == [
        {
            "edge_id": "h1",
            "source": "x",
            "target": "b",
            "blocking": False,
            "impact_score": pytest.approx(1 / 3, abs=1e-4),
            "paths_affected": 1,
            "reason": queue[0]["reason"],
        }
    ]
    assert "changes 1 of 3 learning paths (target: c)" in queue[0]["reason"]
    assert "necessity weak" in queue[0]["reason"]


def test_edges_that_change_no_path_score_zero():
    vg = graph(
        *CHAIN,
        edge("shortcut", "a", "c", "HUMAN_REVIEW"),  # already implied by a -> b -> c
        edge("elsewhere", "c", "y", "HUMAN_REVIEW"),  # y is not on the way to c
    )
    queue = rq.build_review_queue(vg, students(NOBODY, KNOWS_X))["queue"]
    assert {row["edge_id"]: row["paths_affected"] for row in queue} == {
        "shortcut": 0,
        "elsewhere": 0,
    }


def test_order_change_alone_counts_as_a_changed_path():
    vg = graph(edge("e1", "a", "c"), edge("e2", "b", "c"), edge("h", "b", "a", "HUMAN_REVIEW"))
    g = rq.accepted_graph(vg)
    assert rq.personalized_path(g, {}, "c") == ["a", "b", "c"]
    assert rq.build_review_queue(vg, students(NOBODY))["queue"][0]["paths_affected"] == 1


def test_cycle_edge_is_blocking_with_null_impact():
    vg = graph(
        *CHAIN, edge("loop", "c", "a", "HUMAN_REVIEW"), edge("self", "b", "b", "HUMAN_REVIEW")
    )
    queue = rq.build_review_queue(vg, students(NOBODY))["queue"]
    for row in queue:
        assert row["blocking"] is True
        # the flipped path is undefined: null, never a made-up 0
        assert row["paths_affected"] is None and row["impact_score"] is None
        assert "BLOCKING" in row["reason"] and "cycle" in row["reason"]


def test_blocking_edges_come_before_every_impact_ranked_edge(tmp_path):
    vg = graph(
        *CHAIN,
        edge("h_high", "x", "b", "HUMAN_REVIEW"),  # changes every path
        edge("z_loop", "c", "a", "HUMAN_REVIEW"),  # blocking, sorts after h_high by id
        edge("a_loop", "b", "a", "HUMAN_REVIEW"),  # blocking
        edge("h_zero", "a", "c", "HUMAN_REVIEW"),
    )
    out = tmp_path / "review_queue.json"
    queue = rq.write_review_queue(out, vg, students(NOBODY))["queue"]  # schema-validated
    assert [(r["edge_id"], r["blocking"]) for r in queue] == [
        ("a_loop", True),
        ("z_loop", True),
        ("h_high", False),
        ("h_zero", False),
    ]
    assert queue[2]["impact_score"] == 1.0


def test_schema_allows_null_impact_only_for_blocking_edges():
    from cdlp.shared.validate import check

    row = {
        "edge_id": "e",
        "source": "a",
        "target": "b",
        "paths_affected": None,
        "impact_score": None,
        "reason": "r",
    }
    doc = {"schema_version": "1.4", "course_id": "toy", "queue": [row]}
    assert check(doc, "review_queue")  # null impact without blocking: invalid
    assert not check({**doc, "queue": [{**row, "blocking": True}]}, "review_queue")
    assert check({**doc, "queue": [{**row, "blocking": False}]}, "review_queue")
    # a 1.1 row (no blocking field, numeric impact) stays valid
    old = {**row, "paths_affected": 0, "impact_score": 0.05}
    assert not check({**doc, "schema_version": "1.1", "queue": [old]}, "review_queue")


def test_queue_is_sorted_by_impact_then_id():
    vg = graph(
        *CHAIN,
        edge("h_low", "y", "b", "HUMAN_REVIEW"),
        edge("h_high", "x", "b", "HUMAN_REVIEW"),
        edge("h_zero", "a", "c", "HUMAN_REVIEW"),
        edge("h_tie", "z", "b", "HUMAN_REVIEW"),
    )
    # nobody knows x; one student knows y and z
    queue = rq.build_review_queue(vg, students(NOBODY, {"y": 0.9, "z": 0.9}))["queue"]
    assert [row["edge_id"] for row in queue] == ["h_high", "h_low", "h_tie", "h_zero"]
    assert [row["paths_affected"] for row in queue] == [2, 1, 1, 0]


def test_several_targets_count_every_student_target_path():
    vg = graph(*CHAIN, edge("e3", "c", "d"), edge("h", "x", "b", "HUMAN_REVIEW"))
    row = rq.build_review_queue(vg, students(NOBODY, KNOWS_X), targets=["c", "d"])["queue"][0]
    assert row["paths_affected"] == 2  # student 0, for both targets
    assert row["impact_score"] == 0.5
    assert "target: c, d" in row["reason"]


def test_example_data_matches_the_contract(tmp_path):
    vg = json.loads((EXAMPLES / "validated_graph.json").read_text())
    sims = json.loads((EXAMPLES / "sim_students.json").read_text())
    out = tmp_path / "review_queue.json"
    written = rq.write_review_queue(out, vg, sims)  # validated against the schema

    assert json.loads(out.read_text()) == written
    assert written["schema_version"] == "1.4" and written["course_id"] == "ds101"
    # r5 trees -> graphs: graphs is not on the way to avl_tree, so no path changes
    assert [(r["edge_id"], r["paths_affected"]) for r in written["queue"]] == [("r5", 0)]
    assert "target: avl_tree" in written["queue"][0]["reason"]


# ---- pinned to cdlp/learning_path/api.py --------------------------------------
# Test-only import: the module itself never imports learning_path. If api.py's rule
# changes, this test fails and rq.personalized_path must follow (module docstring).
PIN_GRAPHS = {
    "chain": [("a", "b"), ("b", "c"), ("c", "d")],
    "diamond": [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
    "two_roots": [("x", "c"), ("a", "b"), ("b", "c"), ("c", "d")],
    "wide": [("a", "e"), ("b", "e"), ("c", "e"), ("d", "e"), ("a", "b")],
}
PIN_MASTERIES = [
    {},
    {"a": 0.9},
    {"a": 0.8, "b": 0.81},  # 0.8 is not mastered, 0.81 is
    {"b": 0.95, "c": 0.1},
    {"a": 0.9, "b": 0.9, "c": 0.9, "d": 0.9, "e": 0.9, "x": 0.9},
    {"d": 0.85},  # the target itself mastered
]


def _is_topological(order, pairs):
    position = {c: i for i, c in enumerate(order)}
    return all(position[u] < position[v] for u, v in pairs if u in position and v in position)


@pytest.mark.parametrize("name", sorted(PIN_GRAPHS))
@pytest.mark.parametrize("mastery", PIN_MASTERIES, ids=range(len(PIN_MASTERIES)))
def test_path_rule_matches_learning_path_api(name, mastery):
    from cdlp.learning_path import api

    pairs = PIN_GRAPHS[name]
    vg = graph(*(edge(f"e{i}", u, v) for i, (u, v) in enumerate(pairs)))
    goal = rq.default_target(rq.accepted_graph(vg))
    theirs = [step["concept_id"] for step in api.personalized_path(vg, mastery, goal)]
    ours = rq.personalized_path(rq.accepted_graph(vg), mastery, goal)

    assert set(ours) == set(theirs)  # same concepts: ancestors + target - mastered
    assert _is_topological(ours, pairs) and _is_topological(theirs, pairs)
    if name == "chain":  # a unique topological order: identical paths
        assert ours == theirs
