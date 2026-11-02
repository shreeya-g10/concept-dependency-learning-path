"""Review-queue experiment on hand-made graphs (no LLM, no real run)."""

import json

import pytest

from cdlp.validation.review_experiment import (
    main,
    next_edge,
    run_experiment,
    run_strategy,
    summarise,
    teacher_answer,
)


def edge(eid, source, target, decision="HUMAN_REVIEW", confidence=0.5):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "decision": decision,
        "confidence": confidence,
        "checks": {"evidence": "weak", "semantic": "weak", "necessity": "weak", "graph": "ok"},
        "evidence": [],
        "reason": "validator unsure",
    }


def graph(*edges):
    nodes = sorted({n for e in edges for n in (e["source"], e["target"])})
    return {
        "schema_version": "1.5",
        "course_id": "ds101",
        "nodes": [{"id": n, "name": n} for n in nodes],
        "edges": list(edges),
    }


# ACCEPT a -> b -> c. h1 closes a cycle (blocking). Impact for target e: h3 and h4 change
# the path to e, h2 and h5 do not.
G = graph(
    edge("v1", "a", "b", "ACCEPT", 0.9),
    edge("v2", "b", "c", "ACCEPT", 0.9),
    edge("h1", "c", "a", confidence=0.9),
    edge("h2", "a", "d", confidence=0.3),
    edge("h3", "d", "e", confidence=0.2),
    edge("h4", "b", "e", confidence=0.6),
    edge("h5", "x", "y", confidence=0.1),
)
GOLD = {
    ("a", "b"): "hard",
    ("b", "c"): "hard",
    ("c", "a"): "hard",  # positive, but accepting it would close a cycle
    ("a", "d"): "soft",
    ("d", "e"): "none",
    ("b", "e"): "hard",
}  # x -> y is unlabelled
STUDENTS = {"students": [{"student_id": "s1", "mastery": {}}]}


def answered(curve):
    return [r["answered"]["edge_id"] if r["answered"] else None for r in curve[1:]]


def f1(curve):
    return [round(r["f1"], 3) for r in curve]


def test_teacher_answers_from_gold():
    assert teacher_answer(edge("x", "a", "d"), GOLD) == "ACCEPT"  # soft counts as positive
    assert teacher_answer(edge("x", "d", "e"), GOLD) == "REJECT"
    assert teacher_answer(edge("x", "x", "y"), GOLD) == "REJECT"
    assert teacher_answer(edge("x", "x", "y"), GOLD, unlabelled_answer="ACCEPT") == "ACCEPT"


def test_impact_order_blocking_first_then_highest_impact():
    curve = run_strategy(G, GOLD, "impact", 7, students=STUDENTS, targets=["e"])
    assert answered(curve) == ["h1", "h3", "h4", "h2", "h5", None, None]
    first = curve[1]["answered"]
    assert first["blocking"] and first["answer"] == "ACCEPT"
    assert first["status"] == "refused_cycle"  # apply_review refuses it, as on page 3
    # baseline 2 TP of 5 positives; only accepted gold positives (h4, h2) move F1
    assert f1(curve) == [0.571, 0.571, 0.571, 0.75, 0.889, 0.889, 0.889, 0.889]


def test_lowest_confidence_order_blocking_first():
    curve = run_strategy(G, GOLD, "lowest_confidence", 5)
    assert answered(curve) == ["h1", "h5", "h3", "h2", "h4"]
    assert f1(curve) == [0.571, 0.571, 0.571, 0.571, 0.75, 0.889]


@pytest.mark.parametrize("seed", range(5))
def test_random_order_blocking_first_and_reproducible(seed):
    curve = run_strategy(G, GOLD, "random", 5, seed=seed)
    assert answered(curve)[0] == "h1"
    assert sorted(answered(curve)) == ["h1", "h2", "h3", "h4", "h5"]
    assert curve == run_strategy(G, GOLD, "random", 5, seed=seed)


def test_random_seeds_give_different_orders():
    orders = {tuple(answered(run_strategy(G, GOLD, "random", 5, seed=s))) for s in range(10)}
    assert len(orders) > 1


@pytest.mark.parametrize("strategy", ["impact", "random", "lowest_confidence"])
def test_f1_never_falls_and_k0_is_the_validator_graph(strategy):
    curve = run_strategy(G, GOLD, strategy, 10, students=STUDENTS, targets=["e"], seed=1)
    assert [r["k"] for r in curve] == list(range(11))
    assert curve[0]["answered"] is None and round(curve[0]["f1"], 3) == 0.571
    assert all(a["f1"] <= b["f1"] for a, b in zip(curve, curve[1:], strict=False))


def test_an_edge_that_becomes_blocking_jumps_the_queue():
    g = graph(
        edge("v1", "a", "b", "ACCEPT"),
        edge("h1", "b", "c", confidence=0.5),
        edge("h2", "c", "a", confidence=0.99),  # blocking only once h1 is accepted
        edge("h3", "x", "y", confidence=0.1),
        edge("h4", "p", "q", confidence=0.95),
    )
    gold = {("a", "b"): "hard", ("b", "c"): "hard", ("c", "a"): "hard", ("p", "q"): "hard"}
    curve = run_strategy(g, gold, "lowest_confidence", 4)
    assert answered(curve) == ["h3", "h1", "h2", "h4"]
    assert curve[3]["answered"]["blocking"]


def test_impact_needs_students():
    with pytest.raises(ValueError, match="sim_students"):
        next_edge(G, set(), "impact")
    with pytest.raises(ValueError, match="strategy"):
        next_edge(G, set(), "alphabetical")


def test_summarise_mean_and_std():
    a = [{"precision": 1, "recall": 0.0, "f1": 0.0}, {"precision": 1, "recall": 1.0, "f1": 1.0}]
    b = [{"precision": 1, "recall": 0.0, "f1": 0.0}, {"precision": 1, "recall": 0.0, "f1": 0.0}]
    rows = summarise([a, b])
    assert rows[1]["f1"] == 0.5 and rows[1]["f1_std"] == 0.5 and rows[0]["f1_std"] == 0.0


def write_inputs(tmp_path):
    (tmp_path / "validated_graph.json").write_text(json.dumps(G))
    (tmp_path / "students.json").write_text(json.dumps(STUDENTS))
    rows = ["source,target,label,agreement,note"]
    rows += [f"{s},{t},{label},2/2," for (s, t), label in GOLD.items()]
    (tmp_path / "gold.csv").write_text("\n".join(rows) + "\n")
    return {
        "graph": "validated_graph.json",
        "gold": "gold.csv",
        "students": "students.json",
        "targets": ["e"],
        "k_max": 10,
        "strategies": ["impact", "random", "lowest_confidence"],
        "random_seeds": 4,
        "seed": 0,
    }


def test_run_experiment_records_config_and_every_strategy(tmp_path):
    config = write_inputs(tmp_path)
    result = run_experiment(config, base=tmp_path)
    assert result["config"] == config and result["course_id"] == "ds101"
    assert result["human_review_edges"] == 5 and result["blocking_edges"] == ["h1"]
    assert result["gold_positive_human_review_edges"] == 3
    assert set(result["strategies"]) == {"impact", "random", "lowest_confidence"}
    assert result["strategies"]["random"]["seeds"] == [0, 1, 2, 3]
    assert len(result["strategies"]["random"]["runs"]) == 4
    for data in result["strategies"].values():
        assert [r["k"] for r in data["curve"]] == list(range(11))
    assert "git_commit" in result and "date" in result


def test_exclude_pairs_drop_tuning_pairs_from_gold_and_predictions(tmp_path):
    config = write_inputs(tmp_path)
    (tmp_path / "dev.csv").write_text("source,target\na,b\n")
    config["exclude_pairs"] = "dev.csv"
    k0 = run_experiment(config, base=tmp_path)["strategies"]["impact"]["curve"][0]
    assert k0["true_positive"] == 1  # only b -> c is left of the validator's TPs


def test_cli_writes_the_results_file(tmp_path, monkeypatch, capsys):
    config = write_inputs(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.chdir(tmp_path)
    main(["--config", "config.json", "--out", "out/result.json"])
    result = json.loads((tmp_path / "out" / "result.json").read_text())
    assert result["experiment"] == "review_queue"
    assert "impact 0.571" in capsys.readouterr().out
