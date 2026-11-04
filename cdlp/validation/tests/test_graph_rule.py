"""order_rule_v2: which links count in the graph check, and that the accepted graph is a DAG."""

from __future__ import annotations

import json
import random
from pathlib import Path

import networkx as nx
import pytest

from cdlp.validation import __main__ as validation
from cdlp.validation import apply_review, evidence_check, semantic_check
from cdlp.validation.graph_checks import graph_labels, graph_labels_by_id

GRADES = ("strong", "medium", "weak", "none")
RULE = Path(validation.__file__).parents[1] / "discovery" / "configs" / "order_rule_v2.json"


def rels(*pairs):
    return [{"id": f"r{i}", "source": p[0], "target": p[-1]} for i, p in enumerate(pairs)]


def edge(eid, source, target, **extra):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "confidence": 0.9,
        "evidence": [],
        **extra,
    }


def graded(monkeypatch, grade_of):
    """grade_of(link id) -> (evidence, semantic): no LLM anywhere."""

    def evidence_run(relationships, *args, **kwargs):
        return {
            "results": [
                {"relationship_id": r["id"], "evidence": grade_of(r["id"])[0], "quotes": []}
                for r in relationships["relationships"]
            ]
        }

    def semantic_run(relationships, *args, **kwargs):
        return {
            "results": [
                {"relationship_id": r["id"], "semantic": grade_of(r["id"])[1], "rationale": ""}
                for r in relationships["relationships"]
            ]
        }

    monkeypatch.setattr(evidence_check, "run", evidence_run)
    monkeypatch.setattr(semantic_check, "run", semantic_run)


def run(links, **kwargs):
    nodes = sorted({n for link in links for n in (link["source"], link["target"])})
    return validation.validate(
        {"schema_version": "1.14", "course_id": "t", "relationships": links},
        {"concepts": [{"id": n, "name": n} for n in nodes]},
        [],
        skip=kwargs.pop("skip", {"necessity"}),
        **kwargs,
    )


def by_id(graph):
    return {e["id"]: e for e in graph["edges"]}


def accepted(graph):
    return nx.DiGraph(
        (e["source"], e["target"]) for e in graph["edges"] if e["decision"] == "ACCEPT"
    )


# --- the labels ----------------------------------------------------------------------
def test_a_link_left_out_cannot_put_others_on_a_cycle():
    links = rels("a>b", "b>c", "c>a")
    assert graph_labels_by_id(links) == {"r0": "cycle", "r1": "cycle", "r2": "cycle"}
    assert graph_labels_by_id(links, {"r2"}) == {"r0": "ok", "r1": "ok", "r2": "cycle"}


def test_a_link_left_out_cannot_make_another_redundant():
    links = rels("a>b", "b>c", "a>c")
    assert graph_labels_by_id(links, {"r0"})["r2"] == "ok"
    assert graph_labels_by_id(links, {"r2"}) == {"r0": "ok", "r1": "ok", "r2": "redundant"}


def test_a_bidirectional_flag_also_leaves_a_link_out():
    links = rels("a>b", "b>c", "c>a")
    links[2]["bidirectional"] = True
    assert [graph_labels(links)[i] for i in (0, 1)] == ["ok", "ok"]


def test_a_real_cycle_without_reversed_links_is_still_a_cycle():
    assert graph_labels(rels("a>b", "b>a", "c>d", "d>e", "e>c")) == [
        "contradiction",
        "contradiction",
        "cycle",
        "cycle",
        "cycle",
    ]


# --- the decisions -------------------------------------------------------------------
def test_a_reversed_pair_stays_in_review_and_leaves_the_others_alone(monkeypatch):
    graded(monkeypatch, lambda eid: ("strong", "strong"))
    links = [
        edge("r1", "a", "b", order_agreement="reversed"),
        edge("r2", "b", "a", order_agreement="reversed"),
        edge("r3", "b", "c"),
        edge("r4", "c", "a"),
    ]
    edges = by_id(run(links))
    assert edges["r1"]["decision"] == edges["r2"]["decision"] == "HUMAN_REVIEW"
    assert edges["r3"]["decision"] == edges["r4"]["decision"] == "ACCEPT"


def test_a_link_rejected_on_score_does_not_block_a_cycle_or_a_good_link(monkeypatch):
    graded(monkeypatch, lambda eid: ("none", "none") if eid == "bad" else ("strong", "strong"))
    links = [edge("r1", "a", "b"), edge("r2", "b", "c"), edge("bad", "c", "a")]
    edges = by_id(run(links))
    assert edges["bad"]["decision"] == "REJECT"
    assert edges["r1"]["decision"] == edges["r2"]["decision"] == "ACCEPT"


def test_a_link_rejected_on_score_cannot_make_a_good_link_redundant(monkeypatch):
    graded(monkeypatch, lambda eid: ("none", "none") if eid == "bad" else ("strong", "strong"))
    links = [edge("bad", "a", "b"), edge("r2", "b", "c"), edge("r3", "a", "c")]
    assert by_id(run(links))["r3"]["decision"] == "ACCEPT"


def test_a_link_in_review_on_score_still_counts(monkeypatch):
    # strong + none is review on score: it may be real, so the cycle still stops an accept.
    graded(monkeypatch, lambda eid: ("strong", "none") if eid == "unsure" else ("strong", "strong"))
    links = [edge("r1", "a", "b"), edge("r2", "b", "c"), edge("unsure", "c", "a")]
    edges = by_id(run(links))
    assert edges["unsure"]["decision"] == "HUMAN_REVIEW"
    assert edges["r1"]["decision"] == edges["r2"]["decision"] == "HUMAN_REVIEW"


def test_a_redundant_reason_never_names_a_rejected_path(monkeypatch):
    grades = {"bad": ("none", "none")}
    graded(monkeypatch, lambda eid: grades.get(eid, ("strong", "strong")))
    links = [
        edge("bad", "a", "x"),
        edge("r2", "x", "c"),
        edge("r3", "a", "y"),
        edge("r4", "y", "c"),
        edge("r5", "a", "c"),
    ]
    reason = by_id(run(links))["r5"]["reason"]
    assert "a → y → c" in reason and "x" not in reason.split("implied by")[1]


def test_every_run_records_the_rule_and_the_config_exists(monkeypatch):
    graded(monkeypatch, lambda eid: ("strong", "strong"))
    assert run([edge("r1", "a", "b")])["graph_rule"] == validation.GRAPH_RULE
    assert json.loads(RULE.read_text())["version"] == validation.GRAPH_RULE


# --- the accepted graph must stay a DAG ----------------------------------------------
def random_links(seed):
    rng = random.Random(seed)
    nodes = [f"n{i}" for i in range(rng.randint(3, 12))]
    pairs = {tuple(rng.sample(nodes, 2)) for _ in range(rng.randint(2, 45))}
    grades = {f"r{i}": (rng.choice(GRADES), rng.choice(GRADES)) for i in range(len(pairs))}
    return [edge(f"r{i}", *p) for i, p in enumerate(sorted(pairs))], grades


@pytest.mark.parametrize("seed", range(150))
def test_the_accepted_graph_is_a_dag_with_no_pair_accepted_both_ways(monkeypatch, seed):
    links, grades = random_links(seed)
    graded(monkeypatch, grades.__getitem__)
    graph = run(links)
    kept = accepted(graph)
    assert nx.is_directed_acyclic_graph(kept)
    assert not any(kept.has_edge(v, u) for u, v in kept.edges)
    assert nx.transitive_reduction(kept).number_of_edges() == kept.number_of_edges()


@pytest.mark.parametrize("seed", range(40))
def test_it_stays_a_dag_when_a_teacher_accepts_every_review(monkeypatch, seed):
    links, grades = random_links(seed)
    graded(monkeypatch, grades.__getitem__)
    graph = {**run(links), "schema_version": "1.14"}
    decisions = [
        {
            "edge_id": e["id"],
            "source": e["source"],
            "target": e["target"],
            "decision": "ACCEPT",
            "decided_by": "teacher",
            "decided_at": "2026-11-04T00:00:00+00:00",
        }
        for e in graph["edges"]
        if e["decision"] == "HUMAN_REVIEW"
    ]
    reviewed, _ = apply_review.apply_decisions(graph, decisions)
    assert nx.is_directed_acyclic_graph(accepted(reviewed))


def test_the_skip_graph_ablation_is_the_one_exception(monkeypatch):
    graded(monkeypatch, lambda eid: ("strong", "strong"))
    links = [edge("r1", "a", "b"), edge("r2", "b", "c"), edge("r3", "c", "a")]
    graph = run(links, skip={"necessity", "graph"})
    assert not nx.is_directed_acyclic_graph(accepted(graph))
