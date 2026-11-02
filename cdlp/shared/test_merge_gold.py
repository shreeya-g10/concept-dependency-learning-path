"""data/gold/merge_gold.py: kappa both ways, shortcut rule, per-course merge, ties."""

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("merge_gold", ROOT / "data/gold/merge_gold.py")
mg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mg)

COURSES = {"x": ["a", "b", "c", "d"], "y": ["p", "q", "r"]}


def write(folder: Path, name: str, rows: list[tuple]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["source,target,label,note"] + [",".join(r) + "," for r in rows]
    (folder / f"annotator_{name}.csv").write_text("\n".join(lines) + "\n")


def test_shortcut_rule_uses_only_the_annotators_own_path():
    labels = {("a", "b"): "hard", ("b", "c"): "soft", ("a", "c"): "hard", ("c", "d"): "none"}
    ruled = mg.apply_shortcut_rule(labels)
    assert ruled[("a", "c")] == "none"  # a -> b -> c exists
    assert ruled[("a", "b")] == "hard" and ruled[("b", "c")] == "soft"
    # a none edge never forms a path
    assert (
        mg.apply_shortcut_rule({("a", "c"): "soft", ("c", "d"): "none", ("a", "d"): "soft"})[
            ("a", "d")
        ]
        == "soft"
    )


def test_kappa_values():
    assert mg.cohen_kappa(["hard", "none"], ["hard", "none"]) == 1.0
    assert mg.cohen_kappa(["hard", "hard"], ["hard", "hard"]) is None  # chance agreement 1
    assert mg.cohen_kappa(["hard", "soft", "none", "none"], ["soft", "hard", "none", "none"]) == (
        pytest.approx(0.2)  # po 0.5, pe 0.375
    )


def test_run_reports_both_kappas_per_course_and_leaves_ties_out(tmp_path):
    ann = tmp_path / "annotations"
    write(
        ann,
        "a",
        [
            ("a", "b", "hard"),
            ("b", "c", "hard"),
            ("a", "c", "soft"),
            ("p", "q", "soft"),
            ("q", "r", "hard"),
        ],
    )
    write(
        ann,
        "c",
        [
            ("a", "b", "hard"),
            ("b", "c", "hard"),
            ("a", "c", "none"),
            ("p", "q", "none"),
            ("q", "r", "hard"),
        ],
    )
    (ann / "annotator_d.csv").write_text("source,target,label,note")  # empty file is fine
    courses = tmp_path / "courses.json"
    courses.write_text(json.dumps({"courses": COURSES}))
    adj = tmp_path / "adjudication.csv"
    adj.write_text("source,target,label,note\np,q,soft,course text uses p in q\n")

    report = mg.run(ann, courses, adj, tmp_path / "out")

    by_scope = {r["scope"]: r for r in report["pairs"]}
    assert by_scope["x"]["n_pairs"] == 3 and by_scope["y"]["n_pairs"] == 2
    assert by_scope["x"]["kappa_raw"] < 1.0
    assert by_scope["x"]["kappa_shortcut_rule"] == 1.0  # a's shortcut a->c becomes none
    assert report["labels_changed_by_rule"]["a"]["x"] == ["a->c: soft->none"]
    assert report["labels_changed_by_rule"]["c"]["x"] == []

    # a->c tie (soft vs none) is unresolved; p->q tie is adjudicated
    assert [(u["source"], u["target"]) for u in report["merge"]["unresolved"]] == [("a", "c")]
    with (tmp_path / "out/y/gold_edges.csv").open() as f:
        y = {(r["source"], r["target"]): r for r in csv.DictReader(f)}
    assert y[("p", "q")]["label"] == "soft" and "adjudicated" in y[("p", "q")]["agreement"]
    with (tmp_path / "out/x/gold_edges.csv").open() as f:
        x = list(csv.DictReader(f))
    assert ("a", "c") not in {(r["source"], r["target"]) for r in x}
    assert list(x[0]) == mg.COLUMNS


def test_pair_outside_every_course_is_an_error(tmp_path):
    ann = tmp_path / "annotations"
    write(ann, "a", [("a", "p", "hard")])
    courses = tmp_path / "courses.json"
    courses.write_text(json.dumps({"courses": COURSES}))
    with pytest.raises(ValueError, match="exactly one"):
        mg.run(ann, courses, None, tmp_path / "out")


def test_committed_agreement_matches_the_annotator_files(tmp_path):
    """data/gold/ agreement and per-course gold match the annotator files (rerun the script)."""
    gold = ROOT / "data/gold"
    report = mg.run(
        gold / "annotations", gold / "courses.json", gold / "adjudication.csv", tmp_path
    )
    committed = json.loads((gold / "agreement.json").read_text())
    assert report == committed
    for course in report["merge"]["gold_rows"]:
        rel = f"{course}/gold_edges.csv"
        assert (tmp_path / rel).read_text() == (gold / rel).read_text(), rel
