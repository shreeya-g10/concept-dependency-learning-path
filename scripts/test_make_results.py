"""scripts/make_results.py: tables from results files, [RESULT] for missing ones."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_results", ROOT / "scripts/make_results.py")
mr = importlib.util.module_from_spec(spec)
sys.modules["make_results"] = mr  # dataclasses look their module up
spec.loader.exec_module(mr)


def put(root: Path, rel: str, data: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_empty_root_gives_placeholders_and_no_figures(tmp_path):
    m = mr.build(tmp_path, tmp_path / "out")
    md = (tmp_path / "out/tables.md").read_text()
    assert "| Graph-guided adaptive | [RESULT] | [RESULT] |" in md
    assert m["figures"] == {}
    assert mr.RQ24 in m["missing"] and mr.AGREEMENT in m["missing"]
    assert (tmp_path / "out/tables.tex").read_text().count(r"\begin{table}") == len(m["tables"])


def test_present_results_fill_tables_and_figures(tmp_path):
    put(
        tmp_path,
        "cdlp/validation/configs/rq1/settings.json",
        {"settings": [{"name": "full_agent"}]},
    )
    put(
        tmp_path,
        "cdlp/validation/configs/rq1/ds101.json",
        {"dataset": "ds101", "courses": [{"course_id": "ds101"}]},
    )
    row = {
        "setting": "full_agent",
        "status": "ok",
        "precision": 0.9,
        "recall": 0.5,
        "f1": 0.643,
        "human_review_rate": 0.1,
        "llm_calls_per_edge": 4.0,
    }
    put(tmp_path, "cdlp/validation/results/rq1_ds101.json", {"scoring": "direct", "rows": [row]})
    diag = {k: {"avg_questions": 3.0, "accuracy": 0.8} for k in ["adaptive", "ask_all", "random"]}
    put(
        tmp_path,
        mr.RQ24,
        {
            "num_students": 5,
            "target_concept": "t",
            "mastery_threshold": 0.8,
            "rq2_diagnosis": diag,
            "rq4_learning_path": {"total_order_mistakes": 0},
        },
    )
    put(
        tmp_path,
        "cdlp/root_cause/results/dev.json",
        {"config": {"dataset": "tests/dev_set.json"}, "results": [{"method": "llm"}]},
    )

    m = mr.build(tmp_path, tmp_path / "out")
    md = (tmp_path / "out/tables.md").read_text()
    assert "| full_agent | 0.90 | 0.50 | 0.64 | 0.10 | 4.0 |" in md
    assert "| Order violations (total) | 0 |" in md
    assert "| Generic path length (avg.) | [RESULT] |" in md  # absent key stays a placeholder
    assert "dev set, never reported as test" in md  # dev runs are never tabled as RQ3
    assert sorted(m["figures"]) == [
        "figures/rq1_ds101_precision_recall.png",
        "figures/rq2_accuracy_vs_questions.png",
    ]
    assert (tmp_path / "out/figures/rq2_accuracy_vs_questions.png").stat().st_size > 0
    tex = (tmp_path / "out/tables.tex").read_text()
    assert r"full\_agent & 0.90" in tex
    assert "cdlp/root_cause/results/dev.json" in m["results_not_used"]


def test_rerun_is_byte_identical(tmp_path):
    put(tmp_path, mr.RQ24, {"rq2_diagnosis": {}, "rq4_learning_path": {}})
    mr.build(tmp_path, tmp_path / "a")
    mr.build(tmp_path, tmp_path / "b")
    for name in ["tables.md", "tables.tex", "manifest.json"]:
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_tex_escape():
    assert mr.tex_escape("a_b & 50% {x} κ ± \\") == (
        r"a\_b \& 50\% \{x\} $\kappa$ $\pm$ \textbackslash{}"
    )
