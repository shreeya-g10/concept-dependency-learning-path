"""Apply teacher decisions on HUMAN_REVIEW edges to validated_graph.json (contract 1.6).

    python -m cdlp.validation.apply_review --graph outputs/ds101/validated_graph.json \
        --decisions outputs/ds101/review_decisions.json \
        [--decide r5 ACCEPT --comment "graphs are taught after trees"] \
        [--students outputs/ds101/sim_students.json --queue outputs/ds101/review_queue.json]

--decide records one decision (it replaces an earlier one for the same edge) in
review_decisions.json, then applies all of them. Without --decide the decisions are
re-applied as they are (e.g. after the pipeline rewrote validated_graph.json).
With --students and --queue the review queue is rebuilt on the updated graph, so it
only lists edges still waiting and their blocking / impact on the current graph.

Rules
- The result is a function of (validator output, decisions): every teacher decision
  already in the graph is undone first (edge.review.validator_decision is restored),
  then the decisions are applied in decided_at order. Re-running changes nothing.
- Only edges the validator sent to HUMAN_REVIEW can be decided. A decision for any
  other edge, or for an edge that is not in the graph, is reported and skipped.
- REJECT always applies. ACCEPT applies only if the edge closes no cycle with the
  ACCEPT edges at that point (validator ACCEPTs and earlier teacher ACCEPTs). Otherwise
  the edge stays HUMAN_REVIEW with review.status "refused_cycle" and the cycle, so the
  graph stays a DAG. (A teacher can only decide HUMAN_REVIEW edges, so such a cycle can
  only be broken by rejecting another HUMAN_REVIEW edge that is part of it, or by
  re-running validation.)
- Decisions are matched to edges by (source, target), falling back to edge_id, because
  edge ids can change when validation is re-run.
- The validator's own fields (confidence, checks, evidence, reason) are never changed;
  the teacher's decision is in edge.review with decided_by "teacher".

No LLM call. Reused by the review-queue experiment (simulated teacher answers).
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

SCHEMA_VERSION = "1.6"  # review_decisions.json and edge.review are new in 1.6
TEACHER = "teacher"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def reset(graph: dict) -> dict:
    """A copy of the graph with every teacher decision undone (validator decisions only)."""
    graph = copy.deepcopy(graph)
    for edge in graph["edges"]:
        review = edge.pop("review", None)
        if review:
            edge["decision"] = review["validator_decision"]
    return graph


def _find(edges: list[dict], decision: dict) -> dict | None:
    for edge in edges:
        if (edge["source"], edge["target"]) == (decision["source"], decision["target"]):
            return edge
    return next((e for e in edges if e["id"] == decision.get("edge_id")), None)


def _cycle_if_accepted(accepted: nx.DiGraph, source: str, target: str) -> list[str] | None:
    """The cycle source -> target -> ... -> source would close, else None."""
    if source == target:
        return [source, source]
    if source in accepted and target in accepted and nx.has_path(accepted, target, source):
        return [source, *nx.shortest_path(accepted, target, source)]
    return None


def apply_decisions(graph: dict, decisions: list[dict]) -> tuple[dict, list[dict]]:
    """(updated graph, one report row per decision). The input graph is not changed.

    Report rows: {"edge_id", "source", "target", "decision", "status"} with status
    applied / refused_cycle / not_human_review / unknown_edge.
    """
    graph = reset(graph)
    graph["schema_version"] = SCHEMA_VERSION
    accepted = nx.DiGraph(
        (e["source"], e["target"]) for e in graph["edges"] if e["decision"] == "ACCEPT"
    )
    report = []
    for decision in sorted(decisions, key=lambda d: d.get("decided_at", "")):
        edge = _find(graph["edges"], decision)
        row = {k: decision.get(k) for k in ("edge_id", "source", "target", "decision")}
        if edge is None:
            report.append({**row, "status": "unknown_edge"})
            continue
        row["edge_id"] = edge["id"]
        if edge["decision"] != "HUMAN_REVIEW" or "review" in edge:
            # not sent to review by the validator, or already decided by an earlier row
            report.append({**row, "status": "not_human_review"})
            continue
        review = {
            "decided_by": decision.get("decided_by", TEACHER),
            "decision": decision["decision"],
            "validator_decision": "HUMAN_REVIEW",
            "status": "applied",
        }
        for key in ("comment", "decided_at"):
            if decision.get(key):
                review[key] = decision[key]
        if decision["decision"] == "ACCEPT":
            cycle = _cycle_if_accepted(accepted, edge["source"], edge["target"])
            if cycle:
                review.update(status="refused_cycle", cycle=cycle)
            else:
                edge["decision"] = "ACCEPT"
                accepted.add_edge(edge["source"], edge["target"])
        else:
            edge["decision"] = "REJECT"
        edge["review"] = review
        report.append({**row, "status": review["status"]})
    return graph, report


def record_decision(
    decisions: dict,
    edge: dict,
    decision: str,
    comment: str = "",
    decided_at: str | None = None,
) -> dict:
    """decisions (review_decisions.json content) with this edge's decision set or replaced."""
    if decision not in ("ACCEPT", "REJECT"):
        raise ValueError(f"decision must be ACCEPT or REJECT, not {decision!r}")
    row = {
        "edge_id": edge["id"],
        "source": edge["source"],
        "target": edge["target"],
        "decision": decision,
        "decided_by": TEACHER,
        "decided_at": decided_at or now_iso(),
    }
    if comment.strip():
        row["comment"] = comment.strip()
    kept = [
        d
        for d in decisions.get("decisions", [])
        if (d["source"], d["target"]) != (edge["source"], edge["target"])
    ]
    return {**decisions, "schema_version": SCHEMA_VERSION, "decisions": [*kept, row]}


def empty_decisions(course_id: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "course_id": course_id, "decisions": []}


def main(argv: list[str] | None = None) -> list[dict]:
    from cdlp.shared.io import read_json, write_json

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--graph", type=Path, required=True, help="validated_graph.json (updated)")
    parser.add_argument("--decisions", type=Path, required=True, help="review_decisions.json")
    parser.add_argument("--decide", nargs=2, metavar=("EDGE_ID", "DECISION"))
    parser.add_argument("--comment", default="")
    parser.add_argument("--students", type=Path, help="sim_students.json, to rebuild the queue")
    parser.add_argument("--queue", type=Path, help="review_queue.json to rebuild")
    args = parser.parse_args(argv)
    if bool(args.students) != bool(args.queue):
        parser.error("--students and --queue go together")

    graph = read_json(args.graph)
    if args.decisions.exists():
        decisions = read_json(args.decisions)
    else:
        decisions = empty_decisions(graph["course_id"])
    if args.decide:
        edge_id, decision = args.decide
        edge = next((e for e in graph["edges"] if e["id"] == edge_id), None)
        if edge is None:
            parser.error(f"no edge {edge_id!r} in {args.graph}")
        if (edge.get("review") or {}).get("validator_decision", edge["decision"]) != "HUMAN_REVIEW":
            parser.error(f"edge {edge_id} was not sent to HUMAN_REVIEW by the validator")
        decisions = record_decision(decisions, edge, decision.upper(), args.comment)
        write_json(args.decisions, decisions)

    updated, report = apply_decisions(graph, decisions["decisions"])
    write_json(args.graph, updated)
    if args.queue:
        from cdlp.validation.review_queue import write_review_queue

        try:
            write_review_queue(args.queue, updated, read_json(args.students))
        except ValueError as exc:  # e.g. no ACCEPT edge left to pick a default target
            print(f"review queue not rebuilt: {exc}")
    for row in report:
        print(
            f"{row['edge_id']} {row['source']} -> {row['target']}: "
            f"{row['decision']} {row['status']}"
        )
    return report


if __name__ == "__main__":
    main()
