"""Contract test: the CLI runs for every dataset and its outputs keep our formats.
Keep this test passing; add your own unit tests next to it."""

import csv
import subprocess
import sys

import pytest

from cdlp.benchmarks.__main__ import DATASETS, GOLD_COLUMNS
from cdlp.shared.validate import check_file


@pytest.mark.parametrize("dataset", DATASETS)
def test_cli_output_matches_contract(tmp_path, dataset):
    raw = tmp_path / "raw"
    raw.mkdir()
    out = tmp_path / "out"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cdlp.benchmarks",
            *["--dataset", dataset, "--raw", str(raw), "--out-dir", str(out)],
        ],
        check=True,
    )
    assert check_file(out / "concepts.json") == []
    with (out / "gold_edges.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == GOLD_COLUMNS
    assert {r["label"] for r in rows} <= {"hard", "soft", "none"}
