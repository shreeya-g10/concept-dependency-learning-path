"""Unit tests for concept extraction, canonicalization, and deduplication.

Owner: Vaidehi.
Never calls the real LLM in tests; uses pytest monkeypatch.
"""

from cdlp.extraction.extract import (
    are_acronym_match,
    extract_concepts_from_chunks,
    is_valid_concept,
    merge_and_canonicalize,
    semantic_similarity,
    to_slug,
)
from cdlp.shared.validate import check


def test_to_slug():
    assert to_slug("Binary Search Tree") == "binary_search_tree"
    assert to_slug("AVL Trees") == "avl_tree"
    assert to_slug("Recursion") == "recursion"
    assert to_slug("Special@#Characters & More") == "special_characters_more"


def test_is_valid_concept_granularity():
    # Valid
    assert is_valid_concept("Binary Search Tree", "binary_search_tree")
    assert is_valid_concept("Recursion", "recursion")
    assert is_valid_concept("AVL Tree", "avl_tree")

    # Too broad (filtered out)
    assert not is_valid_concept("Computer Science", "computer_science")
    assert not is_valid_concept("Programming", "programming")
    assert not is_valid_concept("Lecture 5 Overview", "lecture")

    # Too fine (filtered out)
    assert not is_valid_concept("Left Subtree", "left_subtree")
    assert not is_valid_concept("Temporary Pointer", "temporary_pointer")
    assert not is_valid_concept("Base Case", "base_case")


def test_acronym_matching():
    assert are_acronym_match("BST", "Binary Search Tree")
    assert are_acronym_match("Binary Search Tree", "BST")
    assert are_acronym_match("AVL", "AVL Tree")
    assert not are_acronym_match("Trees", "Graphs")


def test_semantic_similarity_dedup():
    sim = semantic_similarity("BST", "Binary Search Tree")
    assert sim >= 0.85

    sim_diff = semantic_similarity("Recursion", "Graphs")
    assert sim_diff < 0.6


def test_merge_and_canonicalize():
    raw_data = [
        (
            {
                "id": "binary_search_tree",
                "name": "Binary Search Tree",
                "aliases": [],
                "description": "An ordered binary tree.",
            },
            {"doc": "ds_lec7.pdf", "page": 1, "chunk_id": "ch_1"},
        ),
        (
            {
                "id": "bst",
                "name": "BST",
                "aliases": [],
                "description": "Short form for binary search tree.",
            },
            {"doc": "ds_lec7.pdf", "page": 2, "chunk_id": "ch_2"},
        ),
    ]

    merged = merge_and_canonicalize(raw_data, similarity_threshold=0.85)
    assert len(merged) == 1
    bst = merged[0]
    assert bst["id"] == "binary_search_tree"
    assert "BST" in bst["aliases"]
    assert len(bst["sources"]) == 2


def test_extract_concepts_with_mocked_llm(monkeypatch):
    fake_response = {
        "concepts": [
            {
                "id": "binary_search_tree",
                "name": "Binary Search Tree",
                "aliases": ["BST"],
                "description": "Left < root < right.",
            },
            {
                "id": "left_subtree",
                "name": "Left Subtree",
                "aliases": [],
                "description": "Subtree on the left.",
            },
        ]
    }

    monkeypatch.setattr(
        "cdlp.extraction.extract.chat_json",
        lambda *args, **kwargs: fake_response,
    )
    monkeypatch.setattr(
        "cdlp.extraction.extract.is_llm_available",
        lambda: True,
    )

    chunks = [
        {
            "chunk_id": "ch_mock_1",
            "course_id": "ds101",
            "doc": "ds_lec7.pdf",
            "page": 18,
            "heading": "Binary Search Trees",
            "text": "A BST is an ordered tree.",
        }
    ]

    result = extract_concepts_from_chunks(chunks, course_id="ds101")

    # Contract schema validation
    errors = check(result, "concepts")
    assert errors == []

    # Left subtree should have been filtered out by granularity filter
    concept_ids = [c["id"] for c in result["concepts"]]
    assert "binary_search_tree" in concept_ids
    assert "left_subtree" not in concept_ids
