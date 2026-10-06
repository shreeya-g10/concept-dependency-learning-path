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
            "cdlp.validation",
            *[
                "--relationships",
                f"{EX}/relationships.json",
                "--concepts",
                f"{EX}/concepts.json",
                "--chunks",
                f"{EX}/chunks.jsonl",
                "--out",
                str(tmp_path / "validated_graph.json"),
            ],
        ],
        check=True,
    )
    for name in ["validated_graph.json"]:
        assert check_file(tmp_path / name) == []
