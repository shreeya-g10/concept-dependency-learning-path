"""A pair discovery proposed in both directions must never end up with two ACCEPT edges."""

from __future__ import annotations

from cdlp.validation import __main__ as validation
from cdlp.validation import apply_review, evidence_check, semantic_check


def edge(eid, source, target):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "confidence": 0.9,
        "evidence": [],
        "order_agreement": "reversed",
    }


def strong_everywhere(monkeypatch):
    """Every check as strong as it can be, so only the graph rule can stop an ACCEPT."""

    def evidence_run(relationships, *args, **kwargs):
        rows = relationships["relationships"]
        return {
            "results": [
                {"relationship_id": r["id"], "evidence": "strong", "quotes": []} for r in rows
            ]
        }

    def semantic_run(relationships, *args, **kwargs):
        rows = relationships["relationships"]
        return {
            "results": [
                {"relationship_id": r["id"], "semantic": "strong", "rationale": ""} for r in rows
            ]
        }

    monkeypatch.setattr(evidence_check, "run", evidence_run)
    monkeypatch.setattr(semantic_check, "run", semantic_run)


def run(rels):
    return validation.validate(
        {"schema_version": "1.11", "course_id": "t", "relationships": rels},
        {"concepts": [{"id": n, "name": n} for n in "xyz"]},
        [],
        skip={"necessity"},
    )


def test_a_reversed_pair_cannot_get_two_accepts(monkeypatch):
    strong_everywhere(monkeypatch)
    edges = run([edge("r1", "x", "y"), edge("r2", "y", "x")])["edges"]
    assert [e["decision"] for e in edges] == ["HUMAN_REVIEW", "HUMAN_REVIEW"]
    assert all(e["checks"]["graph"] == "contradiction" for e in edges)


def test_neither_direction_is_picked_automatically(monkeypatch):
    strong_everywhere(monkeypatch)
    edges = run([edge("r1", "x", "y"), edge("r2", "y", "x"), edge("r3", "z", "x")])["edges"]
    assert "ACCEPT" not in {e["decision"] for e in edges if e["id"] in ("r1", "r2")}
    assert next(e for e in edges if e["id"] == "r3")["decision"] == "ACCEPT"


def test_a_teacher_cannot_accept_both_directions(monkeypatch):
    strong_everywhere(monkeypatch)
    graph = {**run([edge("r1", "x", "y"), edge("r2", "y", "x")]), "schema_version": "1.11"}
    decisions = {
        "schema_version": "1.6",
        "course_id": "t",
        "decisions": [
            {
                "edge_id": eid,
                "source": source,
                "target": target,
                "decision": "ACCEPT",
                "decided_by": "teacher",
                "decided_at": "2026-11-03T10:00:00+00:00",
            }
            for eid, source, target in (("r1", "x", "y"), ("r2", "y", "x"))
        ],
    }
    out, _ = apply_review.apply_decisions(graph, decisions["decisions"])
    accepted = [e["id"] for e in out["edges"] if e["decision"] == "ACCEPT"]
    assert accepted == ["r1"]
    assert next(e for e in out["edges"] if e["id"] == "r2")["review"]["status"] == "refused_cycle"
