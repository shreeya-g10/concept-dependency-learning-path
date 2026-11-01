"""Stability-study bookkeeping (no LLM): summary statistics, order check, estimates."""

import pytest

from cdlp.validation import necessity_stability as ns

THRESHOLDS = {"strong": 0.5, "medium": 0.3, "weak": 0.15}


def run(fmt, n, seed, gaps):
    ids = ["r2", "r4", "r6"]
    return {
        "question_format": fmt,
        "n_questions": n,
        "seed": seed,
        "seconds": 10.0,
        "thresholds": THRESHOLDS,
        "gaps": dict(zip(ids, gaps, strict=True)),
        "edges": {i: f"e{i}" for i in ids},
    }


def test_summary_mean_sd_and_order():
    runs = [run("mcq", 5, 42, [0.6, 0.2, 0.0]), run("mcq", 5, 43, [0.4, 0.4, 0.2])]

    (row,) = ns.summarise(runs, ["r2", "r4", "r6"], THRESHOLDS["weak"])

    assert row["edges"]["r2"]["mean"] == 0.5
    assert row["edges"]["r2"]["sd"] == pytest.approx(0.1414, abs=1e-4)
    assert row["edges"]["r2"]["grade_of_mean"] == "strong"
    assert row["order_holds_on_means"] is True  # 0.5 > 0.3 > 0.1, |0.1| < 0.15
    assert row["order_holds_per_seed"] == [True, False]  # seed 43: 0.4 == 0.4


def test_settings_are_kept_apart():
    runs = [run("open", 3, 42, [0.1, 0.1, 0.1]), run("mcq", 3, 42, [0.5, 0.2, 0.0])]

    rows = ns.summarise(runs, ["r2", "r4", "r6"], 0.15)

    assert {(r["question_format"], r["n_questions"]) for r in rows} == {("open", 3), ("mcq", 3)}
    assert all(r["edges"]["r2"]["sd"] is None for r in rows)  # one seed: no SD


def test_missing_gap_breaks_the_order():
    assert ns._order_holds([0.5, None, 0.0], 0.15) is False


def test_estimates_grow_with_n_and_mcq_is_cheaper():
    assert ns.estimate_seconds("open", 5, 3) > ns.estimate_seconds("open", 3, 3)
    assert ns.estimate_seconds("mcq", 3, 3) < ns.estimate_seconds("open", 3, 3)
