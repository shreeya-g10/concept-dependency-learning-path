"""Set 2 of the gold labels: the checks, the conversion, the split, and the committed files."""

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "prepare_set2", ROOT / "data/gold/round2/prepare_set2.py"
)
ps = importlib.util.module_from_spec(spec)
sys.modules["prepare_set2"] = ps
spec.loader.exec_module(ps)

RAW_SHA256 = "319e1d9454c36589fbc8f4d7eae9e24289baa7e753a54b0b8801433bbc9e8a3b"


def blank(n=3):
    return [
        {
            "pair": str(i),
            "concept_a": f"A{i}",
            "concept_b": f"B{i}",
            "where_a": "x p.1",
            "where_b": "y p.2",
        }
        for i in range(1, n + 1)
    ]


def answered(*answers):
    rows = blank(len(answers))
    for row, (first, strength) in zip(rows, answers, strict=True):
        row.update(first=first, strength=strength, note="")
    return rows


def key(n=3):
    return [
        {"pair": str(i), "concept_a_id": f"z{i}", "concept_b_id": f"m{i}", "group": "candidate"}
        for i in range(1, n + 1)
    ]


# --- the checks ------------------------------------------------------------------------


def test_clean_answers_have_no_problems():
    rows = answered(("a", "hard"), ("B", "soft"), ("NEITHER", ""))
    assert ps.find_problems(rows, blank()) == []


@pytest.mark.parametrize(
    "answer, words",
    [
        (("maybe", ""), "first is not"),
        (("", ""), "first is not"),
        (("a", ""), "strength is not"),
        (("b", "medium"), "strength is not"),
        (("neither", "hard"), "strength is filled in"),
    ],
)
def test_bad_answers_are_found_by_pair_number(answer, words):
    rows = answered(("a", "hard"), answer, ("neither", ""))
    problems = ps.find_problems(rows, blank())
    assert len(problems) == 1 and problems[0].startswith("pair 2:") and words in problems[0]


def test_a_problem_message_never_shows_the_answer():
    rows = answered(("secretanswer", "secretstrength"), ("a", "hard"), ("a", "hard"))
    assert "secret" not in " ".join(ps.find_problems(rows, blank()))


@pytest.mark.parametrize("column", ["pair", "concept_a", "concept_b", "where_a", "where_b"])
def test_a_row_that_differs_from_the_blank_file_is_found(column):
    rows = answered(("a", "hard"), ("a", "hard"), ("a", "hard"))
    rows[1][column] = "changed"
    assert any(column in p for p in ps.find_problems(rows, blank()))


def test_a_different_order_is_found():
    rows = answered(("a", "hard"), ("a", "hard"), ("a", "hard"))
    rows[0], rows[1] = rows[1], rows[0]
    assert ps.find_problems(rows, blank())


def test_a_missing_or_repeated_pair_is_found():
    rows = answered(("a", "hard"), ("a", "hard"))
    assert any("2 pairs" in p for p in ps.find_problems(rows, blank()))
    rows = answered(("a", "hard"), ("a", "hard"), ("a", "hard"))
    rows[2]["pair"] = "1"
    assert any("more than once" in p for p in ps.find_problems(rows, blank()))


def test_a_problem_writes_nothing(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw.csv"
    columns = ["pair", "concept_a", "concept_b", "where_a", "where_b", "first", "strength", "note"]
    with raw.open("w", newline="") as f:
        writer = csv.DictWriter(f, columns)
        writer.writeheader()
        writer.writerows(answered(("maybe", ""), ("a", "hard"), ("a", "hard")))
    sent = tmp_path / "blank.csv"
    with sent.open("w", newline="") as f:
        writer = csv.DictWriter(f, columns[:5])
        writer.writeheader()
        writer.writerows(blank())
    monkeypatch.setattr(ps, "RAW", raw)
    monkeypatch.setattr(ps, "BLANK", sent)
    monkeypatch.setattr(ps, "GOLD", tmp_path / "gold.csv")
    monkeypatch.setattr(ps, "SPLIT", tmp_path / "split.json")
    assert ps.main() == 1
    assert not (tmp_path / "gold.csv").exists() and not (tmp_path / "split.json").exists()


# --- the conversion --------------------------------------------------------------------


def test_a_means_concept_a_first_and_b_means_concept_b_first():
    gold = ps.convert(answered(("a", "hard"), ("b", "soft"), ("neither", "")), key())
    assert (gold[0]["source"], gold[0]["target"], gold[0]["label"]) == ("z1", "m1", "hard")
    assert (gold[1]["source"], gold[1]["target"], gold[1]["label"]) == ("m2", "z2", "soft")


def test_neither_is_none_in_sorted_order_whatever_order_it_was_shown_in():
    gold = ps.convert(answered(("Neither", ""), ("a", "hard"), ("a", "hard")), key())
    assert (gold[0]["source"], gold[0]["target"], gold[0]["label"]) == ("m1", "z1", "none")


def test_case_is_ignored_and_the_note_is_kept_as_written():
    rows = answered(("A", "hard"), ("a", "hard"), ("a", "hard"))
    rows[0]["note"] = " Her words, kept "
    gold = ps.convert(rows, key())
    assert gold[0]["source"] == "z1" and gold[0]["note"] == " Her words, kept "


# --- findings are reported, never acted on ---------------------------------------------


def edges(*pairs):
    return [
        {"_pair": str(i), "source": s, "target": t, "label": label, "note": ""}
        for i, (s, t, label) in enumerate(pairs, start=1)
    ]


def test_a_cycle_is_found_as_pair_numbers():
    gold = edges(("a", "b", "hard"), ("b", "c", "soft"), ("c", "a", "hard"), ("x", "y", "hard"))
    assert ps.graph_findings(gold)["cycles"] == [[1, 2, 3]]


def test_a_pair_implied_by_a_longer_path_is_found():
    gold = edges(("a", "b", "hard"), ("b", "c", "hard"), ("a", "c", "soft"))
    assert ps.graph_findings(gold)["implied_by_a_longer_path"] == [3]


def test_none_labels_make_no_path():
    gold = edges(("a", "b", "none"), ("b", "c", "hard"), ("a", "c", "hard"))
    findings = ps.graph_findings(gold)
    assert findings == {"cycles": [], "implied_by_a_longer_path": []}


# --- the split -------------------------------------------------------------------------


def labelled(hard, soft, none):
    labels = ["hard"] * hard + ["soft"] * soft + ["none"] * none
    return [{"_pair": str(i), "label": x} for i, x in enumerate(labels, start=1)]


def test_the_split_is_seeded_and_splits_every_pair_once():
    gold = labelled(20, 10, 90)
    first = ps.split_pairs(gold)
    assert first == ps.split_pairs(gold)
    assert first != ps.split_pairs(gold, seed=1)
    assert not set(first["development"]) & set(first["test"])
    assert sorted(first["development"] + first["test"]) == list(range(1, 121))


def test_the_split_is_30_percent_within_each_label():
    split = ps.split_pairs(labelled(20, 10, 90))
    assert len(split["development"]) == 36
    assert split["counts"]["hard"]["development"] == 6
    assert split["counts"]["soft"]["development"] == 3
    assert split["counts"]["none"]["development"] == 27


def test_rounding_still_gives_30_percent_overall():
    assert len(ps.split_pairs(labelled(7, 11, 102))["development"]) == 36


# --- the committed files ---------------------------------------------------------------


def test_her_raw_file_is_unchanged():
    assert hashlib.sha256(ps.RAW.read_bytes()).hexdigest() == RAW_SHA256


def test_the_raw_file_has_no_problems():
    assert ps.find_problems(ps.read_rows(ps.RAW), ps.read_rows(ps.BLANK)) == []


def test_the_committed_gold_file_is_exactly_what_the_conversion_gives(tmp_path):
    gold = ps.convert(ps.read_rows(ps.RAW), ps.read_rows(ps.KEY))
    ps.write_gold(gold, tmp_path / "gold.csv")
    assert (tmp_path / "gold.csv").read_bytes() == ps.GOLD.read_bytes()


def test_the_committed_gold_file_has_the_gold_columns_and_values():
    rows = ps.read_rows(ps.GOLD)
    assert len(rows) == 120
    assert list(rows[0]) == ["source", "target", "label", "note"]
    assert {r["label"] for r in rows} <= {"hard", "soft", "none"}


def test_the_committed_split_is_what_the_script_gives_and_is_disjoint():
    saved = json.loads(ps.SPLIT.read_text())
    fresh = ps.split_pairs(ps.convert(ps.read_rows(ps.RAW), ps.read_rows(ps.KEY)))
    assert saved["development"] == fresh["development"] and saved["test"] == fresh["test"]
    assert not set(saved["development"]) & set(saved["test"])
    assert len(saved["development"]) == 36 and len(saved["test"]) == 84
    assert saved["labels_sha256"] == RAW_SHA256


def test_the_split_file_holds_no_pair_level_labels():
    saved = json.loads(ps.SPLIT.read_text())
    assert all(isinstance(p, int) for p in saved["development"] + saved["test"])


def test_set_2_shares_no_pairs_with_set_1():
    def pairs(path):
        return {
            frozenset((r["concept_a_id"], r["concept_b_id"])) for r in ps.read_rows(ps.HERE / path)
        }

    set1 = pairs("set1_ai_assisted_not_used/ds101_pairs_key.csv")
    set2 = pairs("private_keys/ds101_set2_key.csv")
    assert len(set1) == 150 and len(set2) == 120 and not set1 & set2


def test_the_committed_set_1_files_hold_no_labels():
    rows = ps.read_rows(ps.HERE / "set1_ai_assisted_not_used/ds101_pairs_to_label.csv")
    assert all(not r[k].strip() for r in rows for k in ("first", "strength", "note"))
    key_columns = ps.read_rows(ps.HERE / "set1_ai_assisted_not_used/ds101_pairs_key.csv")[0]
    assert set(key_columns) == {"pair", "concept_a_id", "concept_b_id", "group"}


def test_set_2_is_not_merged_into_the_gold_yet():
    """merge_gold.py's agreement checks need a second labeller."""
    assert "round2" not in (ROOT / "data/gold/merge_gold.py").read_text()
    assert "annotator_a_set2" not in (ROOT / "data/gold/merge_gold.py").read_text()
    with (ROOT / "data/gold/ds101/gold_edges.csv").open() as f:
        merged = {frozenset((r["source"], r["target"])) for r in csv.DictReader(f)}
    set2 = {frozenset((r["source"], r["target"])) for r in ps.read_rows(ps.GOLD)}
    assert not merged & set2
