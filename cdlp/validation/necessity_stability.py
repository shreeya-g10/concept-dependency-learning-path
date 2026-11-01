"""Necessity stability study: how much does the gap move across seeds, formats and n?

    python -m cdlp.validation.necessity_stability --relationships R --concepts C --chunks K \
        --only r2 r4 r6 --plan open:3 mcq:3 mcq:5 mcq:8 open:5 --seeds 42 43 44 \
        --budget-minutes 60 --out-dir cdlp/validation/results/necessity_stability

Runs the necessity test once per (format, n, seed), in plan order, and saves each run
as <format>_n<n>_seed<seed>.json as soon as it finishes. Before starting a run it
predicts that run's time (measured mean of finished runs with the same format and n,
else the per-call-type estimate) and skips it if the budget would be exceeded, so the
study never runs over its approved time. The "with A" diagnostic is off: the gap
does not use it. Thresholds come from the config and are not changed.

summary.json: per (format, n) and edge, the mean gap and its standard deviation
across seeds (sample SD), plus whether the expected order holds:
gap(order[0]) > gap(order[1]) > gap(order[2]) and |gap(order[2])| < weak threshold,
judged on the means and separately for each seed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from cdlp.shared.io import read_json, read_jsonl
from cdlp.validation import necessity_test as nt

RESULTS = Path(__file__).parent / "results" / "necessity_stability"


# Per-call-type estimates on this laptop (llama3.1:8b; CLAUDE.local.md): a long reply
# ~36 s at n = 3 and grows with n; a short reply ~18 s.
def estimate_seconds(fmt: str, n: int, edges: int) -> float:
    long_call = 12 + 8 * n  # questions / free-text answers
    if fmt == "open":
        grader = 10 + 2.7 * n
        per_edge = long_call + 2 * long_call + 2 * grader  # questions, 2 learners, 2 grades
    else:
        per_edge = (12 + 12 * n) + 2 * 18  # MCQ questions (4 options each), 2 letter replies
    return per_edge * edges


def _order_holds(gaps: list[float | None], weak: float) -> bool:
    if any(g is None for g in gaps):
        return False
    first, second, last = gaps
    return first > second > last and abs(last) < weak


def summarise(runs: list[dict], order: list[str], weak: float) -> list[dict]:
    rows = []
    by_setting: dict[tuple, list[dict]] = {}
    for run in runs:
        by_setting.setdefault((run["question_format"], run["n_questions"]), []).append(run)
    for (fmt, n), group in by_setting.items():
        gaps = {rid: [] for rid in order}
        for run in group:
            for rid in order:
                gaps[rid].append(run["gaps"].get(rid))
        edges = {}
        for rid in order:
            values = [g for g in gaps[rid] if g is not None]
            edges[rid] = {
                "edge": group[0]["edges"][rid],
                "gaps": gaps[rid],
                "mean": round(statistics.mean(values), 4) if values else None,
                "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
                "grade_of_mean": nt.gap_grade(
                    statistics.mean(values) if values else None, group[0]["thresholds"]
                ),
            }
        per_seed = [_order_holds([run["gaps"].get(rid) for rid in order], weak) for run in group]
        rows.append(
            {
                "question_format": fmt,
                "n_questions": n,
                "seeds": [run["seed"] for run in group],
                "edges": edges,
                "order_holds_on_means": _order_holds([edges[r]["mean"] for r in order], weak),
                "order_holds_per_seed": per_seed,
                "seconds": round(sum(run["seconds"] for run in group), 1),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--only", nargs="+", required=True, help="edge ids, in expected order")
    parser.add_argument(
        "--plan", nargs="+", default=["open:3", "mcq:3", "mcq:5", "mcq:8", "open:5"]
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--budget-minutes", type=float, default=60)
    parser.add_argument("--config", type=Path, default=nt.DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args()

    relationships = read_json(args.relationships)
    concepts = read_json(args.concepts)
    chunks = read_jsonl(args.chunks)
    base = nt.load_config(args.config)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    budget, spent = args.budget_minutes * 60, 0.0
    measured: dict[tuple, list[float]] = {}
    runs, skipped = [], []
    for item in args.plan:
        fmt, n = item.split(":")
        n = int(n)
        for seed in args.seeds:
            key = (fmt, n)
            predicted = (
                statistics.mean(measured[key])
                if measured.get(key)
                else estimate_seconds(fmt, n, len(args.only))
            )
            if spent + predicted > budget:
                skipped.append(
                    {
                        "question_format": fmt,
                        "n_questions": n,
                        "seed": seed,
                        "predicted_seconds": round(predicted),
                    }
                )
                print(
                    f"skip {fmt} n={n} seed={seed}: predicted {predicted:.0f}s over budget",
                    flush=True,
                )
                continue
            cfg = {
                **base,
                "question_format": fmt,
                "n_questions": n,
                "seed": seed,
                "with_a_diagnostic": False,
            }
            start = time.monotonic()
            result = nt.run(relationships, concepts, chunks, cfg=cfg, only=args.only)
            seconds = time.monotonic() - start
            spent += seconds
            measured.setdefault(key, []).append(seconds)
            result["seconds"] = round(seconds, 1)
            out = args.out_dir / f"{fmt}_n{n}_seed{seed}.json"
            out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            by_id = {r["relationship_id"]: r for r in result["results"]}
            runs.append(
                {
                    "question_format": fmt,
                    "n_questions": n,
                    "seed": seed,
                    "seconds": seconds,
                    "thresholds": cfg["thresholds"],
                    "gaps": {rid: by_id[rid]["necessity_gap"] for rid in args.only},
                    "edges": {
                        rid: f"{by_id[rid]['source']} -> {by_id[rid]['target']}"
                        for rid in args.only
                    },
                }
            )
            print(
                f"done {fmt} n={n} seed={seed} in {seconds:.0f}s: "
                f"{[by_id[rid]['necessity_gap'] for rid in args.only]} "
                f"(spent {spent / 60:.1f} of {args.budget_minutes:.0f} min)",
                flush=True,
            )

    summary = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": base.get("model") or "LLM_VALIDATOR_MODEL",
        "inputs": {
            "relationships": str(args.relationships),
            "concepts": str(args.concepts),
            "chunks": str(args.chunks),
            "edges_in_expected_order": args.only,
        },
        "plan": args.plan,
        "seeds": args.seeds,
        "budget_minutes": args.budget_minutes,
        "spent_minutes": round(spent / 60, 1),
        "base_config": base,
        "expected_order": "gap(edge 1) > gap(edge 2) > gap(edge 3), |gap(edge 3)| < weak",
        "settings": summarise(runs, args.only, base["thresholds"]["weak"]),
        "skipped": skipped,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"summary -> {args.out_dir / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
