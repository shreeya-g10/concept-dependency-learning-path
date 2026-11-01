import pytest

from cdlp.discovery import candidates
from cdlp.discovery.candidates import (
    _name_in_definition,
    _same_chunk_pairs,
    generate_candidates,
)


def test_name_in_definition():
    concepts = [
        {
            "id": "tree",
            "name": "Tree",
            "aliases": [],
            "description": "A hierarchical structure.",
            "sources": [{"chunk_id": "c1"}],
        },
        {
            "id": "binary_tree",
            "name": "Binary Tree",
            "aliases": [],
            "description": "A binary tree is a type of tree.",
            "sources": [{"chunk_id": "c2"}],
        },
    ]

    pairs = _name_in_definition(concepts)

    assert ("tree", "binary_tree") in pairs


def test_same_chunk_pairs():
    concepts = [
        {
            "id": "a",
            "name": "A",
            "aliases": [],
            "description": "Concept A",
            "sources": [{"chunk_id": "c1"}],
        },
        {
            "id": "b",
            "name": "B",
            "aliases": [],
            "description": "Concept B",
            "sources": [{"chunk_id": "c1"}],
        },
        {
            "id": "c",
            "name": "C",
            "aliases": [],
            "description": "Concept C",
            "sources": [{"chunk_id": "c2"}],
        },
    ]

    pairs = _same_chunk_pairs(concepts)

    assert ("a", "b") in pairs
    assert ("a", "c") not in pairs


def _concept(cid, description="", chunk="c1"):
    return {
        "id": cid,
        "name": cid.title(),
        "aliases": [],
        "description": description,
        "sources": [{"chunk_id": chunk}],
    }


@pytest.fixture
def no_embeddings(monkeypatch):
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())


def test_course_order_alone_is_never_a_candidate(no_embeddings):
    concepts = [_concept("first", "First concept", "c1"), _concept("second", "Second one", "c2")]
    chunks = [{"chunk_id": "c1", "text": ""}, {"chunk_id": "c2", "text": ""}]

    assert generate_candidates(concepts, chunks) == []


def test_course_order_orients_a_content_signal(no_embeddings):
    # the later concept's definition names the earlier one; course order picks the direction
    concepts = [_concept("bake", "Uses an oven.", "c2"), _concept("oven", "A hot box.", "c1")]
    chunks = [{"chunk_id": "c1", "text": ""}, {"chunk_id": "c2", "text": ""}]

    (candidate,) = generate_candidates(concepts, chunks)

    assert (candidate.source, candidate.target) == ("oven", "bake")
    assert candidate.reasons == ["course_order", "name_in_definition"]
    assert not candidate.tied


def test_position_tie_gives_one_tied_candidate(no_embeddings):
    # same chunk AND name_in_definition in opposite directions: used to create two edges
    concepts = [
        _concept("graph", "Nodes and edges."),
        _concept("adjacency_list", "Stores a graph."),
    ]
    chunks = [{"chunk_id": "c1", "text": ""}]

    (candidate,) = generate_candidates(concepts, chunks)

    assert candidate.tied
    assert candidate.reasons == ["name_in_definition", "same_chunk"]


def test_candidate_stats_counts_both_directions_for_ties():
    cands = [
        candidates.Candidate("a", "b", ["same_chunk"], tied=True),
        candidates.Candidate("a", "c", ["same_chunk"]),
    ]
    stats = candidates.candidate_stats(cands, 4)

    assert stats == {
        "concepts": 4,
        "unordered_pairs": 6,
        "candidates": 2,
        "tied": 1,
        "llm_calls": 3,
    }
