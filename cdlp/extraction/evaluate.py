"""Concept extraction precision / recall / F1 against the hand-annotated concept list.

Initial code: Vaidehi. Gold edge merging and Cohen's kappa moved to
data/gold/merge_gold.py (one merger, per course, kappa raw and with the shortcut rule),
so this module never writes gold files.
Usage:
    python -m cdlp.extraction.evaluate [--concepts outputs/<course>/concepts.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

GOLD_DIR = Path("data/gold")
RESULTS_DIR = Path("cdlp/extraction/results")


def evaluate_concept_extraction(
    extracted_concepts_path: Path,
    gold_concepts_path: Path = GOLD_DIR / "gold_concepts.json",
) -> dict[str, float]:
    """Calculate Precision, Recall, and F1 for concept extraction against gold standard."""
    extracted_data = json.loads(Path(extracted_concepts_path).read_text(encoding="utf-8"))
    gold_data = json.loads(Path(gold_concepts_path).read_text(encoding="utf-8"))

    extracted_ids = {c["id"] for c in extracted_data.get("concepts", [])}
    # Also include aliases
    extracted_all = set(extracted_ids)
    for c in extracted_data.get("concepts", []):
        for alias in c.get("aliases", []):
            extracted_all.add(alias.lower().replace(" ", "_"))

    gold_ids = {c["id"] for c in gold_data.get("concepts", [])}

    tp = len(extracted_ids & gold_ids)
    fp = len(extracted_ids - gold_ids)
    fn = len(gold_ids - extracted_ids)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "extracted_count": len(extracted_ids),
        "gold_count": len(gold_ids),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_full_evaluation(
    extracted_concepts_path: Path = Path("outputs/concepts.json"),
    results_dir: Path = RESULTS_DIR,
    gold_concepts_path: Path = GOLD_DIR / "gold_concepts.json",
) -> dict[str, Any]:
    """Concept extraction metrics -> results_dir/evaluation_metrics.json."""
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics = evaluate_concept_extraction(extracted_concepts_path, gold_concepts_path)
    report = {
        "concepts": str(extracted_concepts_path),
        "gold_concepts": str(gold_concepts_path),
        "concept_evaluation": metrics,
    }
    (results_dir / "evaluation_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Concept extraction: P {metrics['precision']:.2f}, R {metrics['recall']:.2f}, "
        f"F1 {metrics['f1']:.2f} -> {results_dir / 'evaluation_metrics.json'}"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, default=Path("outputs/concepts.json"))
    parser.add_argument("--gold-concepts", type=Path, default=GOLD_DIR / "gold_concepts.json")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    a = parser.parse_args()
    run_full_evaluation(a.concepts, a.results_dir, a.gold_concepts)
