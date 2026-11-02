"""Teacher decisions on HUMAN_REVIEW edges (cdlp/validation/apply_review.py). No LLM."""

import copy
import json
import subprocess
import sys

import networkx as nx
import pytest

from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check_file
from cdlp.validation.apply_review import apply_decisions, main, record_decision, reset


def edge(eid, source, target, decision="HUMAN_REVIEW"):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "decision": decision,
        "confidence": 0.5,
        "checks": {"evidence": "weak", "semantic": "medium", "necessity": "weak", "graph": "ok"},
        "evidence": [],
        "reason": "validator unsure",
    }


def graph(*edges):
    nodes = sorted({n for e in edges for n in (e["source"], e["target"])})
    return {
        "schema_version": "1.5",
        "course_id": "ds101",
        "nodes": [{"id": n, "name": n} for n in nodes],
        "edges": list(edges),
    }


def decision(eid, source, target, verdict, at="2026-11-02T10:00:00+00:00", **extra):
    return {
        "edge_id": eid,
        "source": source,
        "target": target,
        "decision": verdict,
        "decided_by": "teacher",
        "decided_at": at,
        **extra,
    }


def by_id(g):
    return {e["id"]: e for e in g["edges"]}


# a -> b -> c accepted; c -> a would close a cycle; a -> c and d -> a are free
BASE = graph(
    edge("e1", "a", "b", "ACCEPT"),
    edge("e2", "b", "c", "ACCEPT"),
    edge("e3", "c", "a"),
    edge("e4", "a", "c"),
    edge("e5", "d", "a"),
    edge("e6", "x", "y", "REJECT"),
)


def test_accept_and_reject_are_applied_and_marked_as_teacher_decisions():
    decisions = [
        decision("e4", "a", "c", "REJECT", comment="redundant"),
        decision("e5", "d", "a", "ACCEPT"),
    ]
    out, report = apply_decisions(BASE, decisions)
    edges = by_id(out)
    assert edges["e4"]["decision"] == "REJECT" and edges["e5"]["decision"] == "ACCEPT"
    assert edges["e5"]["review"] == {
        "decided_by": "teacher",
        "decision": "ACCEPT",
        "validator_decision": "HUMAN_REVIEW",
        "status": "applied",
        "decided_at": "2026-11-02T10:00:00+00:00",
    }
    assert edges["e4"]["review"]["comment"] == "redundant"
    for key in ("confidence", "checks", "evidence", "reason"):  # validator's fields kept
        assert edges["e5"][key] == by_id(BASE)["e5"][key]
    assert [r["status"] for r in report] == ["applied", "applied"]
    assert out["schema_version"] == "1.6"
    assert "review" not in by_id(BASE)["e5"]  # input not modified


def test_an_accept_that_closes_a_cycle_is_refused_and_the_graph_stays_a_dag():
    out, report = apply_decisions(BASE, [decision("e3", "c", "a", "ACCEPT")])
    e3 = by_id(out)["e3"]
    assert e3["decision"] == "HUMAN_REVIEW"
    assert e3["review"]["status"] == "refused_cycle"
    assert e3["review"]["cycle"] == ["c", "a", "b", "c"]
    assert report[0]["status"] == "refused_cycle"
    accepted = nx.DiGraph(
        (e["source"], e["target"]) for e in out["edges"] if e["decision"] == "ACCEPT"
    )
    assert nx.is_directed_acyclic_graph(accepted)


def test_an_earlier_teacher_accept_counts_for_later_cycle_checks():
    g = graph(edge("e1", "a", "b"), edge("e2", "b", "a"))
    first = decision("e1", "a", "b", "ACCEPT", at="2026-11-02T10:00:00+00:00")
    second = decision("e2", "b", "a", "ACCEPT", at="2026-11-02T11:00:00+00:00")
    out, _ = apply_decisions(g, [second, first])  # applied in decided_at order
    assert by_id(out)["e1"]["decision"] == "ACCEPT"
    assert by_id(out)["e2"]["review"]["status"] == "refused_cycle"


def test_a_self_loop_is_never_accepted():
    out, _ = apply_decisions(graph(edge("e1", "a", "a")), [decision("e1", "a", "a", "ACCEPT")])
    assert by_id(out)["e1"]["decision"] == "HUMAN_REVIEW"


def test_only_human_review_edges_can_be_decided():
    decisions = [
        decision("e6", "x", "y", "ACCEPT"),  # validator REJECT
        decision("e1", "a", "b", "REJECT"),  # validator ACCEPT
        decision("zz", "p", "q", "ACCEPT"),  # not in the graph
    ]
    out, report = apply_decisions(BASE, decisions)
    assert [r["status"] for r in report] == ["not_human_review", "not_human_review", "unknown_edge"]
    assert by_id(out)["e6"]["decision"] == "REJECT" and by_id(out)["e1"]["decision"] == "ACCEPT"


def test_reapplying_changes_nothing_and_a_new_decision_replaces_the_old():
    once, _ = apply_decisions(BASE, [decision("e5", "d", "a", "ACCEPT")])
    twice, _ = apply_decisions(once, [decision("e5", "d", "a", "ACCEPT")])
    assert once == twice
    flipped, _ = apply_decisions(once, [decision("e5", "d", "a", "REJECT")])
    assert by_id(flipped)["e5"]["decision"] == "REJECT"
    assert reset(flipped)["edges"] == BASE["edges"]


def test_decisions_follow_an_edge_whose_id_changed():
    renumbered = copy.deepcopy(BASE)
    by_id(renumbered)["e5"]["id"] = "r99"
    out, report = apply_decisions(renumbered, [decision("e5", "d", "a", "ACCEPT")])
    assert by_id(out)["r99"]["decision"] == "ACCEPT" and report[0]["edge_id"] == "r99"


def test_record_decision_keeps_one_row_per_edge():
    e5 = by_id(BASE)["e5"]
    doc = record_decision({"course_id": "ds101", "decisions": []}, e5, "ACCEPT", "  ")
    doc = record_decision(doc, e5, "REJECT", "changed my mind", decided_at="t2")
    assert [(d["decision"], d.get("comment")) for d in doc["decisions"]] == [
        ("REJECT", "changed my mind")
    ]
    with pytest.raises(ValueError):
        record_decision(doc, e5, "MAYBE")


# --- CLI, contract and examples -----------------------------------------------------


def test_cli_records_applies_and_rebuilds_the_queue(tmp_path, capsys):
    g = read_json(EXAMPLES / "validated_graph.json")
    (tmp_path / "validated_graph.json").write_text(json.dumps(g))
    args = [
        *["--graph", str(tmp_path / "validated_graph.json")],
        *["--decisions", str(tmp_path / "review_decisions.json")],
        *["--students", str(EXAMPLES / "sim_students.json")],
        *["--queue", str(tmp_path / "review_queue.json")],
    ]
    main([*args, "--decide", "r5", "REJECT", "--comment", "not needed"])
    for name in ["validated_graph.json", "review_decisions.json", "review_queue.json"]:
        assert check_file(tmp_path / name) == [], name
    out = read_json(tmp_path / "validated_graph.json")
    assert by_id(out)["r5"]["decision"] == "REJECT"
    assert by_id(out)["r5"]["review"]["comment"] == "not needed"
    assert read_json(tmp_path / "review_queue.json")["queue"] == []  # nothing left waiting
    assert "r5 trees -> graphs: REJECT applied" in capsys.readouterr().out

    main([*args, "--decide", "r5", "ACCEPT"])  # a teacher-decided edge can be re-decided
    assert by_id(read_json(tmp_path / "validated_graph.json"))["r5"]["decision"] == "ACCEPT"
    assert len(read_json(tmp_path / "review_decisions.json")["decisions"]) == 1


def test_cli_refuses_to_decide_an_edge_the_validator_decided(tmp_path):
    (tmp_path / "validated_graph.json").write_text((EXAMPLES / "validated_graph.json").read_text())
    with pytest.raises(SystemExit):
        main(
            [
                *["--graph", str(tmp_path / "validated_graph.json")],
                *["--decisions", str(tmp_path / "review_decisions.json")],
                *["--decide", "r1", "REJECT"],
            ]
        )
    assert not (tmp_path / "review_decisions.json").exists()


def test_cli_runs_as_a_module(tmp_path):
    (tmp_path / "validated_graph.json").write_text((EXAMPLES / "validated_graph.json").read_text())
    result = subprocess.run(
        [
            *[sys.executable, "-m", "cdlp.validation.apply_review"],
            *["--graph", str(tmp_path / "validated_graph.json")],
            *["--decisions", str(tmp_path / "review_decisions.json")],
            *["--decide", "r5", "ACCEPT"],
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "r5 trees -> graphs: ACCEPT applied" in result.stdout


def test_reviewed_example_is_the_example_decisions_applied_to_the_example_graph():
    decisions = read_json(EXAMPLES / "review_decisions.json")["decisions"]
    out, _ = apply_decisions(read_json(EXAMPLES / "validated_graph.json"), decisions)
    assert out == read_json(EXAMPLES / "reviewed_validated_graph.json")
