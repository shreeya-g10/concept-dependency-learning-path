"""Contract test: the CLI runs on the shared examples and its output passes the schema.
Keep this test passing; add your own unit tests next to it."""

import subprocess
import sys

from cdlp.shared.validate import check_file

EX = "cdlp/shared/examples"


def test_cli_output_matches_contract(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cdlp.extraction",
            *["--input", "data/raw", "--out-dir", str(tmp_path)],
        ],
        check=True,
    )
    for name in ["chunks.jsonl", "concepts.json"]:
        assert check_file(tmp_path / name) == []
