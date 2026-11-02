"""Tests for quiz item validation and robustness.

Ensures malformed LLM outputs never raise KeyError and invalid items
(missing fields, answer not in options) are safely skipped.
"""

from __future__ import annotations

from cdlp.learning_path.quiz import (
    clean_and_filter_quiz_items,
    get_quiz_items,
    validate_quiz_item,
)


def test_validate_quiz_item_missing_fields_never_raises_keyerror():
    assert not validate_quiz_item({})
    assert not validate_quiz_item({"question": "What is X?"})
    assert not validate_quiz_item({"question": "What is X?", "options": ["A", "B"]})
    assert not validate_quiz_item({"options": ["A", "B"], "answer": "A"})
    assert not validate_quiz_item(None)
    assert not validate_quiz_item("invalid string")


def test_validate_quiz_item_answer_must_be_in_options():
    # Answer not in options
    bad_item = {
        "question": "What is AVL balance factor?",
        "options": ["0", "1", "2"],
        "answer": "3",  # Not in options
    }
    assert not validate_quiz_item(bad_item)

    # Valid item (exact match)
    good_item = {
        "question": "What is AVL balance factor?",
        "options": ["-1, 0, +1", "At most 2", "Any integer"],
        "answer": "-1, 0, +1",
    }
    assert validate_quiz_item(good_item)

    # Case-insensitive match is accepted
    case_item = {
        "question": "What is BST invariant?",
        "options": ["Left subtree smaller", "Right subtree smaller"],
        "answer": "left subtree smaller",
    }
    assert validate_quiz_item(case_item)


def test_validate_quiz_item_options_length():
    # Only 1 option
    one_opt = {
        "question": "Only one option?",
        "options": ["Only option"],
        "answer": "Only option",
    }
    assert not validate_quiz_item(one_opt)


def test_clean_and_filter_quiz_items_skips_bad_items():
    raw_llm_output = [
        # Bad: missing answer
        {"question": "Q1?", "options": ["A", "B"]},
        # Bad: answer not in options
        {"question": "Q2?", "options": ["A", "B"], "answer": "C"},
        # Bad: missing question
        {"options": ["A", "B"], "answer": "A"},
        # Bad: empty options
        {"question": "Q3?", "options": [], "answer": "A"},
        # Good: standard answer
        {
            "id": "q_test_01",
            "concept_id": "test_concept",
            "question": "Good question?",
            "options": ["Opt 1", "Opt 2"],
            "answer": "Opt 1",
            "chunk_id": "ch_01",
        },
        # Good: using correct_answer from prompt v1
        {
            "concept_id": "test_concept_2",
            "question": "Prompt v1 style question?",
            "options": ["Choice A", "Choice B"],
            "correct_answer": "Choice B",
        },
    ]

    cleaned = clean_and_filter_quiz_items(raw_llm_output)
    assert len(cleaned) == 2
    assert cleaned[0]["id"] == "q_test_01"
    assert cleaned[0]["answer"] == "Opt 1"
    assert cleaned[1]["concept_id"] == "test_concept_2"
    assert cleaned[1]["answer"] == "Choice B"


def test_get_quiz_items_schema_conformance(tmp_path):
    for course in ["ds101", "ml101"]:
        catalog = get_quiz_items(course_id=course)
        assert catalog["course_id"] == course
        assert len(catalog["items"]) >= 5
        for item in catalog["items"]:
            assert item["answer"] in item["options"]
