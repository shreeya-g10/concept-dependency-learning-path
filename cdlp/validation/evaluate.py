"""RQ1 harness: score every discovery / validation setting against gold, per course.

    python -m cdlp.validation.evaluate --config cdlp/validation/configs/rq1/ds101.json
    python -m cdlp.validation.evaluate --config cdlp/validation/configs/rq1/al_cpl.json

RQ1: does an independent validation agent improve the precision of LLM-proposed
prerequisite edges, and at what cost to recall?

This script makes NO LLM call. It reads the files each setting already produced in the
course's run folder and writes one results file per course,
`<out-dir>/rq1_<course_id>.json`, plus `rq1_<dataset>_micro.json` (pooled counts) when a
dataset has several courses (AL-CPL has four domains). Page 3 of the website charts them.

What counts as a predicted edge
- `relationships` settings (discovery only, baseline prompt): every proposed edge. An
  edge the LLM proposed in both directions (`bidirectional`) predicts both pairs unless
  the config says `"bidirectional": "forward"`.
- `validated` settings (single judge, self-consistency, full agent, agent minus a check):
  ACCEPT edges only. HUMAN_REVIEW is not a prediction; its rate is reported next to P/R.

Scoring conventions (set per dataset in the config)
- `scoring`: `direct` compares predicted pairs with gold pairs. `closure` first takes the
  transitive closure of the predicted edges, for benchmarks whose positives include
  shortcut pairs (AL-CPL). `auto` uses the closure when some gold positive is implied by
  a path of other gold positives (University Course: not stated by the dataset).
- `unlabelled_pairs`: `false_positive` counts a predicted pair that gold does not label
  as an error (our own gold, same rule as cdlp/discovery/evaluate.py). `ignore` scores
  only labelled pairs (benchmarks, which label a fixed pair list).
- `exclude_pairs`: optional CSV (`source,target`) of pairs used to tune thresholds. They
  are dropped from gold and predictions so tuning data never scores the result.

LLM calls per edge = (the setting's calls + the calls of the setting it builds on, e.g.
discovery under a validator) / edges the setting scored (proposed edges for validators).
Calls come from `<run_dir>/<setting>.stats.json` (`{"llm_calls": n}`); without that file
the value is null. Every result records the config, models, prompt versions, temperature,
seed, git commit and date.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

POSITIVE_LABELS = {"hard", "soft"}
DECISIONS = ("ACCEPT", "REJECT", "HUMAN_REVIEW")
RESULTS = Path(__file__).parent / "results"


# ---- gold -------------------------------------------------------------------
def load_gold(path: Path, concept_ids: set[str] | None = None) -> dict[tuple[str, str], str]:
    """(source, target) -> hard / soft / none. Restricted to the course's concepts when
    given, so one gold file can hold several courses."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    gold = {}
    for row in rows:
        pair = (row["source"].strip(), row["target"].strip())
        if concept_ids is not None and not set(pair) <= concept_ids:
            continue
        gold[pair] = row["label"].strip().lower()
    return gold


def load_pairs(path: Path) -> set[tuple[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return {(r["source"].strip(), r["target"].strip()) for r in csv.DictReader(f)}


# ---- graph helpers (own copy: modules never import each other) ---------------
def _successors(pairs) -> dict[str, set[str]]:
    succ: dict[str, set[str]] = {}
    for u, v in pairs:
        succ.setdefault(u, set()).add(v)
    return succ


def _reachable(succ: dict, start: str, skip: tuple | None = None) -> set[str]:
    seen, stack = set(), [w for w in succ.get(start, ()) if (start, w) != skip]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(succ.get(node, ()))
    return seen


def transitive_closure(pairs) -> set[tuple[str, str]]:
    """All (u, w), u != w, with a directed path u -> ... -> w."""
    succ = _successors(set(pairs))
    return {(u, w) for u in succ for w in _reachable(succ, u) if u != w}


def implied_pairs(pairs) -> set[tuple[str, str]]:
    """Pairs also reachable through a path of the OTHER pairs (length >= 2)."""
    pairs = set(pairs)
    succ = _successors(pairs)
    return {(u, v) for u, v in pairs if v in _reachable(succ, u, skip=(u, v))}


def resolve_scoring(scoring: str, gold: dict[tuple[str, str], str]) -> tuple[str, int]:
    """Return (direct | closure, number of gold positives implied by other positives)."""
    positives = {pair for pair, label in gold.items() if label in POSITIVE_LABELS}
    implied = len(implied_pairs(positives))
    if scoring == "auto":
        return ("closure" if implied else "direct"), implied
    if scoring not in {"direct", "closure"}:
        raise ValueError(f"scoring must be direct, closure or auto, not {scoring!r}")
    return scoring, implied


# ---- predictions --------------------------------------------------------------
def predicted_pairs(data: dict, kind: str, bidirectional: str = "both") -> set[tuple[str, str]]:
    if kind == "relationships":
        pairs = set()
        for r in data["relationships"]:
            pairs.add((r["source"], r["target"]))
            if r.get("bidirectional") and bidirectional == "both":
                pairs.add((r["target"], r["source"]))
        return pairs
    if kind == "validated":
        return {(e["source"], e["target"]) for e in data["edges"] if e["decision"] == "ACCEPT"}
    raise ValueError(f"setting kind must be relationships or validated, not {kind!r}")


def decision_counts(data: dict, kind: str) -> dict[str, int] | None:
    if kind != "validated":
        return None
    return {d: sum(e["decision"] == d for e in data["edges"]) for d in DECISIONS}


def n_scored_edges(data: dict, kind: str) -> int:
    return len(data["relationships"] if kind == "relationships" else data["edges"])


# ---- metrics ------------------------------------------------------------------
def score(
    predicted: set[tuple[str, str]],
    gold: dict[tuple[str, str], str],
    *,
    scoring: str = "direct",
    unlabelled_pairs: str = "false_positive",
) -> dict:
    """TP / FP / FN and P / R / F1 for one set of predicted pairs.

    scoring must already be resolved to direct or closure (see resolve_scoring).
    """
    if unlabelled_pairs not in {"false_positive", "ignore"}:
        raise ValueError(f"unlabelled_pairs must be false_positive or ignore: {unlabelled_pairs!r}")
    pairs = transitive_closure(predicted) if scoring == "closure" else set(predicted)
    pairs = {(u, v) for u, v in pairs if u != v}
    if unlabelled_pairs == "ignore":
        pairs = {p for p in pairs if p in gold}
    positives = {p for p, label in gold.items() if label in POSITIVE_LABELS}

    tp = len(pairs & positives)
    fp = len(pairs - positives)
    fn = len(positives - pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "scored_pairs": len(pairs),
        "false_positive_pairs": [
            {"source": s, "target": t, "gold": gold.get((s, t), "unlabelled")}
            for s, t in sorted(pairs - positives)
        ],
        "false_negative_pairs": [
            {"source": s, "target": t, "gold": gold[(s, t)]} for s, t in sorted(positives - pairs)
        ],
    }


def read_calls(run_dir: Path, setting: str) -> int | None:
    path = run_dir / f"{setting}.stats.json"
    if not path.is_file():
        return None
    return int(json.loads(path.read_text(encoding="utf-8"))["llm_calls"])


# ---- config -------------------------------------------------------------------
def load_config(path: Path) -> dict:
    """Read a dataset config; `settings_file` is resolved relative to the config."""
    path = Path(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if "settings_file" in config:
        shared = json.loads((path.parent / config["settings_file"]).read_text(encoding="utf-8"))
        config["settings"] = shared["settings"]
        config.setdefault("models", shared.get("models"))
        config.setdefault("prompt_versions", shared.get("prompt_versions"))
        config.setdefault("temperature", shared.get("temperature"))
        config.setdefault("seed", shared.get("seed"))
    names = [s["name"] for s in config["settings"]]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate setting names in {path}")
    for s in config["settings"]:
        if s.get("adds_calls_of") and s["adds_calls_of"] not in names:
            raise ValueError(f"{s['name']}: adds_calls_of {s['adds_calls_of']!r} is not a setting")
    return config


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _course_concepts(course: dict, base: Path) -> set[str] | None:
    if not course.get("concepts"):
        return None
    path = base / course["concepts"]
    if not path.is_file():
        return None
    return {c["id"] for c in json.loads(path.read_text(encoding="utf-8"))["concepts"]}


def evaluate_course(config: dict, course: dict, base: Path = Path(".")) -> dict:
    """Score every setting of the config on one course. Missing files -> status missing."""
    run_dir = base / course["run_dir"]
    concept_ids = _course_concepts(course, base)
    gold = load_gold(base / course["gold"], concept_ids)
    excluded = set()
    if config.get("exclude_pairs"):
        excluded = load_pairs(base / config["exclude_pairs"])
        gold = {p: label for p, label in gold.items() if p not in excluded}
    scoring, implied = resolve_scoring(config.get("scoring", "direct"), gold)
    unlabelled = config.get("unlabelled_pairs", "false_positive")

    calls = {s["name"]: read_calls(run_dir, s["name"]) for s in config["settings"]}
    rows = []
    for setting in config["settings"]:
        name, kind = setting["name"], setting["kind"]
        row = {"setting": name, "kind": kind, "predictions": setting["predictions"]}
        path = run_dir / setting["predictions"]
        if not path.is_file():
            row.update(status="missing", precision=None, recall=None, f1=None)
            row.update(human_review_rate=None, llm_calls_per_edge=None)
            rows.append(row)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        predicted = predicted_pairs(data, kind, config.get("bidirectional", "both")) - excluded
        row["status"] = "ok"
        row.update(score(predicted, gold, scoring=scoring, unlabelled_pairs=unlabelled))

        counts = decision_counts(data, kind)
        edges = n_scored_edges(data, kind)
        row["edges"] = edges
        row["decisions"] = counts
        row["human_review_rate"] = (
            (counts["HUMAN_REVIEW"] / edges if edges else 0.0) if counts else None
        )

        own = calls[name]
        base_setting = setting.get("adds_calls_of")
        extra = calls[base_setting] if base_setting else 0
        total = None if own is None or extra is None else own + extra
        row["llm_calls"] = own
        row["llm_calls_total"] = total
        row["llm_calls_per_edge"] = total / edges if total is not None and edges else None
        rows.append(row)

    positives = sum(label in POSITIVE_LABELS for label in gold.values())
    return {
        "experiment": "rq1",
        "dataset": config["dataset"],
        "course_id": course["course_id"],
        "scoring": scoring,
        "gold_summary": {
            "pairs": len(gold),
            "positive": positives,
            "none": len(gold) - positives,
            "positives_implied_by_other_positives": implied,
            "excluded_pairs": len(excluded),
        },
        "rows": rows,
    }


def micro_average(dataset: str, results: list[dict]) -> dict:
    """Pool TP / FP / FN over the courses of one dataset (e.g. the 4 AL-CPL domains)."""
    names = [r["setting"] for r in results[0]["rows"]]
    rows = []
    for i, name in enumerate(names):
        per_course = [res["rows"][i] for res in results]
        ok = [r for r in per_course if r["status"] == "ok"]
        row = {"setting": name, "kind": per_course[0]["kind"], "courses": len(ok)}
        if len(ok) < len(per_course):
            row.update(status="missing", precision=None, recall=None, f1=None)
            row.update(human_review_rate=None, llm_calls_per_edge=None)
            rows.append(row)
            continue
        tp = sum(r["true_positive"] for r in ok)
        fp = sum(r["false_positive"] for r in ok)
        fn = sum(r["false_negative"] for r in ok)
        p = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        edges = sum(r["edges"] for r in ok)
        review = [r["decisions"]["HUMAN_REVIEW"] for r in ok if r["decisions"]]
        totals = [r["llm_calls_total"] for r in ok]
        row.update(
            status="ok",
            true_positive=tp,
            false_positive=fp,
            false_negative=fn,
            precision=p,
            recall=rec,
            f1=2 * p * rec / (p + rec) if p + rec else 0.0,
            edges=edges,
            human_review_rate=(sum(review) / edges if edges else 0.0) if review else None,
            llm_calls_per_edge=(
                sum(totals) / edges if edges and all(t is not None for t in totals) else None
            ),
        )
        rows.append(row)
    return {
        "experiment": "rq1",
        "dataset": dataset,
        "course_id": f"{dataset} (micro, {len(results)} courses)",
        "scoring": sorted({r["scoring"] for r in results}),
        "rows": rows,
    }


def run(config_path: Path, out_dir: Path = RESULTS, base: Path = Path("."), strict=False):
    config = load_config(config_path)
    meta = {
        "config_file": str(config_path),
        **{k: v for k, v in config.items() if k != "courses"},
        "git_commit": _git_commit(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    written, results = [], []
    for course in config["courses"]:
        result = {**evaluate_course(config, course, base), "config": {**meta, "course": course}}
        missing = [r["setting"] for r in result["rows"] if r["status"] == "missing"]
        if missing and strict:
            raise SystemExit(f"{course['course_id']}: no predictions for {', '.join(missing)}")
        results.append(result)
        path = out_dir / f"rq1_{course['course_id']}.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        written.append(path)
        print(_summary_line(result, missing), file=sys.stderr)
    if len(results) > 1:
        pooled = {**micro_average(config["dataset"], results), "config": meta}
        path = out_dir / f"rq1_{config['dataset']}_micro.json"
        path.write_text(json.dumps(pooled, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def _summary_line(result: dict, missing: list[str]) -> str:
    parts = [
        f"{r['setting']} P={r['precision']:.2f} R={r['recall']:.2f} F1={r['f1']:.2f}"
        for r in result["rows"]
        if r["status"] == "ok"
    ]
    tail = f"; missing: {', '.join(missing)}" if missing else ""
    return f"{result['course_id']} ({result['scoring']}): " + " | ".join(parts) + tail


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument(
        "--base", type=Path, default=Path("."), help="paths in the config are relative to this"
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail when a setting has no predictions"
    )
    args = parser.parse_args(argv)
    for path in run(args.config, args.out_dir, args.base, args.strict):
        print(f"-> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
