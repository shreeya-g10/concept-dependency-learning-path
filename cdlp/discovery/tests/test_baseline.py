"""Baseline (one call, full concept list) with the LLM mocked."""

import pytest

from cdlp.discovery import baseline

CONCEPTS = [
    {"id": "a", "name": "A", "description": "first"},
    {"id": "b", "name": "B", "description": ""},
    {"id": "c", "name": "C"},
]


@pytest.fixture
def llm(monkeypatch):
    calls = []

    def answer_with(payload):
        def fake(prompt, **kwargs):
            calls.append((prompt, kwargs))
            return payload

        monkeypatch.setattr(baseline, "chat_json", fake)

    answer_with.calls = calls
    return answer_with


def test_one_call_with_every_concept(llm):
    llm({"relationships": []})

    baseline.discover_baseline(CONCEPTS)

    ((prompt, kwargs),) = llm.calls
    assert all(f"{c['id']}: {c['name']}" in prompt for c in CONCEPTS)
    assert kwargs["prompt_version"] == "baseline_v1"


def test_output_is_contract_format(llm):
    llm(
        {"relationships": [{"source": "a", "target": "b", "strength": "HARD", "confidence": "LOW"}]}
    )

    (edge,) = baseline.discover_baseline(CONCEPTS)

    assert edge == {
        "id": "b1",
        "source": "a",
        "target": "b",
        "type": "PREREQUISITE",
        "strength": "hard",
        "confidence": 0.5,
        "evidence": [],
        "method": "llm_baseline_v1",
    }


def test_junk_is_dropped(llm):
    llm(
        {
            "relationships": [
                {"source": "a", "target": "zzz", "strength": "HARD"},  # unknown id
                {"source": "a", "target": "a", "strength": "HARD"},  # self-loop
                {"source": "a", "target": "b", "strength": "MAYBE"},  # bad strength
                "not a dict",
                {"source": "b", "target": "c", "strength": "soft"},
                {"source": "b", "target": "c", "strength": "soft"},  # duplicate
            ]
        }
    )

    edges = baseline.discover_baseline(CONCEPTS)

    assert [(e["source"], e["target"], e["strength"]) for e in edges] == [("b", "c", "soft")]


@pytest.mark.parametrize("payload", [None, [], {}, {"relationships": "x"}])
def test_malformed_payload_gives_no_edges(llm, payload):
    llm(payload)

    assert baseline.discover_baseline(CONCEPTS) == []


def test_both_directions_become_one_bidirectional_edge(llm):
    llm(
        {
            "relationships": [
                {"source": "a", "target": "b", "strength": "HARD", "confidence": "LOW"},
                {"source": "b", "target": "a", "strength": "SOFT", "confidence": "HIGH"},
            ]
        }
    )

    (edge,) = baseline.discover_baseline(CONCEPTS)

    assert (edge["source"], edge["target"]) == ("b", "a")
    assert edge["bidirectional"] is True
    assert (edge["reverse_strength"], edge["reverse_confidence"]) == ("hard", 0.5)


def test_prompt_has_no_course_concepts():
    text = baseline.load_prompt().lower()
    for term in ["tree", "recursion", "graph", "avl", "vector", "matri", "regression", "gradient"]:
        assert term not in text
