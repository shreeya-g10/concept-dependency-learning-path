"""Review-queue experiment: graph F1 after k simulated teacher answers, per strategy.

    python -m cdlp.validation.review_experiment \
        --config cdlp/validation/configs/review_experiment/ds101.json

Question: with a budget of k teacher answers (k = 0 ... k_max), which order of the
HUMAN_REVIEW edges raises the validated graph's F1 against gold fastest?

Strategies (all re-rank after every answer, on the graph as it is at that point)
- `impact`: the review queue's order (cdlp/validation/review_queue.py), highest
  impact_score first: how many simulated students' paths change if the edge is accepted.
- `random`: uniform random order, repeated over `random_seeds` seeds (mean and std).
- `lowest_confidence`: validator confidence, lowest first.
In every strategy, **blocking edges come first** (accepting them would close a cycle
with the ACCEPT edges on the current graph). Within a tier each strategy uses its own
order; ties go to the smallest edge id.

Simulated teacher: answers from gold. A hard / soft pair gets ACCEPT, a `none` pair gets
REJECT. A pair gold does not label gets `unlabelled_answer` (default REJECT, matching
RQ1's `unlabelled_pairs: false_positive`: an unlabelled pair is not a prerequisite).
Every answer is applied with cdlp/validation/apply_review.py, so an ACCEPT that would
close a cycle is refused exactly as on website page 3 (the answer is still spent).
An edge is asked once; when the queue is empty, later k repeat the last F1.

Scoring is RQ1's (cdlp/validation/evaluate.py: load_gold, resolve_scoring, score):
predictions are the ACCEPT edges, so HUMAN_REVIEW counts as "not predicted".

Read the results with these properties in mind (they follow from the design):
- Only an ACCEPT of a gold-positive edge changes F1 (TP + 1). A REJECT, a refused ACCEPT
  and an answer on a blocking edge leave F1 unchanged, so F1 never falls with k.
- Blocking-first spends budget on edges that can never be accepted, in every strategy.
- The teacher is a perfect oracle on the same gold that scores the graph, so the curve is
  an upper bound on what a real teacher's answers would give. No strategy sees gold:
  only the teacher's answers come from it.

Reproducible: the config fixes seeds, k_max and every path. The result is written to
cdlp/validation/results/review_experiment_<course_id>.json with the config, git commit
and date. No LLM call.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cdlp.validation.apply_review import apply_decisions
from cdlp.validation.evaluate import (
    POSITIVE_LABELS,
    RESULTS,
    _git_commit,
    load_gold,
    load_pairs,
    predicted_pairs,
    resolve_scoring,
    score,
)
from cdlp.validation.review_queue import accepted_graph, build_review_queue, is_blocking

STRATEGIES = ("impact", "random", "lowest_confidence")
SIMULATED_TEACHER = "simulated_teacher"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)  # answers are stamped T0 + k seconds


def teacher_answer(edge: dict, gold: dict, unlabelled_answer: str = "REJECT") -> str:
    label = gold.get((edge["source"], edge["target"]))
    if label is None:
        return unlabelled_answer
    return "ACCEPT" if label in POSITIVE_LABELS else "REJECT"


def next_edge(
    graph: dict,
    asked: set[str],
    strategy: str,
    students: dict | None = None,
    rng: random.Random | None = None,
    targets: list[str] | None = None,
) -> tuple[dict, bool] | None:
    """(edge, blocking) the strategy asks next on this graph; None when nothing waits."""
    pending = [
        e for e in graph["edges"] if e["decision"] == "HUMAN_REVIEW" and e["id"] not in asked
    ]
    if not pending:
        return None
    accepted = accepted_graph(graph)
    blocking = {e["id"]: is_blocking(accepted, e["source"], e["target"]) for e in pending}
    if strategy == "impact":
        if students is None:
            raise ValueError("the impact strategy needs sim_students")
        impact = {}
        if accepted.number_of_edges() or targets:
            queue = build_review_queue(graph, students, targets)["queue"]
            impact = {row["edge_id"]: row["impact_score"] for row in queue}

        def key(e):
            return (-(impact.get(e["id"]) or 0.0), e["id"])
    elif strategy == "random":
        # one random number per edge and step, drawn in id order: reproducible per seed
        draws = {e["id"]: rng.random() for e in sorted(pending, key=lambda e: e["id"])}

        def key(e):
            return (draws[e["id"]], e["id"])
    elif strategy == "lowest_confidence":

        def key(e):
            return (e["confidence"], e["id"])
    else:
        raise ValueError(f"strategy must be one of {STRATEGIES}, not {strategy!r}")
    edge = min(pending, key=lambda e: (not blocking[e["id"]], *key(e)))
    return edge, blocking[edge["id"]]


def run_strategy(
    graph: dict,
    gold: dict,
    strategy: str,
    k_max: int,
    *,
    students: dict | None = None,
    seed: int | None = None,
    targets: list[str] | None = None,
    scoring: str = "direct",
    unlabelled_pairs: str = "false_positive",
    unlabelled_answer: str = "REJECT",
    excluded: frozenset = frozenset(),
) -> list[dict]:
    """One curve: a row per k = 0 ... k_max with P / R / F1 and the answer given at k."""
    rng = random.Random(seed) if strategy == "random" else None
    decisions: list[dict] = []
    asked: set[str] = set()
    current = graph
    curve = []

    def row(k, answered):
        predicted = predicted_pairs(current, "validated") - excluded
        metrics = score(predicted, gold, scoring=scoring, unlabelled_pairs=unlabelled_pairs)
        return {
            "k": k,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "true_positive": metrics["true_positive"],
            "answered": answered,
        }

    curve.append(row(0, None))
    for k in range(1, k_max + 1):
        chosen = next_edge(current, asked, strategy, students, rng, targets)
        if chosen is None:
            curve.append({**curve[-1], "k": k, "answered": None})
            continue
        edge, blocking = chosen
        asked.add(edge["id"])
        answer = teacher_answer(edge, gold, unlabelled_answer)
        decisions.append(
            {
                "edge_id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "decision": answer,
                "decided_by": SIMULATED_TEACHER,
                "decided_at": (T0 + timedelta(seconds=k)).isoformat(),
            }
        )
        current, report = apply_decisions(graph, decisions)
        answered = {
            "edge_id": edge["id"],
            "source": edge["source"],
            "target": edge["target"],
            "answer": answer,
            "status": report[-1]["status"],
            "blocking": blocking,  # when it was asked
        }
        curve.append(row(k, answered))
    return curve


def summarise(curves: list[list[dict]]) -> list[dict]:
    """Mean and std of P / R / F1 per k over several curves (the random strategy)."""
    rows = []
    for k, at_k in enumerate(zip(*curves, strict=True)):
        rows.append({"k": k})
        for metric in ("precision", "recall", "f1"):
            values = [r[metric] for r in at_k]
            rows[-1][metric] = statistics.fmean(values)
            rows[-1][f"{metric}_std"] = statistics.pstdev(values)
    return rows


def run_experiment(config: dict, base: Path = Path(".")) -> dict:
    from cdlp.shared.io import read_json

    graph = read_json(base / config["graph"])
    concept_ids = {n["id"] for n in graph.get("nodes", [])} or None
    gold = load_gold(base / config["gold"], concept_ids)
    excluded = frozenset()
    if config.get("exclude_pairs"):
        excluded = frozenset(load_pairs(base / config["exclude_pairs"]))
        gold = {p: label for p, label in gold.items() if p not in excluded}
    scoring, _ = resolve_scoring(config.get("scoring", "direct"), gold)
    students = read_json(base / config["students"]) if config.get("students") else None
    common = {
        "students": students,
        "targets": config.get("targets"),
        "scoring": scoring,
        "unlabelled_pairs": config.get("unlabelled_pairs", "false_positive"),
        "unlabelled_answer": config.get("unlabelled_answer", "REJECT"),
        "excluded": excluded,
    }
    k_max = config.get("k_max", 10)
    strategies = {}
    for name in config.get("strategies", STRATEGIES):
        if name == "random":
            seeds = list(
                range(config.get("seed", 0), config.get("seed", 0) + config["random_seeds"])
            )
            curves = [run_strategy(graph, gold, name, k_max, seed=s, **common) for s in seeds]
            strategies[name] = {"seeds": seeds, "curve": summarise(curves), "runs": curves}
        else:
            strategies[name] = {"curve": run_strategy(graph, gold, name, k_max, **common)}
    pending = [e for e in graph["edges"] if e["decision"] == "HUMAN_REVIEW"]
    blocking = [
        e["id"] for e in pending if is_blocking(accepted_graph(graph), e["source"], e["target"])
    ]
    return {
        "experiment": "review_queue",
        "course_id": graph["course_id"],
        "config": config,
        "scoring": scoring,
        "human_review_edges": len(pending),
        "blocking_edges": blocking,
        "gold_positive_human_review_edges": sum(
            gold.get((e["source"], e["target"])) in POSITIVE_LABELS for e in pending
        ),
        "strategies": strategies,
        "git_commit": _git_commit(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="default: results/review_experiment_<course>.json")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = run_experiment(config)
    out = args.out or RESULTS / f"review_experiment_{result['course_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for name, data in result["strategies"].items():
        print(name, " ".join(f"{r['f1']:.3f}" for r in data["curve"]))
    print(f"wrote {out}")
    return result


if __name__ == "__main__":
    main()
