"""Contract test: the CLI converts every dataset's fixture and the outputs keep our formats.
Fixtures are tiny hand-made files shaped like the real downloads; no network access.
Keep this test passing; add your own unit tests next to it."""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from cdlp.benchmarks.__main__ import DATASETS, GOLD_COLUMNS
from cdlp.shared.io import read_json
from cdlp.shared.validate import check_file

FIXTURES = Path(__file__).parent / "fixtures"
COURSES = {
    "al_cpl": [f"al_cpl_{d}" for d in ("data_mining", "geometry", "physics", "precalculus")],
    "university_course": ["university_course"],
    "lecturebank": ["lecturebank"],
}


@pytest.mark.parametrize("dataset", DATASETS)
def test_cli_output_matches_contract(tmp_path, dataset):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cdlp.benchmarks",
            *["--dataset", dataset, "--raw", str(FIXTURES / dataset), "--out-dir", str(tmp_path)],
        ],
        check=True,
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(COURSES[dataset])
    for course_id in COURSES[dataset]:
        folder = tmp_path / course_id
        assert check_file(folder / "concepts.json") == []
        assert read_json(folder / "concepts.json")["course_id"] == course_id
        with (folder / "gold_edges.csv").open(newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert reader.fieldnames == GOLD_COLUMNS
        assert rows and {r["label"] for r in rows} <= {"hard", "soft", "none"}
        ids = {c["id"] for c in read_json(folder / "concepts.json")["concepts"]}
        assert {r["source"] for r in rows} | {r["target"] for r in rows} <= ids


def test_missing_download_explains_what_to_do(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cdlp.benchmarks",
            "--dataset",
            "lecturebank",
            "--raw",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "cdlp/benchmarks/README.md" in result.stderr
