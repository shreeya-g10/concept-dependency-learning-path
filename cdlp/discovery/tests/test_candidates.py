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


def test_generate_candidates_uses_course_order():
    concepts = [
        {
            "id": "first",
            "name": "First",
            "aliases": [],
            "description": "First concept",
            "sources": [{"chunk_id": "c1"}],
        },
        {
            "id": "second",
            "name": "Second",
            "aliases": [],
            "description": "Second concept",
            "sources": [{"chunk_id": "c2"}],
        },
    ]

    chunks = [
        {"chunk_id": "c1", "text": "First concept"},
        {"chunk_id": "c2", "text": "Second concept"},
    ]

    candidates = generate_candidates(
        concepts,
        chunks,
        embedding_threshold=1.0,
    )

    pairs = {
        (candidate.source, candidate.target)
        for candidate in candidates
    }

    assert ("first", "second") in pairs