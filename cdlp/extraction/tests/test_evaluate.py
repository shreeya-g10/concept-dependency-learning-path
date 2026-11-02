"""Concept extraction evaluation (gold merging and kappa: data/gold/merge_gold.py)."""

from pathlib import Path

from cdlp.extraction.evaluate import evaluate_concept_extraction, run_full_evaluation


def test_evaluate_concept_extraction():
    concepts_path = (
        Path("outputs/concepts.json")
        if Path("outputs/concepts.json").exists()
        else Path("cdlp/shared/examples/concepts.json")
    )
    metrics = evaluate_concept_extraction(
        extracted_concepts_path=concepts_path,
        gold_concepts_path=Path("data/gold/gold_concepts.json"),
    )
    assert metrics["precision"] > 0.7
    assert metrics["recall"] > 0.7
    assert metrics["f1"] > 0.7


def test_run_full_evaluation_writes_only_results(tmp_path):
    report = run_full_evaluation(Path("cdlp/shared/examples/concepts.json"), tmp_path / "results")
    assert set(report) == {"concepts", "gold_concepts", "concept_evaluation"}
    assert sorted(p.name for p in (tmp_path / "results").iterdir()) == ["evaluation_metrics.json"]
