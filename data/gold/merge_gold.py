"""Merge the annotator files per course and report Cohen's kappa both ways.

    python data/gold/merge_gold.py [--annotations data/gold/annotations]
        [--courses data/gold/courses.json] [--adjudication data/gold/adjudication.csv]
        [--out-dir data/gold/merged]

Reads every `annotations/annotator_<x>.csv` (source,target,label,note) exactly as
committed. Each pair belongs to the course in `courses.json` that holds both concepts
(a pair matching no course, or two, is an error).

Agreement (`<out-dir>/agreement.json`), for every annotator pair with >= 2 shared
pairs, per course and overall, computed **before any adjudication**:
- raw: Cohen's kappa on the committed labels;
- shortcut rule: the same, after this mechanical rule is applied to each annotator's
  file on its own: a pair labelled hard or soft becomes none if that annotator's own
  hard/soft pairs already form a path from A to B through another concept. The
  number of labels the rule changed is reported per annotator and course.

Merge (`<out-dir>/<course>/gold_edges.csv`, columns source,target,label,agreement,note,
the same as data/gold/gold_edges.csv): majority of the committed (raw) labels. A tie
is decided only by a row in the adjudication file (source,target,label,note); without
one the pair is left out of the gold file and listed as unresolved in agreement.json.
Nothing here edits an annotator file or data/gold/gold_edges.csv.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

GOLD = Path(__file__).resolve().parent
LABELS = ("hard", "soft", "none")
POSITIVE = {"hard", "soft"}
COLUMNS = ["source", "target", "label", "agreement", "note"]
RULE = (
    "A pair labelled hard or soft becomes none if the same annotator's own hard/soft "
    "pairs already form a path from A to B through another concept."
)

Pair = tuple[str, str]


def load_annotations(folder: Path) -> dict[str, dict[Pair, dict]]:
    """annotator letter -> {(source, target): {"label", "note"}}; empty files kept."""
    out = {}
    for path in sorted(folder.glob("annotator_*.csv")):
        rows = {}
        with path.open(newline="", encoding="utf-8") as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                source, target = (
                    (row.get("source") or "").strip(),
                    (row.get("target") or "").strip(),
                )
                if not source and not target:
                    continue
                label = (row.get("label") or "").strip().lower()
                if label not in LABELS:
                    raise ValueError(f"{path.name} line {n}: label {label!r} not in {LABELS}")
                if (source, target) in rows:
                    raise ValueError(f"{path.name} line {n}: duplicate pair {source} -> {target}")
                rows[(source, target)] = {"label": label, "note": (row.get("note") or "").strip()}
        out[path.stem.removeprefix("annotator_")] = rows
    return out


def course_of(pair: Pair, courses: dict[str, list[str]]) -> str:
    hits = [c for c, ids in courses.items() if set(pair) <= set(ids)]
    if len(hits) != 1:
        raise ValueError(f"pair {pair[0]} -> {pair[1]} matches courses {hits}, need exactly one")
    return hits[0]


def apply_shortcut_rule(labels: dict[Pair, str]) -> dict[Pair, str]:
    """The rule above, on one annotator's labels. Decided on the committed labels only
    (not iterated), so the result does not depend on the order of the pairs."""
    succ: dict[str, set[str]] = defaultdict(set)
    for (a, b), label in labels.items():
        if label in POSITIVE:
            succ[a].add(b)

    def has_longer_path(a: str, b: str) -> bool:
        stack, seen = [x for x in succ[a] if x != b], set()
        while stack:
            node = stack.pop()
            if node == b:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack += succ[node]
        return False

    return {
        pair: "none" if label in POSITIVE and has_longer_path(*pair) else label
        for pair, label in labels.items()
    }


def cohen_kappa(x: list[str], y: list[str]) -> float | None:
    """Cohen's kappa; None when chance agreement is 1 (both raters used one label)."""
    n = len(x)
    observed = sum(a == b for a, b in zip(x, y, strict=True)) / n
    expected = sum((x.count(c) / n) * (y.count(c) / n) for c in set(x) | set(y))
    if expected == 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def agreement(annotations: dict[str, dict[Pair, dict]], courses: dict[str, list[str]]) -> dict:
    raw = {a: {p: r["label"] for p, r in rows.items()} for a, rows in annotations.items()}
    ruled = {a: apply_shortcut_rule(labels) for a, labels in raw.items()}
    changed = {
        a: {
            course: sorted(
                f"{s}->{t}: {raw[a][(s, t)]}->none"
                for (s, t) in raw[a]
                if raw[a][(s, t)] != ruled[a][(s, t)] and course_of((s, t), courses) == course
            )
            for course in courses
        }
        for a in raw
    }
    pairs = []
    for a, b in itertools.combinations(sorted(raw), 2):
        shared = sorted(set(raw[a]) & set(raw[b]))
        scopes = {"all": shared}
        for course in courses:
            scopes[course] = [p for p in shared if course_of(p, courses) == course]
        for scope, keys in scopes.items():
            if len(keys) < 2:
                continue
            pairs.append(
                {
                    "annotators": [a, b],
                    "scope": scope,
                    "n_pairs": len(keys),
                    "kappa_raw": cohen_kappa([raw[a][k] for k in keys], [raw[b][k] for k in keys]),
                    "kappa_shortcut_rule": cohen_kappa(
                        [ruled[a][k] for k in keys], [ruled[b][k] for k in keys]
                    ),
                }
            )
    return {"pairs": pairs, "labels_changed_by_rule": changed}


def load_adjudication(path: Path | None) -> dict[Pair, dict]:
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        rows = {(r["source"].strip(), r["target"].strip()): r for r in csv.DictReader(f)}
    for pair, r in rows.items():
        if r["label"].strip().lower() not in LABELS:
            raise ValueError(f"adjudication {pair}: label {r['label']!r} not in {LABELS}")
    return rows


def merge(
    annotations: dict[str, dict[Pair, dict]],
    courses: dict[str, list[str]],
    adjudication: dict[Pair, dict],
) -> tuple[dict[str, list[dict]], list[dict]]:
    """(course -> gold rows, unresolved ties)."""
    votes: dict[Pair, list[tuple[str, dict]]] = defaultdict(list)
    for annotator, rows in sorted(annotations.items()):
        for pair, row in rows.items():
            votes[pair].append((annotator, row))
    gold: dict[str, list[dict]] = {c: [] for c in courses}
    unresolved = []
    for pair in sorted(votes):
        course = course_of(pair, courses)
        counts = Counter(row["label"] for _, row in votes[pair])
        ranked = counts.most_common()
        notes = "; ".join(row["note"] for _, row in votes[pair] if row["note"])
        n = len(votes[pair])
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            tie = {"source": pair[0], "target": pair[1], "course": course}
            tie["labels"] = {a: row["label"] for a, row in votes[pair]}
            if pair not in adjudication:
                unresolved.append(tie)
                continue
            adj = adjudication[pair]
            label = adj["label"].strip().lower()
            agreement_str = f"{counts[label]}/{n} (adjudicated)"
            notes = "; ".join(x for x in [notes, f"adjudication: {adj.get('note', '')}"] if x)
        else:
            label = ranked[0][0]
            agreement_str = f"{ranked[0][1]}/{n}"
        gold[course].append(
            {
                "source": pair[0],
                "target": pair[1],
                "label": label,
                "agreement": agreement_str,
                "note": notes,
            }
        )
    return gold, unresolved


def write_gold(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run(annotations_dir: Path, courses_file: Path, adjudication_file: Path | None, out: Path):
    annotations = load_annotations(annotations_dir)
    courses = json.loads(courses_file.read_text(encoding="utf-8"))["courses"]
    gold, unresolved = merge(annotations, courses, load_adjudication(adjudication_file))
    for course, rows in gold.items():
        write_gold(out / course / "gold_edges.csv", rows)
    report = {
        "computed_on": "labels as committed, before any adjudication",
        "shortcut_rule": RULE,
        "annotators": {a: len(rows) for a, rows in sorted(annotations.items())},
        **agreement(annotations, courses),
        "merge": {
            "rule": "majority of committed labels; ties only by the adjudication file",
            "gold_rows": {c: len(rows) for c, rows in gold.items()},
            "unresolved": unresolved,
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "agreement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=GOLD / "annotations")
    parser.add_argument("--courses", type=Path, default=GOLD / "courses.json")
    parser.add_argument("--adjudication", type=Path, default=GOLD / "adjudication.csv")
    parser.add_argument("--out-dir", type=Path, default=GOLD / "merged")
    args = parser.parse_args(argv)
    report = run(args.annotations, args.courses, args.adjudication, args.out_dir)
    for row in report["pairs"]:
        a, b = row["annotators"]
        print(
            f"kappa {a} vs {b} [{row['scope']}, n={row['n_pairs']}]: "
            f"raw {row['kappa_raw']}, shortcut rule {row['kappa_shortcut_rule']}"
        )
    for a, per_course in report["labels_changed_by_rule"].items():
        n = sum(len(v) for v in per_course.values())
        print(f"shortcut rule changed {n} of annotator {a}'s labels")
    m = report["merge"]
    print(f"gold rows {m['gold_rows']}; unresolved ties: {len(m['unresolved'])} -> {args.out_dir}")


if __name__ == "__main__":
    main()
