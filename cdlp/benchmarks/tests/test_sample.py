"""Stratified, seeded sampler (no network, no LLM)."""

import csv
import json

import pytest

from cdlp.benchmarks import sample


def gold(n_pos, n_neg):
    return [
        {"source": f"p{i}", "target": f"q{i}", "label": "hard", "agreement": "", "note": ""}
        for i in range(n_pos)
    ] + [
        {"source": f"n{i}", "target": f"m{i}", "label": "none", "agreement": "", "note": ""}
        for i in range(n_neg)
    ]


@pytest.mark.parametrize(
    "counts, n, expected",
    [
        ({"positive": 292, "negative": 534}, 200, {"positive": 71, "negative": 129}),
        ({"positive": 1, "negative": 9}, 5, {"positive": 1, "negative": 4}),
        ({"positive": 3, "negative": 2}, 50, {"positive": 3, "negative": 2}),
    ],  # n > population
)
def test_proportional_allocation(counts, n, expected):
    assert sample.allocate(counts, n) == expected


def test_sample_is_stratified_nested_and_seeded():
    rows = gold(35, 65)
    a = sample.sample_course(rows, "c", 20, 10, 42)
    b = sample.sample_course(list(reversed(rows)), "c", 20, 10, 42)  # file order ignored
    c = sample.sample_course(rows, "c", 20, 10, 7)

    assert a["sample"] == {"positive": 7, "negative": 13}
    assert a["subset"] == {"positive": 4, "negative": 6}  # 3.5 / 6.5 -> largest remainder
    assert a["in_subset"] <= {(r["source"], r["target"]) for r in a["rows"]}  # nested
    assert a["rows"] == b["rows"] and a["in_subset"] == b["in_subset"]
    assert a["rows"] != c["rows"]  # another seed, another sample
    assert a["weights"] == {"positive": 5.0, "negative": 5.0}


def test_write_sample_files(tmp_path):
    from cdlp.benchmarks.common import write_gold_edges
    from cdlp.shared.validate import check_file

    rows = gold(10, 30)
    write_gold_edges(tmp_path / "gold_edges.csv", rows)
    ids = sorted({r["source"] for r in rows} | {r["target"] for r in rows} | {"unused"})
    (tmp_path / "concepts.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "course_id": "toy",
                "concepts": [
                    {"id": i, "name": i, "sources": [{"doc": "f", "page": 1}]} for i in ids
                ],
            }
        )
    )

    meta = sample.write_sample(tmp_path, 8, 4, 42)

    assert (meta["n"], meta["subset_n"], meta["sample"]) == (8, 4, {"positive": 2, "negative": 6})
    with (tmp_path / "sample_pairs.csv").open() as f:
        listed = list(csv.DictReader(f))
    assert len(listed) == 8 and sum(int(r["in_subset"]) for r in listed) == 4
    with (tmp_path / "gold_edges_subset.csv").open() as f:
        assert len(list(csv.DictReader(f))) == 4
    assert check_file(tmp_path / "sample_concepts.json") == []
    sampled = json.loads((tmp_path / "sample_concepts.json").read_text())["concepts"]
    assert "unused" not in {c["id"] for c in sampled} and len(sampled) == 16
