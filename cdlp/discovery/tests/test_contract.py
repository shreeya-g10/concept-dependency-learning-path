"""Contract test: the CLI runs on the shared examples and its output passes the schema.
Runs in-process with the LLM and the embedding model mocked, so it never calls an LLM.
Keep this test passing; add your own unit tests next to it."""

import sys

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.discovery import candidates, llm_discovery
from cdlp.shared import llm
from cdlp.shared.io import read_json
from cdlp.shared.validate import check_file

EX = "cdlp/shared/examples"


@pytest.fixture(autouse=True)
def mocked_models(monkeypatch):
    def no_llm(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", no_llm)
    monkeypatch.setattr(llm, "chat_json", no_llm)
    # embedding model: not installed in CI
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())
    # every candidate is a hard prerequisite, citing the source concept's chunk
    monkeypatch.setattr(
        llm_discovery,
        "chat_json",
        lambda prompt, **kwargs: {
            "relationship": "DIRECT",
            "strength": "HARD",
            "confidence": "HIGH",
            "evidence_chunk_ids": [prompt.split("Chunk ID: ")[1].split("\n")[0]],
        },
    )


def run_cli(monkeypatch, out_dir, *extra):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cdlp.discovery",
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(out_dir)],
            *extra,
        ],
    )
    cli.main()


def test_cli_output_matches_contract(tmp_path, monkeypatch):
    run_cli(monkeypatch, tmp_path)

    for name in ["relationships.json", "quiz_items.json"]:
        assert check_file(tmp_path / name) == []
    assert not (tmp_path / "sim_students.json").exists()  # built from validated edges now

    course = read_json(f"{EX}/concepts.json")["course_id"]
    relationships = read_json(tmp_path / "relationships.json")
    assert relationships["course_id"] == course
    assert relationships["relationships"], "examples should yield at least one candidate"
    for edge in relationships["relationships"]:
        assert edge["method"] == f"llm_{llm_discovery.PROMPT_VERSION}"


def test_examples_do_not_send_every_pair(tmp_path, monkeypatch, capsys):
    run_cli(monkeypatch, tmp_path)

    n = len(read_json(f"{EX}/concepts.json")["concepts"])
    edges = read_json(tmp_path / "relationships.json")["relationships"]
    assert len(edges) < n * (n - 1) // 2
    assert "candidates:" in capsys.readouterr().err
