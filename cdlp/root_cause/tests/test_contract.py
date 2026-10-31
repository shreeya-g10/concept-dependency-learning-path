"""Contract test: the CLI runs on the shared examples and its output passes the schema.
Keep this test passing; add your own unit tests next to it."""

import subprocess
import sys

import pytest

from cdlp.root_cause import api
from cdlp.shared import llm
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check, check_file

EX = "cdlp/shared/examples"


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests must never call a real LLM: any call through cdlp.shared.llm fails."""

    def fail(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", fail)
    monkeypatch.setattr(llm, "chat_json", fail)


def test_cli_output_matches_contract(tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "cdlp.root_cause",
            *[
                "--graph",
                f"{EX}/validated_graph.json",
                "--quiz",
                f"{EX}/quiz_items.json",
                "--answers",
                f"{EX}/student_answers.json",
                "--out",
                str(tmp_path / "root_cause.json"),
            ],
        ],
        check=True,
    )
    assert check_file(tmp_path / "root_cause.json") == []


def test_trace_returns_a_root_cause_entry():
    graph = read_json(EXAMPLES / "validated_graph.json")
    item = next(i for i in read_json(EXAMPLES / "quiz_items.json")["items"] if i["id"] == "q_bst_1")
    result = api.trace(graph, item, "8", {"binary_tree": 0.9, "binary_search_tree": 0.2})

    wrapped = {
        "schema_version": "1.1",
        "course_id": "ds101",
        "traces": [{"student_id": "student_b", **result}],
    }
    assert check(wrapped, "root_cause") == []
    assert result["item_id"] == "q_bst_1" and result["answer"] == "8"
