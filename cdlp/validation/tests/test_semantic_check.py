"""Semantic check / single LLM judge, with the LLM mocked."""

import json
import re
import sys

import pytest

from cdlp.validation import semantic_check

CONCEPTS = {
    "concepts": [
        {
            "id": "roux",
            "name": "Making a Roux",
            "aliases": ["Roux"],
            "description": "Flour in fat.",
        },
        {"id": "bechamel", "name": "Bechamel Sauce", "aliases": [], "description": ""},
        {"id": "searing", "name": "Searing Meat", "description": "High-heat browning."},
    ]
}
RELATIONSHIPS = {
    "course_id": "cook101",
    "relationships": [
        {"id": "r1", "source": "roux", "target": "bechamel"},
        {"id": "r2", "source": "searing", "target": "bechamel"},
    ],
}


@pytest.fixture
def llm(monkeypatch):
    """Grades keyed by (source name, target name), parsed from the prompt."""
    replies, calls = {}, []

    def fake_chat_json(prompt, **kwargs):
        calls.append(kwargs)
        source, target = re.search(r'learn "(.+?)" BEFORE "(.+?)"', prompt).groups()
        reply = replies.get((source, target), {"semantic": "none", "rationale": "No link."})
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(semantic_check, "chat_json", fake_chat_json)
    fake_chat_json.replies, fake_chat_json.calls = replies, calls
    return fake_chat_json


def test_grades_rationale_and_judge_decisions(llm):
    llm.replies[("Making a Roux", "Bechamel Sauce")] = {
        "semantic": "STRONG",
        "rationale": "A bechamel is thickened with a roux.",
    }

    result = semantic_check.run(RELATIONSHIPS, CONCEPTS, model="judge-model")

    r1, r2 = result["results"]
    assert (r1["semantic"], r1["judge_decision"]) == ("strong", "ACCEPT")
    assert r1["rationale"] == "A bechamel is thickened with a roux."
    assert (r2["semantic"], r2["judge_decision"]) == ("none", "REJECT")
    assert {"model", "prompt_version", "temperature", "seed", "date"} <= result.keys()
    assert all(c["model"] == "judge-model" for c in llm.calls)
    assert all(c["prompt_version"] == "semantic_v2" for c in llm.calls)


@pytest.mark.parametrize(
    "grade, decision",
    [("strong", "ACCEPT"), ("medium", "ACCEPT"), ("weak", "REJECT"), ("none", "REJECT")],
)
def test_judge_rule(grade, decision):
    assert semantic_check.judge_decision(grade) == decision


@pytest.mark.parametrize(
    "reply", [{}, {"semantic": "excellent"}, ["not", "a dict"], ValueError("not JSON")]
)
def test_malformed_reply_is_none_and_rejected(llm, reply):
    llm.replies[("Making a Roux", "Bechamel Sauce")] = reply

    r1 = semantic_check.run(RELATIONSHIPS, CONCEPTS)["results"][0]

    assert (r1["semantic"], r1["judge_decision"]) == ("none", "REJECT")


def test_uses_validator_model_from_env(llm, monkeypatch):
    monkeypatch.setenv("LLM_VALIDATOR_MODEL", "some-validator")

    assert semantic_check.run(RELATIONSHIPS, CONCEPTS)["model"] == "some-validator"


def test_prompt_shows_names_aliases_and_descriptions_but_no_chunks():
    prompt = semantic_check.build_prompt(
        RELATIONSHIPS["relationships"][0], {c["id"]: c for c in CONCEPTS["concepts"]}
    )

    assert '"Making a Roux" (Roux): Flour in fat.' in prompt
    assert '"Bechamel Sauce" (no aliases): (no description)' in prompt
    assert "{" + "source_name}" not in prompt
    assert "chunk" not in prompt.lower()


@pytest.mark.parametrize("version", ["semantic_v1", "semantic_v2"])
def test_prompt_examples_have_no_course_concepts(version):
    text = semantic_check.prompt_file(version).read_text().lower()
    for term in ["tree", "recursion", "graph", "avl", "vector", "matri", "regression", "gradient"]:
        assert term not in text, term


def test_v2_grades_specialisation_as_strong_and_v1_is_kept():
    v2 = semantic_check.prompt_file("semantic_v2").read_text()

    assert "kind of" in v2 and "specialisation" in v2
    assert semantic_check.prompt_file("semantic_v1").exists()


def test_prompt_version_is_selectable(llm):
    result = semantic_check.run(RELATIONSHIPS, CONCEPTS, prompt_version="semantic_v1")

    assert result["prompt_version"] == "semantic_v1"
    assert all(c["prompt_version"] == "semantic_v1" for c in llm.calls)


def test_cli_writes_results(llm, tmp_path, monkeypatch):
    rels, concepts, out = tmp_path / "r.json", tmp_path / "c.json", tmp_path / "semantic.json"
    rels.write_text(json.dumps(RELATIONSHIPS))
    concepts.write_text(json.dumps(CONCEPTS))
    monkeypatch.setattr(
        sys,
        "argv",
        ["semantic_check", "--relationships", str(rels), "--concepts", str(concepts)]
        + ["--out", str(out)],
    )

    semantic_check.main()

    assert len(json.loads(out.read_text())["results"]) == 2
