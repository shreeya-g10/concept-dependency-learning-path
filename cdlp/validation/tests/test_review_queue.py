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


def test_cycle_edge_scores_zero_and_says_why():
    vg = graph(*CHAIN, edge("loop", "c", "a", "HUMAN_REVIEW"))
    row = rq.build_review_queue(vg, students(NOBODY))["queue"][0]
    assert row["paths_affected"] == 0 and row["impact_score"] == 0
    assert "cycle" in row["reason"]


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
    assert written["schema_version"] == "1.1" and written["course_id"] == "ds101"
    # r5 trees -> graphs: graphs is not on the way to avl_tree, so no path changes
    assert [(r["edge_id"], r["paths_affected"]) for r in written["queue"]] == [("r5", 0)]
    assert "target: avl_tree" in written["queue"][0]["reason"]
