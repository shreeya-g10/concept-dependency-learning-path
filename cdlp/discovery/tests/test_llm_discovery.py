"""LLM discovery logic with the LLM mocked: tie merging, robustness, transitive flag."""

import pytest

from cdlp.discovery import llm_discovery
from cdlp.discovery.candidates import Candidate

CONCEPTS = [
    {"id": a, "name": a, "description": "", "sources": [{"chunk_id": f"c_{a}"}]}
    for a in ["a", "b", "c"]
]
CHUNKS = [{"chunk_id": f"c_{a}", "doc": "x.pdf", "page": 1, "text": a} for a in ["a", "b", "c"]]


def answer(relationship="DIRECT", strength="HARD", confidence="HIGH", chunks=("c_a",)):
    return {
        "relationship": relationship,
        "strength": strength,
        "confidence": confidence,
        "evidence_chunk_ids": list(chunks),
    }


@pytest.fixture
def llm(monkeypatch):
    """Answers keyed by (source_id, target_id), read from the formatted prompt."""
    answers = {}

    def fake_chat_json(prompt, **kwargs):
        assert kwargs["prompt_version"] == llm_discovery.PROMPT_VERSION
        source = prompt.split("SOURCE CONCEPT:\nID: ")[1].split("\n")[0]
        target = prompt.split("TARGET CONCEPT:\nID: ")[1].split("\n")[0]
        return answers.get((source, target), answer("NONE", "NONE"))

    monkeypatch.setattr(llm_discovery, "chat_json", fake_chat_json)
    return answers


def test_tied_pair_both_direct_keeps_one_bidirectional_edge(llm):
    llm[("a", "b")] = answer(confidence="MEDIUM")
    llm[("b", "a")] = answer(strength="SOFT", confidence="HIGH")

    rels = llm_discovery.discover_candidates(
        [Candidate("a", "b", ["same_chunk"], tied=True)], CONCEPTS, CHUNKS
    )
    (edge,) = llm_discovery.build_contract_relationships(rels, CONCEPTS, CHUNKS)

    assert (edge["source"], edge["target"]) == ("b", "a")  # higher confidence kept
    assert edge["bidirectional"] is True
    assert edge["reverse_strength"] == "hard"
    assert edge["reverse_confidence"] == llm_discovery.CONFIDENCE_SCORES["MEDIUM"]


def test_tied_pair_one_direction_is_a_normal_edge(llm):
    llm[("b", "a")] = answer()

    rels = llm_discovery.discover_candidates(
        [Candidate("a", "b", ["same_chunk"], tied=True)], CONCEPTS, CHUNKS
    )
    (edge,) = llm_discovery.build_contract_relationships(rels, CONCEPTS, CHUNKS)

    assert (edge["source"], edge["target"]) == ("b", "a")
    assert "bidirectional" not in edge


def test_untied_pair_is_asked_once(llm, monkeypatch):
    calls = []
    original = llm_discovery.chat_json
    monkeypatch.setattr(
        llm_discovery, "chat_json", lambda p, **k: calls.append(p) or original(p, **k)
    )

    llm_discovery.discover_candidates([Candidate("a", "b", ["same_chunk"])], CONCEPTS, CHUNKS)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "not a dict",
        {},
        {"relationship": "DIRECT"},  # no strength
        {"relationship": "DIRECT", "strength": "MAYBE"},
        {"relationship": "maybe", "strength": "HARD"},
    ],
)
def test_malformed_llm_output_becomes_none(raw):
    result = llm_discovery._normalise_result(raw, "a", "b", {"c_a"})

    assert result["relationship"] == "NONE"
    assert (result["source"], result["target"]) == ("a", "b")


def test_evidence_ids_not_shown_to_the_llm_are_dropped():
    result = llm_discovery._normalise_result(answer(chunks=["c_a", "made_up"]), "a", "b", {"c_a"})

    assert result["evidence_chunk_ids"] == ["c_a"]


@pytest.mark.parametrize(
    "label, score",
    [("HIGH", 0.9), ("medium", 0.7), (" low ", 0.5), ("??", 0.5), (None, 0.5), (0.42, 0.42)],
)
def test_confidence_labels_map_through_one_constant(label, score):
    assert llm_discovery.confidence_score(label) == score


def chain_answers(llm):
    llm[("a", "b")] = answer()
    llm[("b", "c")] = answer()
    llm[("a", "c")] = answer()  # implied by a -> b -> c
    return [Candidate(s, t, ["same_chunk"]) for s, t in [("a", "b"), ("b", "c"), ("a", "c")]]


def test_transitive_edges_are_kept_by_default(llm):
    rels = llm_discovery.discover_candidates(chain_answers(llm), CONCEPTS, CHUNKS)

    assert {(r["source"], r["target"]) for r in rels if r["relationship"] == "DIRECT"} == {
        ("a", "b"),
        ("b", "c"),
        ("a", "c"),
    }


def test_remove_transitive_flag_leaves_redundant_edges_out_without_rewriting(llm):
    rels = llm_discovery.discover_candidates(
        chain_answers(llm), CONCEPTS, CHUNKS, remove_transitive=True
    )

    assert {(r["source"], r["target"]) for r in rels} == {("a", "b"), ("b", "c")}
    assert all(r["relationship"] == "DIRECT" for r in rels)


def test_contract_evidence_never_writes_page_zero():
    rels = [
        {
            "source": "a",
            "target": "b",
            "relationship": "DIRECT",
            "strength": "hard",
            "confidence": 0.9,
            "evidence_chunk_ids": ["c_x"],
        }
    ]
    chunks = [{"chunk_id": "c_x", "text": "t"}]  # no doc, no page

    (edge,) = llm_discovery.build_contract_relationships(rels, CONCEPTS, chunks)

    assert edge["evidence"] == [{"chunk_id": "c_x", "quote": "t"}]


def test_v1_prompt_is_kept_and_v2_has_no_course_concepts():
    v1 = llm_discovery.load_prompt("discover_v1")
    v2 = llm_discovery.load_prompt("discover_v2").lower()

    assert "binary tree" in v1.lower()  # kept for the record
    for term in ["tree", "recursion", "graph", "avl", "vector", "matri", "regression", "gradient"]:
        assert term not in v2


def _direct(*pairs):
    return [{"source": s, "target": t, "relationship": "DIRECT"} for s, t in pairs]


def test_transitive_edges_any_path_length():
    rels = _direct(("a", "b"), ("b", "c"), ("c", "d"), ("a", "d"), ("a", "c"))

    assert llm_discovery.transitive_edges(rels) == {("a", "d"), ("a", "c")}


def test_transitive_edges_skips_cyclic_graphs():
    assert llm_discovery.transitive_edges(_direct(("a", "b"), ("b", "c"), ("c", "a"))) == set()
