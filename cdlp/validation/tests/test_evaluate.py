"""RQ1 harness on the example data with mocked setting outputs. No LLM call anywhere."""

import json
import shutil
from pathlib import Path

import pytest

from cdlp.validation import evaluate as ev

EXAMPLES = Path(__file__).resolve().parents[2] / "shared" / "examples"
CONFIGS = Path(__file__).resolve().parents[1] / "configs" / "rq1"

# Same labels as data/gold/gold_edges.csv for the example concepts (6 positives).
GOLD = """source,target,label,agreement,note
binary_search_tree,avl_tree,hard,,
binary_tree,avl_tree,none,,
binary_tree,binary_search_tree,hard,,
graphs,avl_tree,none,,
recursion,avl_tree,none,,
recursion,binary_search_tree,soft,,
recursion,binary_tree,soft,,
trees,avl_tree,none,,
trees,binary_tree,hard,,
trees,graphs,soft,,
"""


def _validated_variant(decisions: dict[str, str]) -> dict:
    data = json.loads((EXAMPLES / "validated_graph.json").read_text())
    for edge in data["edges"]:
        edge["decision"] = decisions.get(edge["id"], edge["decision"])
    return data


def _make_run(run_dir: Path, *, skip=(), calls=None) -> None:
    """Mock every setting's output in run_dir, built from cdlp/shared/examples."""
    run_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "relationships.json": json.loads((EXAMPLES / "relationships.json").read_text()),
        "relationships_baseline.json": json.loads(
            (EXAMPLES / "relationships_baseline.json").read_text()
        ),
        "validated_graph.json": _validated_variant({}),
        # single judge accepts everything it was shown except the edge with no evidence
        "validated_single_judge.json": _validated_variant({"r5": "ACCEPT"}),
        "validated_self_consistency.json": _validated_variant({"r5": "REJECT"}),
        # without the necessity test, the weak trees -> graphs edge is accepted
        "validated_minus_necessity.json": _validated_variant({"r5": "ACCEPT"}),
        "validated_minus_evidence.json": _validated_variant({"r6": "HUMAN_REVIEW"}),
        "validated_minus_semantic.json": _validated_variant({}),
        "validated_minus_graph.json": _validated_variant({}),
    }
    for name, data in files.items():
        if name not in skip:
            (run_dir / name).write_text(json.dumps(data))
    for setting, n in (calls or {}).items():
        (run_dir / f"{setting}.stats.json").write_text(json.dumps({"llm_calls": n}))


@pytest.fixture
def project(tmp_path):
    """A base folder laid out like the repo: gold, concepts and one run folder."""
    (tmp_path / "data/gold").mkdir(parents=True)
    (tmp_path / "data/gold/gold_edges.csv").write_text(GOLD)
    (tmp_path / "outputs/ds101").mkdir(parents=True)
    shutil.copy(EXAMPLES / "concepts.json", tmp_path / "outputs/ds101/concepts.json")
    _make_run(
        tmp_path / "outputs/rq1/ds101",
        calls={"discovery_only": 7, "baseline_prompt": 1, "full_agent": 18},
    )
    return tmp_path


def _rows(result):
    return {r["setting"]: r for r in result["rows"]}


def test_every_config_loads_and_covers_the_rq1_settings():
    expected = {
        "discovery_only",
        "baseline_prompt",
        "single_judge",
        "self_consistency",
        "full_agent",
        "minus_evidence",
        "minus_semantic",
        "minus_necessity",
        "minus_graph",
    }
    datasets = set()
    for path in sorted(CONFIGS.glob("*.json")):
        if path.name == "settings.json":
            continue
        config = ev.load_config(path)
        datasets.add(config["dataset"])
        assert {s["name"] for s in config["settings"]} == expected
        assert config["models"]["validator"] != config["models"]["discovery"]
        assert config["scoring"] in {"direct", "closure", "auto"}
        assert "lecturebank" not in json.dumps(config).lower()  # licence not stated
    assert datasets == {"ds101", "ml101", "al_cpl", "university_course"}


def test_benchmark_configs_use_closure_and_score_labelled_pairs_only():
    al_cpl = ev.load_config(CONFIGS / "al_cpl.json")
    assert al_cpl["scoring"] == "closure" and al_cpl["unlabelled_pairs"] == "ignore"
    assert len(al_cpl["courses"]) == 4
    assert ev.load_config(CONFIGS / "university_course.json")["scoring"] == "closure"
    assert ev.load_config(CONFIGS / "ds101.json")["scoring"] == "direct"


def test_direct_scoring_on_examples(project):
    config = ev.load_config(CONFIGS / "ds101.json")
    rows = _rows(ev.evaluate_course(config, config["courses"][0], base=project))

    # discovery: 6 edges, trees <-> graphs proposed both ways -> 7 pairs
    d = rows["discovery_only"]
    assert (d["true_positive"], d["false_positive"], d["false_negative"]) == (5, 2, 1)
    assert d["precision"] == pytest.approx(5 / 7) and d["recall"] == pytest.approx(5 / 6)
    assert d["human_review_rate"] is None
    assert {(p["source"], p["target"], p["gold"]) for p in d["false_positive_pairs"]} == {
        ("graphs", "trees", "unlabelled"),
        ("graphs", "avl_tree", "none"),
    }

    # full agent: ACCEPT r1-r4 only; r5 is HUMAN_REVIEW and not a prediction
    a = rows["full_agent"]
    assert (a["true_positive"], a["false_positive"], a["false_negative"]) == (4, 0, 2)
    assert a["precision"] == 1.0 and a["recall"] == pytest.approx(4 / 6)
    assert a["human_review_rate"] == pytest.approx(1 / 6)
    assert a["decisions"] == {"ACCEPT": 4, "REJECT": 1, "HUMAN_REVIEW": 1}

    b = rows["baseline_prompt"]
    assert (b["true_positive"], b["false_positive"], b["false_negative"]) == (2, 1, 4)

    assert rows["minus_necessity"]["true_positive"] == 5
    assert rows["minus_evidence"]["human_review_rate"] == pytest.approx(2 / 6)


def test_llm_calls_per_edge_adds_discovery_cost(project):
    config = ev.load_config(CONFIGS / "ds101.json")
    rows = _rows(ev.evaluate_course(config, config["courses"][0], base=project))
    assert rows["discovery_only"]["llm_calls_per_edge"] == pytest.approx(7 / 6)
    assert rows["baseline_prompt"]["llm_calls_per_edge"] == pytest.approx(1 / 3)
    assert rows["full_agent"]["llm_calls_total"] == 25
    assert rows["full_agent"]["llm_calls_per_edge"] == pytest.approx(25 / 6)
    # no stats file -> unknown, never 0
    assert rows["single_judge"]["llm_calls_per_edge"] is None


def test_closure_scoring_counts_shortcut_positives():
    pairs = {
        ("trees", "binary_tree"),
        ("binary_tree", "binary_search_tree"),
        ("binary_search_tree", "avl_tree"),
        ("recursion", "binary_tree"),
    }
    labels = {}
    for line in GOLD.splitlines()[1:]:
        s, t, label, *_ = line.split(",")
        labels[(s, t)] = label
    direct = ev.score(pairs, labels, scoring="direct", unlabelled_pairs="ignore")
    closure = ev.score(pairs, labels, scoring="closure", unlabelled_pairs="ignore")
    assert direct["true_positive"] == 4
    # the closure adds recursion -> binary_search_tree (positive) and three none shortcuts
    assert (closure["true_positive"], closure["false_positive"]) == (5, 3)
    assert closure["false_negative"] == 1  # trees -> graphs


def test_auto_scoring_detects_implied_positives():
    labels = {("a", "b"): "hard", ("b", "c"): "hard", ("a", "c"): "hard"}
    assert ev.resolve_scoring("auto", labels) == ("closure", 1)
    labels[("a", "c")] = "none"
    assert ev.resolve_scoring("auto", labels) == ("direct", 0)
    with pytest.raises(ValueError):
        ev.resolve_scoring("transitive", labels)


def test_ignore_mode_skips_unlabelled_pairs():
    labels = {("a", "b"): "hard", ("b", "c"): "none"}
    predicted = {("a", "b"), ("x", "y")}
    assert ev.score(predicted, labels, unlabelled_pairs="ignore")["precision"] == 1.0
    assert ev.score(predicted, labels, unlabelled_pairs="false_positive")["precision"] == 0.5


def test_gold_is_restricted_to_course_concepts(tmp_path):
    path = tmp_path / "gold.csv"
    path.write_text(GOLD + "vectors,matrices,hard,,\n")
    assert ("vectors", "matrices") not in ev.load_gold(path, {"trees", "binary_tree"})
    assert set(ev.load_gold(path, {"trees", "binary_tree"})) == {("trees", "binary_tree")}


def test_excluded_dev_pairs_never_score(project):
    (project / "dev.csv").write_text("source,target\ntrees,binary_tree\n")
    config = {**ev.load_config(CONFIGS / "ds101.json"), "exclude_pairs": "dev.csv"}
    result = ev.evaluate_course(config, config["courses"][0], base=project)
    a = _rows(result)["full_agent"]
    assert (a["true_positive"], a["false_negative"]) == (3, 2)
    assert result["gold_summary"]["excluded_pairs"] == 1


def test_cli_writes_results_the_website_can_chart(project, tmp_path):
    out = tmp_path / "results"
    ev.main(
        ["--config", str(CONFIGS / "ds101.json"), "--out-dir", str(out), "--base", str(project)]
    )
    result = json.loads((out / "rq1_ds101.json").read_text())
    assert result["dataset"] == "ds101" and result["scoring"] == "direct"
    assert [r["setting"] for r in result["rows"]][:2] == ["discovery_only", "baseline_prompt"]
    for row in result["rows"]:
        assert {"setting", "precision", "recall", "f1", "human_review_rate"} <= set(row)
        assert "llm_calls_per_edge" in row
    config = result["config"]
    assert config["models"]["validator"] == "llama3.1:8b"
    assert config["temperature"] == 0.0 and config["seed"] == 42
    assert config["prompt_versions"]["discovery"] == "discover_v2"
    assert config["course"]["course_id"] == "ds101" and "date" in config


def test_missing_setting_is_reported_not_fatal_unless_strict(project, tmp_path):
    run_dir = project / "outputs/rq1/ds101"
    (run_dir / "validated_self_consistency.json").unlink()
    config = ev.load_config(CONFIGS / "ds101.json")
    row = _rows(ev.evaluate_course(config, config["courses"][0], base=project))["self_consistency"]
    assert row["status"] == "missing" and row["precision"] is None
    with pytest.raises(SystemExit):
        ev.run(CONFIGS / "ds101.json", tmp_path / "r", base=project, strict=True)


def test_multi_course_dataset_writes_micro_average(project, tmp_path):
    config = {
        "dataset": "toy",
        "settings_file": "settings.json",
        "scoring": "direct",
        "unlabelled_pairs": "false_positive",
        "courses": [
            {
                "course_id": f"toy_{i}",
                "concepts": "outputs/ds101/concepts.json",
                "gold": "data/gold/gold_edges.csv",
                "run_dir": "outputs/rq1/ds101",
            }
            for i in (1, 2)
        ],
    }
    path = tmp_path / "configs" / "toy.json"
    path.parent.mkdir()
    shutil.copy(CONFIGS / "settings.json", path.parent / "settings.json")
    path.write_text(json.dumps(config))
    written = ev.run(path, tmp_path / "r", base=project)
    assert [p.name for p in written] == ["rq1_toy_1.json", "rq1_toy_2.json", "rq1_toy_micro.json"]
    micro = _rows(json.loads((tmp_path / "r/rq1_toy_micro.json").read_text()))
    assert micro["full_agent"]["true_positive"] == 8
    assert micro["full_agent"]["precision"] == 1.0
    assert micro["full_agent"]["human_review_rate"] == pytest.approx(2 / 12)
    assert micro["single_judge"]["llm_calls_per_edge"] is None
