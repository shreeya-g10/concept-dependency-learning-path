"""Contract test: the CLI runs on the shared examples and its output passes the schema.
Runs in-process with every LLM step replaced by the shared examples, so it never
calls an LLM. Keep this test passing; add your own unit tests next to it."""

import sys

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.shared import llm
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check_file

EX = "cdlp/shared/examples"


@pytest.fixture(autouse=True)
def examples_instead_of_llm(monkeypatch):
    def no_llm(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", no_llm)
    monkeypatch.setattr(llm, "chat_json", no_llm)
    # embedding model (not installed in CI); its output is unused once discovery is mocked
    monkeypatch.setattr(cli, "generate_candidates", lambda concepts, chunks: [])
    monkeypatch.setattr(cli, "discover_candidates", lambda candidates, concepts, chunks: [])
    monkeypatch.setattr(
        cli,
        "build_contract_relationships",
        lambda relationships, concepts, chunks: read_json(EXAMPLES / "relationships.json")[
            "relationships"
        ],
    )
    monkeypatch.setattr(
        cli,
        "generate_quiz_items",
        lambda concepts, chunks: read_json(EXAMPLES / "quiz_items.json")["items"],
    )


def test_cli_output_matches_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cdlp.discovery",
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(tmp_path)],
        ],
    )
    cli.main()

    for name in ["relationships.json", "quiz_items.json", "sim_students.json"]:
        assert check_file(tmp_path / name) == []
    course = read_json(f"{EX}/concepts.json")["course_id"]
    assert read_json(tmp_path / "relationships.json")["course_id"] == course
