"""Evaluate discovered edges against gold prerequisite labels.

    python -m cdlp.discovery.evaluate --relationships outputs/ds101/relationships.json \
        [--gold data/gold/<course>/gold_edges.csv] --out cdlp/discovery/results/evaluation.json

Counting (directed pairs):
- TP: gold says hard/soft and the edge was predicted.
- FP: an edge was predicted and gold does NOT say hard/soft. That includes pairs
  labelled none AND pairs missing from gold entirely (otherwise precision is
  inflated by only scoring the few pairs someone thought to label negative).
- FN: gold says hard/soft and the edge was not predicted.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

POSITIVE_LABELS = {"hard", "soft"}


def load_gold(path: Path) -> list[dict]:
    with Path(path).open(newline="") as file:
        return list(csv.DictReader(file))


def _is_predicted(row: dict) -> bool:
    # raw discovery records carry relationship=DIRECT/NONE; contract edges are all predictions
    return row.get("relationship", "DIRECT") == "DIRECT"


def evaluate(relationships: list[dict], gold: list[dict]) -> dict:
    gold_map = {(row["source"], row["target"]): row["label"].strip().lower() for row in gold}
    predicted = {(row["source"], row["target"]): row for row in relationships if _is_predicted(row)}

    true_positive = false_positive = false_negative = strength_correct = 0
    false_positive_pairs = []

    for pair, row in sorted(predicted.items()):
        if gold_map.get(pair) in POSITIVE_LABELS:
            true_positive += 1
            if str(row.get("strength", "")).lower() == gold_map[pair]:
                strength_correct += 1
        else:
            false_positive += 1
            false_positive_pairs.append(
                {"source": pair[0], "target": pair[1], "gold": gold_map.get(pair, "unlabelled")}
            )

    false_negative_pairs = [
        {"source": s, "target": t, "gold": label}
        for (s, t), label in sorted(gold_map.items())
        if label in POSITIVE_LABELS and (s, t) not in predicted
    ]
    false_negative = len(false_negative_pairs)

    precision = true_positive / (true_positive + false_positive) if predicted else 0.0
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "strength_accuracy": strength_correct / true_positive if true_positive else 0.0,
        "false_positive_pairs": false_positive_pairs,
        "false_negative_pairs": false_negative_pairs,
    }


def prompt_version_of(relationships: list[dict]) -> str:
    """The prompt the edges record ("llm_discover_v3_1"), so results never name a default."""
    methods = {str(r.get("method", "")) for r in relationships}
    method = methods.pop() if len(methods) == 1 else ""
    return method.removeprefix("llm_") if method.startswith("llm_") else "unknown"


def main() -> None:
    from cdlp.discovery.llm_discovery import TEMPERATURE
    from cdlp.shared.io import read_json
    from cdlp.shared.llm import DEFAULT_MODEL, DEFAULT_SEED, PROVIDER

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--gold", type=Path, help="default: data/gold/<course_id>/gold_edges.csv")
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).parent / "results/evaluation.json"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model that produced the edges")
    parser.add_argument("--prompt-version", help="default: the method the edges record")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="LLM seed used")
    args = parser.parse_args()

    data = read_json(args.relationships)
    args.gold = args.gold or Path("data/gold") / data["course_id"] / "gold_edges.csv"
    metrics = evaluate(data["relationships"], load_gold(args.gold))
    result = {
        "config": {
            "relationships": str(args.relationships),
            "course_id": data.get("course_id"),
            "gold": str(args.gold),
            "provider": PROVIDER,
            "model": args.model,
            "prompt_version": args.prompt_version or prompt_version_of(data["relationships"]),
            "temperature": TEMPERATURE,
            "seed": args.seed,
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "metrics": metrics,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f}",
        f"-> {args.out}",
    )


if __name__ == "__main__":
    main()
