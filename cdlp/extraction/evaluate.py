"""Gold standard annotation merging, inter-annotator agreement (Cohen's kappa),
and concept extraction precision / recall evaluation.

Owner: Vaidehi.
Usage:
    python -m cdlp.extraction.evaluate
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from sklearn.metrics import cohen_kappa_score
except ImportError:
    # Pure-Python Cohen's kappa fallback for lightweight environments
    def cohen_kappa_score(y1: list[str], y2: list[str]) -> float:
        if not y1 or not y2 or len(y1) != len(y2):
            return 0.0
        n = len(y1)
        categories = list(set(y1) | set(y2))
        po = sum(1 for a, b in zip(y1, y2, strict=True) if a == b) / n
        pe = sum((y1.count(c) / n) * (y2.count(c) / n) for c in categories)
        if pe == 1.0:
            return 1.0
        return (po - pe) / (1 - pe)


GOLD_DIR = Path("data/gold")
ANNOTATIONS_DIR = GOLD_DIR / "annotations"
RESULTS_DIR = Path("cdlp/extraction/results")


def load_annotation_file(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Load one annotator's CSV: (source, target) -> {label, note}."""
    annotations: dict[tuple[str, str], dict[str, str]] = {}
    if not path.exists():
        return annotations

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row.get("source", "").strip().lower()
            dst = row.get("target", "").strip().lower()
            label = row.get("label", "").strip().lower()
            note = row.get("note", "").strip()
            if src and dst and label in ("hard", "soft", "none"):
                annotations[(src, dst)] = {"label": label, "note": note}
    return annotations


def compute_pairwise_kappas(
    annotator_data: dict[str, dict[tuple[str, str], dict[str, str]]],
) -> dict[str, float]:
    """Compute Cohen's kappa for every pair of annotators with overlapping annotations."""
    names = sorted(annotator_data.keys())
    kappas: dict[str, float] = {}

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name1, name2 = names[i], names[j]
            d1, d2 = annotator_data[name1], annotator_data[name2]
            common_pairs = sorted(set(d1.keys()) & set(d2.keys()))

            if len(common_pairs) >= 2:
                labels1 = [d1[pair]["label"] for pair in common_pairs]
                labels2 = [d2[pair]["label"] for pair in common_pairs]
                kappa = float(cohen_kappa_score(labels1, labels2))
                pair_key = f"{name1}_vs_{name2}"
                kappas[pair_key] = round(kappa, 4)

    return kappas


def merge_annotations(
    annotations_dir: Path = ANNOTATIONS_DIR,
    out_csv: Path = GOLD_DIR / "gold_edges.csv",
    out_concepts_json: Path = GOLD_DIR / "gold_concepts.json",
) -> tuple[int, int, dict[str, float]]:
    """Merge all annotator CSVs into gold_edges.csv and gold_concepts.json."""
    csv_files = sorted(annotations_dir.glob("annotator_*.csv"))
    annotator_data: dict[str, dict[tuple[str, str], dict[str, str]]] = {}

    for file_path in csv_files:
        annotator_id = file_path.stem
        annotator_data[annotator_id] = load_annotation_file(file_path)

    # Compute Cohen's kappa
    kappas = compute_pairwise_kappas(annotator_data)

    # Majority vote per pair
    pair_votes: dict[tuple[str, str], list[str]] = defaultdict(list)
    pair_notes: dict[tuple[str, str], list[str]] = defaultdict(list)

    for data in annotator_data.values():
        for pair, info in data.items():
            pair_votes[pair].append(info["label"])
            if info["note"]:
                pair_notes[pair].append(info["note"])

    merged_rows: list[dict[str, str]] = []
    gold_concept_ids: set[str] = set()

    for (src, dst), votes in sorted(pair_votes.items()):
        # Most common vote
        counts = Counter(votes)
        consensus_label = counts.most_common(1)[0][0]
        notes_str = "; ".join(pair_notes[(src, dst)])

        merged_rows.append(
            {
                "source": src,
                "target": dst,
                "label": consensus_label,
                "agreement": f"{counts[consensus_label]}/{len(votes)}",
                "note": notes_str,
            }
        )
        gold_concept_ids.add(src)
        gold_concept_ids.add(dst)

    # Write gold_edges.csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "target", "label", "agreement", "note"])
        writer.writeheader()
        writer.writerows(merged_rows)

    # Write gold_concepts.json
    gold_concepts_data = {
        "schema_version": "1.0",
        "course_id": "ds101",
        "concepts": [
            {
                "id": cid,
                "name": cid.replace("_", " ").title(),
                "aliases": [cid.upper()] if len(cid) <= 4 else [],
                "description": f"Gold standard concept {cid}.",
                "sources": [{"doc": "gold_standard", "page": 1}],
            }
            for cid in sorted(gold_concept_ids)
        ],
    }
    out_concepts_json.write_text(
        json.dumps(gold_concepts_data, indent=2, ensure_ascii=False) + "\n"
    )

    return len(merged_rows), len(gold_concept_ids), kappas


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
) -> dict[str, Any]:
    """Execute gold merge, Cohen's kappa calculation, and extraction evaluation."""
    results_dir.mkdir(parents=True, exist_ok=True)

    edge_count, concept_count, kappas = merge_annotations()

    avg_kappa = round(sum(kappas.values()) / len(kappas), 4) if kappas else 0.0

    concept_metrics = evaluate_concept_extraction(extracted_concepts_path)

    report = {
        "gold_edges_merged": edge_count,
        "gold_concepts_count": concept_count,
        "cohens_kappa_pairwise": kappas,
        "cohens_kappa_average": avg_kappa,
        "concept_evaluation": concept_metrics,
    }

    # Save metrics JSON
    metrics_file = results_dir / "evaluation_metrics.json"
    metrics_file.write_text(json.dumps(report, indent=2) + "\n")

    # Save human-readable report Markdown
    report_md = f"""# Concept Extraction & Gold Standard Evaluation Report
Owner: Vaidehi (@vkumaw)

## 1. Gold Standard Agreement (Cohen's Kappa)
- **Total merged edges**: {edge_count}
- **Unique gold concepts**: {concept_count}
- **Average Cohen's $\\kappa$**: {avg_kappa} (target $\\ge 0.60$)

### Pairwise Inter-Annotator Agreement:
| Annotator Pair | Cohen's $\\kappa$ | Agreement Level |
|---|---|---|
"""
    for pair, score in kappas.items():
        level = "Substantial / Almost Perfect" if score >= 0.75 else "Moderate"
        report_md += f"| {pair} | {score} | {level} |\n"

    report_md += f"""
## 2. Concept Extraction (RQ0) Performance vs. Gold Standard
- **Precision**: {concept_metrics["precision"]:.2%}
- **Recall**: {concept_metrics["recall"]:.2%}
- **F1 Score**: {concept_metrics["f1"]:.2%}
- **True Positives**: {concept_metrics["true_positives"]}
- **False Positives**: {concept_metrics["false_positives"]}
- **False Negatives**: {concept_metrics["false_negatives"]}
"""
    (results_dir / "README.md").write_text(report_md)
    print(
        f"Evaluation complete. Average Cohen's kappa: {avg_kappa}, "
        f"Concept F1: {concept_metrics['f1']:.2%}"
    )
    return report


if __name__ == "__main__":
    run_full_evaluation()
