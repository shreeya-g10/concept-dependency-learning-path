"""The ladder comparison: fair scoring, labelled as simulated, and it reproduces RQ2. No LLM."""

import json
import random
from pathlib import Path

import pytest

from cdlp.learning_path import evaluate
from cdlp.learning_path.sim_students import generate_simulated_students
from cdlp.shared.io import EXAMPLES, read_json

GRAPH = read_json(EXAMPLES / "validated_graph.json")
QUIZ = read_json(EXAMPLES / "quiz_items.json")["items"]
CFG = json.loads(evaluate.LADDER_CONFIG.read_text())
SMALL = {**CFG, "num_students": 30, "bootstrap_resamples": 50, "answer_seeds": [42]}
RESULTS = Path(evaluate.__file__).parent / "results"


@pytest.fixture(scope="module")
def run():
    students = generate_simulated_students(GRAPH, num_students=30, seed=42)["students"]
    return evaluate.evaluate_ladders(GRAPH, QUIZ, students, SMALL)


def test_every_strategy_has_every_score(run):
    assert set(run["strategies"]) == {
        "adaptive",
        "adaptive_levelled",
        "ladder_linear",
        "ladder_middle",
    }
    for row in run["strategies"].values():
        for key in ("questions", "accuracy", "wrongly_known", "gap_coverage", "path_length"):
            assert key in row


def test_adaptive_is_the_same_run_as_rq2():
    students = generate_simulated_students(GRAPH, num_students=500, seed=42)["students"]
    ladder_row = evaluate.evaluate_ladders(
        GRAPH, QUIZ, students, {**CFG, "bootstrap_resamples": 10}
    )["strategies"]["adaptive"]
    saved = json.loads((RESULTS / "rq2_rq4_results.json").read_text())
    assert ladder_row["questions"] == pytest.approx(
        saved["rq2_diagnosis"]["adaptive"]["avg_questions"]
    )
    assert ladder_row["accuracy"] == pytest.approx(saved["rq2_diagnosis"]["adaptive"]["accuracy"])
    assert ladder_row["gap_coverage"] == pytest.approx(
        saved["rq4_learning_path"]["avg_gap_coverage"]
    )


def test_the_answer_chance_depends_on_the_level_and_on_knowing():
    model = CFG["answer_model"]
    rng = random.Random(1)

    def rate(true_mastery, level):
        hits = sum(
            evaluate.simulate_level_answer(rng, true_mastery, level, model) for _ in range(4000)
        )
        return hits / 4000

    assert rate(0.9, "easy") > rate(0.9, "hard") > rate(0.1, "easy") > rate(0.1, "hard")


def test_self_report_can_be_wrong_both_ways():
    model = CFG["self_report"]
    rng = random.Random(1)
    known = [evaluate.simulate_self_report(rng, 0.9, model) for _ in range(500)]
    unknown = [evaluate.simulate_self_report(rng, 0.1, model) for _ in range(500)]
    assert "no" in known or "not_sure" in known
    assert "yes" in unknown
    assert known.count("yes") > unknown.count("yes")


def test_results_say_they_are_simulated_with_placeholders():
    out = evaluate.ladder_comparison(GRAPH, QUIZ, {**SMALL, "sensitivity": {}})
    assert out["placeholder_items"] and out["simulated_students"] and out["no_llm"]
    assert any("not real difficulty" in a for a in out["assumptions"])
    assert out["config"]["answer_model"] == CFG["answer_model"]
    assert set(out["conditions"]) == {"graph_consistent", "graph_independent"}


def test_without_hard_items_nothing_is_known_by_a_stand_in():
    students = generate_simulated_students(GRAPH, num_students=30, seed=42)["students"]
    cfg = {**SMALL, "drop_levels": ["hard"]}
    strategies = evaluate.evaluate_ladders(GRAPH, QUIZ, students, cfg)["strategies"]
    for name in evaluate.LADDER_STRATEGIES:
        assert strategies[name]["stand_ins_for_hard"] == 0
        assert strategies[name]["no_hard_question"] > 0
    assert strategies["ladder_linear"]["wrongly_known"] == 0


def test_placeholder_items_are_marked_and_can_drop_a_level():
    items = evaluate.placeholder_ladder_items(GRAPH, "avl_tree", ["hard"])
    assert all("placeholder" in i["id"] and "placeholder" in i["question"] for i in items)
    assert {i["difficulty"] for i in items} == {"easy", "medium"}


def test_ladder_main_writes_its_own_file_and_leaves_rq2_alone(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({**SMALL, "sensitivity": {}}))
    monkeypatch.setattr(evaluate, "LADDER_CONFIG", cfg)
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path)
    (tmp_path / "rq2_rq4_results.json").write_text("keep me")
    evaluate.ladder_main()
    assert (tmp_path / "rq2_rq4_results.json").read_text() == "keep me"
    assert json.loads((tmp_path / "ladder_comparison.json").read_text())["placeholder_items"]


def test_the_committed_results_match_their_config():
    path = RESULTS / "ladder_comparison.json"
    saved = json.loads(path.read_text())
    assert saved["config"] == CFG
