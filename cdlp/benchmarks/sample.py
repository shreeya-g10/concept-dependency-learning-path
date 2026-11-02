"""Seeded, stratified sample of a converted benchmark's labelled pairs (RQ1).

    python -m cdlp.benchmarks.sample [--courses-dir outputs/benchmarks] [--n 200] \
        [--subset 100] [--seed 42] [--course al_cpl_geometry ...]

For every course folder with a gold_edges.csv (default: all), draws n labelled pairs
stratified by label (positive = hard or soft, negative = none) in proportion to the
graph's own positive rate, and a nested subset of `subset` pairs (also stratified, drawn
from the sample) for the costlier settings (self-consistency). Writes, next to the gold:

    sample_pairs.csv           the n pairs, gold columns + in_subset (0/1)
    gold_edges_sample.csv      the n pairs as a gold file (score on this)
    gold_edges_subset.csv      the subset as a gold file
    sample_concepts.json       the concepts that occur in the sample (discovery input)
    sample.json                seed, sizes, population and sample counts per stratum,
                               inverse-probability weights, the files written

Same seed and inputs -> same sample: the RNG is seeded per course and stratum, and rows
are sorted before drawing, so file order does not matter.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from cdlp.benchmarks.common import GOLD_COLUMNS, write_gold_edges

POSITIVE = {"hard", "soft"}


def _stratum(row: dict) -> str:
    return "positive" if row["label"] in POSITIVE else "negative"


def allocate(counts: dict[str, int], n: int) -> dict[str, int]:
    """Proportional allocation with largest remainders; never more than a stratum has.
    Equal remainders go to the smaller stratum, and when n allows, every non-empty stratum
    gets at least one pair, so the rarer label (usually the positives) is never left out."""
    total = sum(counts.values())
    n = min(n, total)
    if not n:
        return {s: 0 for s in counts}
    exact = {s: n * c / total for s, c in counts.items()}
    take = {s: int(v) for s, v in exact.items()}
    order = sorted(exact, key=lambda s: (-(exact[s] - take[s]), counts[s], s))
    for s in order[: n - sum(take.values())]:
        take[s] += 1
    nonempty = [s for s in counts if counts[s]]
    if n >= len(nonempty):
        for s in nonempty:
            if take[s] == 0:
                donor = max(take, key=lambda d: (take[d], d))
                take[donor] -= 1
                take[s] = 1
    return {s: min(take[s], counts[s]) for s in counts}


def _draw(rows: list[dict], k: int, seed_key: str) -> list[dict]:
    ordered = sorted(rows, key=lambda r: (r["source"], r["target"]))
    return random.Random(seed_key).sample(ordered, k)


def sample_course(gold: list[dict], course_id: str, n: int, subset: int, seed: int) -> dict:
    strata: dict[str, list[dict]] = {"positive": [], "negative": []}
    for row in gold:
        strata[_stratum(row)].append(row)
    population = {s: len(r) for s, r in strata.items()}

    take = allocate(population, n)
    chosen = {s: _draw(strata[s], take[s], f"{seed}:{course_id}:{s}") for s in strata}
    take_sub = allocate({s: len(r) for s, r in chosen.items()}, subset)
    in_subset = {
        (r["source"], r["target"])
        for s in chosen
        for r in _draw(chosen[s], take_sub[s], f"{seed}:{course_id}:{s}:subset")
    }
    rows = sorted((r for s in chosen for r in chosen[s]), key=lambda r: (r["source"], r["target"]))
    return {
        "rows": rows,
        "in_subset": in_subset,
        "population": population,
        "sample": take,
        "subset": take_sub,
        "weights": {s: round(population[s] / take[s], 4) if take[s] else None for s in strata},
    }


def write_sample(folder: Path, n: int, subset: int, seed: int) -> dict:
    from cdlp.shared.io import read_json, write_json

    with (folder / "gold_edges.csv").open(newline="") as f:
        gold = list(csv.DictReader(f))
    concepts = read_json(folder / "concepts.json")
    course_id = concepts["course_id"]
    drawn = sample_course(gold, course_id, n, subset, seed)
    rows, in_subset = drawn["rows"], drawn["in_subset"]

    with (folder / "sample_pairs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*GOLD_COLUMNS, "in_subset"], lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    **{c: r.get(c, "") for c in GOLD_COLUMNS},
                    "in_subset": int((r["source"], r["target"]) in in_subset),
                }
            )
    write_gold_edges(folder / "gold_edges_sample.csv", rows)
    write_gold_edges(
        folder / "gold_edges_subset.csv",
        [r for r in rows if (r["source"], r["target"]) in in_subset],
    )
    used = {r["source"] for r in rows} | {r["target"] for r in rows}
    write_json(
        folder / "sample_concepts.json",
        {**concepts, "concepts": [c for c in concepts["concepts"] if c["id"] in used]},
    )
    meta = {
        "course_id": course_id,
        "seed": seed,
        "n": len(rows),
        "subset_n": len(in_subset),
        "stratify_by": "label (positive = hard/soft, negative = none), proportional",
        "population": drawn["population"],
        "sample": drawn["sample"],
        "subset": drawn["subset"],
        "weights": drawn["weights"],
        "concepts_in_sample": len(used),
        "files": [
            "sample_pairs.csv",
            "gold_edges_sample.csv",
            "gold_edges_subset.csv",
            "sample_concepts.json",
        ],
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (folder / "sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--courses-dir", type=Path, default=Path("outputs/benchmarks"))
    parser.add_argument("--course", nargs="*", help="course ids (default: every folder)")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--subset", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    folders = sorted(p.parent for p in args.courses_dir.glob("*/gold_edges.csv"))
    if args.course:
        folders = [f for f in folders if f.name in set(args.course)]
    if not folders:
        raise SystemExit(
            f"no converted course in {args.courses_dir} (run python -m cdlp.benchmarks)"
        )
    for folder in folders:
        m = write_sample(folder, args.n, args.subset, args.seed)
        print(
            f"{m['course_id']}: sample {m['sample']} of {m['population']}, "
            f"subset {m['subset']}, {m['concepts_in_sample']} concepts -> {folder}"
        )


if __name__ == "__main__":
    main()
