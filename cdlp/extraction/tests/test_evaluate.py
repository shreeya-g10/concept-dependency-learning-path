"""Unit tests for gold standard merging, Cohen's kappa, and evaluation metrics.

Owner: Vaidehi.
"""

from pathlib import Path

from cdlp.extraction.evaluate import (
    compute_pairwise_kappas,
    evaluate_concept_extraction,
    merge_annotations,
)


def test_compute_pairwise_kappas():
    d1 = {
        ("trees", "binary_tree"): {"label": "hard", "note": ""},
        ("recursion", "binary_tree"): {"label": "soft", "note": ""},
        ("graphs", "avl_tree"): {"label": "none", "note": ""},
    }
    d2 = {
        ("trees", "binary_tree"): {"label": "hard", "note": ""},
        ("recursion", "binary_tree"): {"label": "soft", "note": ""},
        ("graphs", "avl_tree"): {"label": "none", "note": ""},
    }

    annotator_data = {"a": d1, "b": d2}
    kappas = compute_pairwise_kappas(annotator_data)
    assert kappas["a_vs_b"] == 1.0


def test_merge_annotations(tmp_path):
    annotations_dir = Path("data/gold/annotations")
    out_csv = tmp_path / "gold_edges.csv"
    out_json = tmp_path / "gold_concepts.json"

    edge_count, concept_count, kappas = merge_annotations(
        annotations_dir=annotations_dir,
        out_csv=out_csv,
        out_concepts_json=out_json,
    )
    assert edge_count >= 10
    assert concept_count >= 6
    assert out_csv.exists()
    assert out_json.exists()


def test_evaluate_concept_extraction():
    metrics = evaluate_concept_extraction(
        extracted_concepts_path=Path("outputs/concepts.json"),
        gold_concepts_path=Path("data/gold/gold_concepts.json"),
    )
    assert metrics["precision"] > 0.7
    assert metrics["recall"] > 0.7
    assert metrics["f1"] > 0.7
