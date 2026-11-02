import json
import sys

from cdlp.discovery import evaluate as evaluate_module
from cdlp.discovery.evaluate import evaluate

GOLD = [
    {"source": "a", "target": "b", "label": "hard"},
    {"source": "b", "target": "c", "label": "soft"},
    {"source": "a", "target": "c", "label": "none"},
]


def edge(source, target, strength="hard"):
    return {"source": source, "target": target, "strength": strength}


def test_perfect_prediction():
    result = evaluate([edge("a", "b"), edge("b", "c", "soft")], GOLD)

    assert (result["precision"], result["recall"], result["f1"]) == (1.0, 1.0, 1.0)
    assert result["strength_accuracy"] == 1.0


def test_unlabelled_predicted_edge_is_a_false_positive():
    # (x, y) is not in gold at all; it must still count against precision
    result = evaluate([edge("a", "b"), edge("x", "y")], GOLD)

    assert result["false_positive"] == 1
    assert result["false_positive_pairs"] == [{"source": "x", "target": "y", "gold": "unlabelled"}]
    assert result["precision"] == 0.5


def test_gold_none_and_reversed_edges_are_false_positives():
    result = evaluate([edge("a", "c"), edge("b", "a")], GOLD)

    assert result["true_positive"] == 0
    assert result["false_positive"] == 2
    assert result["false_negative"] == 2


def test_raw_records_with_relationship_none_are_not_predictions():
    raw = [{"source": "a", "target": "c", "relationship": "NONE", "strength": "none"}]

    assert evaluate(raw, GOLD)["false_positive"] == 0


def test_cli_records_config(tmp_path, monkeypatch):
    rels = tmp_path / "relationships.json"
    rows = [{**edge("a", "b"), "method": "llm_discover_v2"}]
    rels.write_text(json.dumps({"course_id": "x", "relationships": rows}))
    gold = tmp_path / "gold.csv"
    gold.write_text("source,target,label\na,b,hard\n")
    out = tmp_path / "evaluation.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate", "--relationships", str(rels), "--gold", str(gold), "--out", str(out)],
    )

    evaluate_module.main()

    config = json.loads(out.read_text())["config"]
    assert {"model", "prompt_version", "seed", "date", "temperature"} <= config.keys()
    assert config["prompt_version"] == "discover_v2"


def test_prompt_version_comes_from_the_edges_not_the_default():
    assert evaluate_module.prompt_version_of([{"method": "llm_discover_v2"}]) == "discover_v2"
    # never guess: mixed or missing methods are reported as unknown
    assert evaluate_module.prompt_version_of([{"method": "other"}]) == "unknown"
    assert evaluate_module.prompt_version_of([{}]) == "unknown"
    assert evaluate_module.prompt_version_of([]) == "unknown"
    mixed = [{"method": "llm_discover_v2"}, {"method": "llm_discover_v3"}]
    assert evaluate_module.prompt_version_of(mixed) == "unknown"
