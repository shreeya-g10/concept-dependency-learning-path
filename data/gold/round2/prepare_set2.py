"""Checks Vaidehi's set 2 labels, converts them to gold format and splits them. Makes no LLM call.

    python data/gold/round2/prepare_set2.py

Reads ds101_set2_labels_vaidehi.csv, which it never changes, and writes annotator_a_set2.csv and
set2_split.json. If the checks find a problem it lists it and writes nothing: labels are never
fixed here. Output is counts and pair numbers only, so running it does not show the labels.

A means concept_a comes first and b means concept_b comes first. For neither (label none) neither
concept comes first, so source and target are simply in sorted id order.

The cycle and shortcut findings are reported, not acted on. Nothing here merges into
data/gold/<course>/gold_edges.csv.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "ds101_set2_labels_vaidehi.csv"
BLANK = HERE / "send_to_annotator" / "ds101_set2_to_label.csv"
KEY = HERE / "private_keys" / "ds101_set2_key.csv"
GOLD = HERE / "annotator_a_set2.csv"
SPLIT = HERE / "set2_split.json"
SEED = 44
DEV_SHARE = 0.3
LABELS = ("hard", "soft", "none")
SAME_AS_BLANK = ("pair", "concept_a", "concept_b", "where_a", "where_b")


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def find_problems(rows: list[dict], blank: list[dict]) -> list[str]:
    """Every problem, by pair number. No message includes an answer."""
    problems = []
    if len(rows) != len(blank):
        problems.append(f"{len(rows)} pairs, but the blank file has {len(blank)}")
    numbers = [r.get("pair") for r in rows]
    for number in sorted({n for n in numbers if numbers.count(n) > 1}):
        problems.append(f"pair {number}: appears more than once")
    for position, (row, sent) in enumerate(zip(rows, blank, strict=False), start=1):
        name = row.get("pair") or f"row {position}"
        for column in SAME_AS_BLANK:
            if row.get(column) != sent.get(column):
                problems.append(f"pair {name}: {column} differs from the blank file")
    for position, row in enumerate(rows, start=1):
        name = row.get("pair") or f"row {position}"
        first = (row.get("first") or "").strip().lower()
        strength = (row.get("strength") or "").strip()
        if first not in ("a", "b", "neither"):
            problems.append(f"pair {name}: first is not a, b or neither")
        elif first in ("a", "b") and strength not in ("hard", "soft"):
            problems.append(f"pair {name}: first is a or b, but strength is not hard or soft")
        elif first == "neither" and strength:
            problems.append(f"pair {name}: first is neither, but strength is filled in")
    return problems


def convert(rows: list[dict], key: list[dict]) -> list[dict]:
    """Gold rows in pair order, with the pair number under "_pair" (not written to the file)."""
    ids = {k["pair"]: (k["concept_a_id"], k["concept_b_id"]) for k in key}
    out = []
    for row in rows:
        a, b = ids[row["pair"]]
        first = row["first"].strip().lower()
        if first == "a":
            source, target, label = a, b, row["strength"].strip()
        elif first == "b":
            source, target, label = b, a, row["strength"].strip()
        else:
            source, target, label = *sorted((a, b)), "none"
        out.append(
            {
                "_pair": row["pair"],
                "source": source,
                "target": target,
                "label": label,
                "note": row["note"],
            }
        )
    return out


def write_gold(gold: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, ["source", "target", "label", "note"], lineterminator="\n")
        writer.writeheader()
        for row in gold:
            writer.writerow({k: row[k] for k in ("source", "target", "label", "note")})


def graph_findings(gold: list[dict]) -> dict:
    """Cycles among the hard and soft labels, and labelled pairs a longer path already implies."""
    import networkx as nx

    pair_of = {(r["source"], r["target"]): r["_pair"] for r in gold if r["label"] != "none"}
    graph = nx.DiGraph()
    graph.add_edges_from(pair_of)
    cycles = []
    for cycle in nx.simple_cycles(graph):
        edges = zip(cycle, cycle[1:] + cycle[:1], strict=True)
        cycles.append(sorted(int(pair_of[edge]) for edge in edges))
    implied = []
    for (source, target), pair in pair_of.items():
        without = graph.copy()
        without.remove_edge(source, target)
        if nx.has_path(without, source, target):
            implied.append(int(pair))
    return {"cycles": sorted(cycles), "implied_by_a_longer_path": sorted(implied)}


def split_pairs(gold: list[dict], seed: int = SEED, dev_share: float = DEV_SHARE) -> dict:
    """A seeded split, stratified by label. Rounded by largest remainder, so the share holds."""
    by_label = {
        label: sorted(int(r["_pair"]) for r in gold if r["label"] == label) for label in LABELS
    }
    wanted = round(len(gold) * dev_share)
    exact = {label: len(pairs) * dev_share for label, pairs in by_label.items()}
    take = {label: int(value) for label, value in exact.items()}
    by_remainder = sorted(LABELS, key=lambda label: (take[label] - exact[label], label))
    for label in by_remainder[: wanted - sum(take.values())]:
        take[label] += 1
    development, test = [], []
    for label, pairs in by_label.items():
        drawn = random.Random(f"{seed}:{label}").sample(pairs, take[label])
        development += drawn
        test += [p for p in pairs if p not in drawn]
    return {
        "development": sorted(development),
        "test": sorted(test),
        "counts": {
            label: {"development": take[label], "test": len(by_label[label]) - take[label]}
            for label in LABELS
        },
    }


def main() -> int:
    rows, blank, key = read_rows(RAW), read_rows(BLANK), read_rows(KEY)
    problems = find_problems(rows, blank)
    print(f"checked {len(rows)} pairs against {BLANK.name}: {len(problems)} problems")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print("Nothing was written. Labels are not fixed here.")
        return 1

    gold = convert(rows, key)
    write_gold(gold, GOLD)
    groups = {k["pair"]: k["group"] for k in key}
    counts = Counter((groups[r["_pair"]], r["label"]) for r in gold)
    print(f"{'group':16s} {'hard':>5s} {'soft':>5s} {'none':>5s} {'total':>6s}")
    for group in sorted(set(groups.values())):
        row = [counts[(group, label)] for label in LABELS]
        print(f"{group:16s} {row[0]:5d} {row[1]:5d} {row[2]:5d} {sum(row):6d}")
    totals = [sum(counts[(g, label)] for g in set(groups.values())) for label in LABELS]
    print(f"{'all':16s} {totals[0]:5d} {totals[1]:5d} {totals[2]:5d} {sum(totals):6d}")

    findings = graph_findings(gold)
    print(
        f"cycles among the labels: {len(findings['cycles'])}, as pair numbers {findings['cycles']}"
    )
    implied = findings["implied_by_a_longer_path"]
    print(f"labelled and implied by a longer path: {len(implied)}, pairs {implied}")

    split = split_pairs(gold)
    SPLIT.write_text(
        json.dumps(
            {
                "version": "set2_split_v1",
                "seed": SEED,
                "development_share": DEV_SHARE,
                "stratified_by": "label",
                "rules": {
                    "development": "threshold calibration only. Scores must never come from it.",
                    "test": "final scores only. Never use it to choose a threshold or a setting.",
                },
                "pair_numbers_are_from": "private_keys/ds101_set2_key.csv",
                "labels_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
                **split,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"split: {len(split['development'])} development, {len(split['test'])} test")
    for label, part in split["counts"].items():
        print(f"  {label}: {part['development']} development, {part['test']} test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
