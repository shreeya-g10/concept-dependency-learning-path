"""validation: relationships + concepts + chunks -> validated_graph.json

    python -m cdlp.validation --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --chunks outputs/chunks.jsonl \
        --out outputs/validated_graph.json \
        [--skip-evidence] [--skip-semantic] [--skip-necessity] [--skip-graph] \
        [--review-queue outputs/review_queue.json --students outputs/sim_students.json]

Runs the graph, evidence, semantic (prompt semantic_v2) and necessity checks on every
proposed edge and combines them into ACCEPT / REJECT / HUMAN_REVIEW with the decision
rule and thresholds in configs/default.json ("decision"). Every edge is kept, with
all four checks, its confidence, evidence quotes and a reason.

Each --skip-* flag drops one check (the RQ1 ablations). A skipped check is written as
"skipped" (contract 1.5), listed under "skipped_checks", named in each reason, and
never blocks ACCEPT. A check with weight 0 in the config is report-only: it runs and is
recorded on every edge, but takes no part in the score, the vetoes or the decision.
Necessity is report-only by default (weight 0; --necessity-weight overrides it).
--demo-subset N validates only the N proposed edges with the highest discovery confidence
(ties by id), for a quick demo; the output says so in its top-level "subset" field, and
the website shows a banner. It is not an evaluation of the course graph.
With --demo-rule <config> the N edges are picked by that written rule instead (demo_rule.py,
e.g. configs/demo_subset_ds101.json); the chosen edges and the rule are written next to
--out as <out stem>.demo_subset.json. Only proposed edges can ever be chosen.
--necessity-sample N runs the necessity test only on a seeded sample of N edges (same
sample for the same seed and edges, so the runs with and without necessity compare on
the same edges); the other edges get necessity "skipped". The sampled ids are written
next to --out as <out stem>.necessity_sample.json.
The run's LLM call counts go to <out dir>/<setting>.stats.json (write_stats), where
setting is full_agent, minus_<check> or minus_<a>_<b>... (or --setting).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import networkx as nx

from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl
from cdlp.validation import (
    demo_rule,
    evidence_check,
    graph_checks,
    necessity_test,
    semantic_check,
)

CHECKS = ("evidence", "semantic", "necessity", "graph")
LLM_CHECKS = ("evidence", "semantic", "necessity")
DEFAULT_CONFIG = Path(__file__).parent / "configs" / "default.json"
SCHEMA_VERSION = "1.8"  # 1.5: 'skipped'; 1.8: optional top-level 'subset' (demo runs)
SKIPPED = "skipped"
STRUCTURAL_REJECT = {graph_checks.SELF_LOOP: "self-loop", graph_checks.DUPLICATE: "duplicate"}


def load_decision_config(path: Path | str = DEFAULT_CONFIG) -> dict:
    return json.loads(Path(path).read_text())["decision"]


def setting_name(skipped: set[str]) -> str:
    return "full_agent" if not skipped else "minus_" + "_".join(c for c in CHECKS if c in skipped)


def implied_by(relationship: dict, relationships: list[dict], labels: dict[str, str]) -> list:
    """Shortest path source -> ... -> target through OTHER acyclic edges, or []."""
    graph = nx.DiGraph(
        (r["source"], r["target"])
        for r in relationships
        if r["id"] != relationship["id"]
        and labels[r["id"]] in (graph_checks.OK, graph_checks.REDUNDANT)
    )
    try:
        path = nx.shortest_path(graph, relationship["source"], relationship["target"])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    return path if len(path) > 2 else []


def deciding(grades: dict[str, str | None], cfg: dict) -> dict[str, str]:
    """The checks that take part in the decision: ran (not None) and weight > 0."""
    return {c: g for c, g in grades.items() if g is not None and cfg["weights"].get(c, 0) > 0}


def score(grades: dict[str, str], cfg: dict) -> float | None:
    """Weighted mean of the deciding checks' grade points (None if none decides)."""
    active = deciding(grades, cfg)
    total = sum(cfg["weights"][c] for c in active)
    if not total:
        return None
    return sum(cfg["weights"][c] * cfg["grade_points"][g] for c, g in active.items()) / total


def decide(
    graph_label: str,
    grades: dict[str, str | None],
    cfg: dict,
    *,
    bidirectional: bool = False,
    implied_path: list | None = None,
) -> tuple[str, float, str]:
    """(decision, confidence, reason). grades: evidence / semantic / necessity grade,
    None for a skipped check. graph_label: graph_checks label ("ok" when skipped)."""
    if graph_label in STRUCTURAL_REJECT:
        return "REJECT", 1.0, f"{STRUCTURAL_REJECT[graph_label]}."
    if bidirectional or graph_label == graph_checks.CONTRADICTION:
        why = "proposed in both directions" if bidirectional else "the reverse edge is proposed"
        return "HUMAN_REVIEW", 0.5, f"Direction unclear: {why}."
    if graph_label == graph_checks.REDUNDANT:
        path = " → ".join(implied_path or [])
        return "REJECT", 1.0, f"Redundant: implied by {path}." if path else "Redundant."

    s = score(grades, cfg)
    ran = deciding(grades, cfg)
    summary = (
        ", ".join(
            f"{c} {g}" + ("" if c in ran else " (report-only)")
            for c, g in grades.items()
            if g is not None
        )
        or "no check ran"
    )
    unsupported = (
        cfg.get("reject_if_unsupported")
        and ran.get("evidence") in ("weak", "none")
        and ran.get("semantic") in ("weak", "none")
    )
    if s is None:
        decision = "HUMAN_REVIEW"
    elif s < cfg["reject_below"] or unsupported:
        decision = "REJECT"
    elif s >= cfg["accept_min"] and "none" not in ran.values():
        decision = "ACCEPT"
    else:
        decision = "HUMAN_REVIEW"

    if graph_label == graph_checks.CYCLE and decision == "ACCEPT":
        decision = "HUMAN_REVIEW"  # a cycle is never auto-accepted
    confidence = (
        0.5 if s is None or decision == "HUMAN_REVIEW" else (s if decision == "ACCEPT" else 1 - s)
    )
    detail = f"score {s:.2f}" if s is not None else "no score"
    if unsupported:
        detail += "; neither the material nor the semantic check supports it"
    if graph_label == graph_checks.CYCLE:
        detail += "; lies on a cycle, so never accepted automatically"
    return decision, round(confidence, 4), f"{summary} ({detail})."


def necessity_sample_ids(rels: list[dict], n: int, seed: int, course_id: str) -> list[str]:
    """Seeded sample of n relationship ids (all of them if there are fewer)."""
    import random

    ids = sorted(r["id"] for r in rels)
    if n >= len(ids):
        return ids
    return sorted(random.Random(f"{seed}:{course_id}").sample(ids, n))


def demo_subset(relationships: dict, n: int) -> tuple[dict, dict]:
    """Keep the n proposed edges with the highest discovery confidence (ties by id)."""
    rels = relationships["relationships"]
    kept = sorted(rels, key=lambda r: (-float(r.get("confidence") or 0), r["id"]))[:n]
    kept_ids = {r["id"] for r in kept}
    subset = {
        "kind": "demo",
        "n": len(kept),
        "of": len(rels),
        "selection": "highest discovery confidence (ties by id)",
    }
    return {**relationships, "relationships": [r for r in rels if r["id"] in kept_ids]}, subset


def validate(
    relationships: dict,
    concepts: dict,
    chunks: list[dict],
    *,
    skip: set[str] = frozenset(),
    config_path: Path | str = DEFAULT_CONFIG,
    embed=None,
    necessity_weight: float | None = None,
    necessity_sample: int | None = None,
    necessity_seed: int = 42,
) -> dict:
    cfg = load_decision_config(config_path)
    if necessity_weight is not None:
        cfg["weights"] = {**cfg["weights"], "necessity": necessity_weight}
    rels = relationships["relationships"]
    labels = (
        graph_checks.graph_labels_by_id(rels)
        if "graph" not in skip
        else {r["id"]: graph_checks.OK for r in rels}
    )

    def by_id(result: dict | None) -> dict:
        return {r["relationship_id"]: r for r in (result or {}).get("results", [])}

    evidence = by_id(
        evidence_check.run(relationships, concepts, chunks, embed=embed)
        if "evidence" not in skip
        else None
    )
    semantic = by_id(
        semantic_check.run(relationships, concepts, prompt_version="semantic_v2")
        if "semantic" not in skip
        else None
    )
    ncfg = necessity_test.load_config(config_path)
    sampled = (
        necessity_sample_ids(rels, necessity_sample, necessity_seed, relationships["course_id"])
        if necessity_sample is not None and "necessity" not in skip
        else None
    )
    necessity = by_id(
        necessity_test.run(relationships, concepts, chunks, cfg=ncfg, only=sampled)
        if "necessity" not in skip and sampled != []
        else None
    )

    edges = []
    for r in rels:
        ev, se, ne = evidence.get(r["id"]), semantic.get(r["id"]), necessity.get(r["id"])
        if sampled is not None and r["id"] not in sampled:
            ne = None  # outside the necessity sample, whatever the check returned
        grades = {
            "evidence": ev["evidence"] if ev else None,
            "semantic": se["semantic"] if se else None,
            "necessity": ne["necessity"] if ne and ne.get("status") == "ok" else None,
        }
        decision, confidence, reason = decide(
            labels[r["id"]],
            grades,
            cfg,
            bidirectional=bool(r.get("bidirectional")),
            implied_path=implied_by(r, rels, labels)
            if labels[r["id"]] == graph_checks.REDUNDANT
            else None,
        )
        if se and se.get("rationale"):
            reason += f" Semantic: {se['rationale']}"
        skipped = [c for c in CHECKS if c in skip]
        if skipped:
            reason += f" (skipped: {', '.join(skipped)})"
        if sampled is not None and r["id"] not in sampled:
            reason += " (necessity not in the sample)"
        edges.append(
            {
                "id": r["id"],
                "source": r["source"],
                "target": r["target"],
                "type": "PREREQUISITE",
                "strength": r["strength"],
                "decision": decision,
                "confidence": confidence,
                "checks": {
                    "evidence": SKIPPED if "evidence" in skip else grades["evidence"],
                    "semantic": SKIPPED if "semantic" in skip else grades["semantic"],
                    # necessity that could not run (no course text for B) is skipped too
                    "necessity": SKIPPED
                    if "necessity" in skip or grades["necessity"] is None
                    else grades["necessity"],
                    "graph": SKIPPED if "graph" in skip else labels[r["id"]],
                },
                "necessity_gap": ne.get("necessity_gap") if ne else None,
                "score_control": ne.get("score_control") if ne else None,
                "score_without": ne.get("score_without") if ne else None,
                "n_questions": ncfg["n_questions"],
                "question_format": ncfg.get("question_format", "open"),
                # quotes verified by the evidence check; else discovery's cited chunks
                "evidence": (ev["quotes"] if ev else None) or r.get("evidence", []),
                "reason": reason,
            }
        )
    result = {
        "schema_version": SCHEMA_VERSION,
        "course_id": relationships["course_id"],
        "nodes": [{"id": c["id"], "name": c["name"]} for c in concepts["concepts"]],
        "edges": edges,
        "skipped_checks": [c for c in CHECKS if c in skip],
    }
    if sampled is not None:
        result["_necessity_sample"] = {
            "n": necessity_sample,
            "seed": necessity_seed,
            "ids": sampled,
        }
    return result


def write_graph(path: Path, graph: dict) -> None:
    """Write a validated graph under any name (validated_graph.json, or an RQ1 ablation
    such as validated_minus_evidence_necessity.json): the file-name ending does not
    pick the schema here, so the contract is checked explicitly."""
    from cdlp.shared.validate import check

    errors = check(graph, "validated_graph")
    if errors:
        raise ValueError(
            f"{path.name} breaks the validated_graph contract:\n  " + "\n  ".join(errors)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    for check in CHECKS:
        parser.add_argument(f"--skip-{check}", action="store_true", help=f"ablation: no {check}")
    parser.add_argument("--review-queue", type=Path, help="also write review_queue.json here")
    parser.add_argument("--students", type=Path, help="sim_students.json (for --review-queue)")
    parser.add_argument("--setting", help="name for the stats file (default from the skips)")
    parser.add_argument("--stats", type=Path, help="default: <out dir>/<setting>.stats.json")
    parser.add_argument(
        "--necessity-weight",
        type=float,
        help="override the config's necessity weight (0 = report-only, the default)",
    )
    parser.add_argument(
        "--necessity-sample", type=int, help="run necessity on a seeded sample of N edges only"
    )
    parser.add_argument("--necessity-seed", type=int, default=42)
    parser.add_argument(
        "--demo-subset",
        type=int,
        help="validate only the N highest-confidence proposed edges (labelled as a demo subset)",
    )
    parser.add_argument(
        "--demo-rule",
        type=Path,
        help="with --demo-subset: pick the N edges by this written rule, not by confidence",
    )
    args = parser.parse_args(argv)
    if args.demo_rule and not args.demo_subset:
        parser.error("--demo-rule needs --demo-subset N")
    if args.review_queue and not args.students:
        parser.error("--review-queue needs --students (sim_students.json)")

    skip = {c for c in CHECKS if getattr(args, f"skip_{c}")}
    relationships = read_json(args.relationships)
    subset = None
    if args.demo_rule:
        relationships, subset, record = demo_rule.select(
            relationships, args.demo_subset, demo_rule.load_rule(args.demo_rule)
        )
        sidecar = args.out.with_name(f"{args.out.stem}.demo_subset.json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        tiers = [edge["tier"] for edge in record["selected"]]
        print(
            f"demo subset ({record['rule_id']}): {subset['n']} of {subset['of']} proposed edges, "
            f"{ {tier: tiers.count(tier) for tier in record['tier_order']} } -> {sidecar}",
            file=sys.stderr,
        )
        for link in record["missing_chain_links"]:
            print(
                f"WARNING: chain link {link['source']} -> {link['target']} was not proposed "
                "by discovery, so it is not in the demo graph",
                file=sys.stderr,
            )
    elif args.demo_subset:
        relationships, subset = demo_subset(relationships, args.demo_subset)
        print(f"demo subset: {subset['n']} of {subset['of']} proposed edges", file=sys.stderr)
    result = validate(
        relationships,
        read_json(args.concepts),
        read_jsonl(args.chunks),
        skip=skip,
        config_path=args.config,
        necessity_weight=args.necessity_weight,
        necessity_sample=args.necessity_sample,
        necessity_seed=args.necessity_seed,
    )
    if subset:
        result["subset"] = subset
    sample = result.pop("_necessity_sample", None)
    if sample:
        sidecar = args.out.with_name(f"{args.out.stem}.necessity_sample.json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(sample, indent=2) + "\n")
    write_graph(args.out, result)
    if args.review_queue:
        from cdlp.validation.review_queue import write_review_queue

        write_review_queue(args.review_queue, result, read_json(args.students))
    setting = args.setting or setting_name(skip)
    stats = llm.write_stats(args.stats or args.out.parent / f"{setting}.stats.json")
    decisions = [e["decision"] for e in result["edges"]]
    print(
        f"{setting}: {decisions.count('ACCEPT')} ACCEPT, {decisions.count('REJECT')} REJECT, "
        f"{decisions.count('HUMAN_REVIEW')} HUMAN_REVIEW; {stats['llm_calls']} LLM calls, "
        f"{stats['cache_hits']} cache hits -> {args.out}",
        file=sys.stderr,
    )
    return result


if __name__ == "__main__":
    main()
