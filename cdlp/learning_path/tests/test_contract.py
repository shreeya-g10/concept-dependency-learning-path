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
            "cdlp.learning_path",
            *[
                "--graph",
                f"{EX}/validated_graph.json",
                "--quiz",
                f"{EX}/quiz_items.json",
                "--students",
                f"{EX}/sim_students.json",
                "--target",
                "avl_tree",
                "--out-dir",
                str(tmp_path),
            ],
        ],
        check=True,
    )
    for name in ["student_state.json", "learning_path.json"]:
        assert check_file(tmp_path / name) == []
