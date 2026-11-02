"""Tests for quiz item validation and robustness.

Ensures malformed LLM outputs never raise KeyError and invalid items
(missing fields, answer not in options) are safely skipped.
"""

from __future__ import annotations

from cdlp.learning_path.quiz import (
    clean_and_filter_quiz_items,
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


# ---- stricter checks -----------------------------------------------------------


def test_duplicate_options_and_ambiguous_answers_are_skipped():
    dup = {"question": "Q?", "options": ["A", "a ", "B"], "answer": "A"}
    assert not validate_quiz_item(dup)  # "A" would match two options
    letter = {"question": "Q?", "options": ["n - 1", "n"], "correct_answer": "A"}
    assert not validate_quiz_item(letter)  # a letter is not an option's text
    non_str = {"question": "Q?", "options": ["x", 3], "answer": "x"}
    assert not validate_quiz_item(non_str)


# ---- generation from chunks (LLM mocked) ---------------------------------------

from cdlp.learning_path import quiz  # noqa: E402
from cdlp.shared.io import EXAMPLES, read_json, read_jsonl  # noqa: E402
from cdlp.shared.validate import check  # noqa: E402


def good(question, answer="right", chunk="ch_l7_p18"):
    return {
        "question": question,
        "options": ["right", "wrong 1", "wrong 2", "wrong 3"],
        "correct_answer": answer,
        "evidence_chunk_ids": [chunk],
    }


def fake_llm(monkeypatch, replies):
    """replies: concept_id -> reply dict (or an exception to raise)."""
    prompts = []

    def fake_chat_json(prompt, **kwargs):
        prompts.append((prompt, kwargs))
        concept_id = prompt.split("CONCEPT ID:\n", 1)[1].split("\n", 1)[0]
        reply = replies.get(concept_id, {"items": []})
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(quiz, "chat_json", fake_chat_json)
    return prompts


def test_concept_chunks_sources_first_then_mentions():
    concepts = read_json(EXAMPLES / "concepts.json")["concepts"]
    chunks = read_jsonl(EXAMPLES / "chunks.jsonl")
    bst = next(c for c in concepts if c["id"] == "binary_search_tree")
    picked = quiz.concept_chunks(bst, chunks)
    cited = [s["chunk_id"] for s in bst["sources"]]
    assert [c["chunk_id"] for c in picked][: len(cited)] == cited
    assert len(picked) <= quiz.MAX_CHUNKS
    assert quiz.concept_chunks({"id": "x", "name": "Nonexistent Topic"}, chunks) == []


def test_generate_keeps_only_valid_items_and_records_skips(monkeypatch):
    import json

    concepts = read_json(EXAMPLES / "concepts.json")
    chunks = read_jsonl(EXAMPLES / "chunks.jsonl")
    bst_chunk = next(
        s["chunk_id"]
        for c in concepts["concepts"]
        if c["id"] == "binary_search_tree"
        for s in c["sources"]
    )
    prompts = fake_llm(
        monkeypatch,
        {
            "binary_search_tree": {
                "items": [
                    good("Where are smaller keys?", "RIGHT ", chunk=bst_chunk),
                    good("Answer missing?", answer="not an option"),
                    good("Invented chunk id?", chunk="ch_made_up"),
                    {"question": "", "options": ["a", "b"], "correct_answer": "a"},
                    "not even a dict",
                ]
            },
            "recursion": json.JSONDecodeError("bad", "doc", 0),
            "trees": {"something": "else"},
        },
    )
    out = quiz.generate_quiz_items(
        concepts, chunks, course_id="ml101", model="m-test", prompt_version="quiz_v1"
    )

    assert check(out, "quiz_items") == []
    assert out["course_id"] == "ml101"
    bst = [i for i in out["items"] if i["concept_id"] == "binary_search_tree"]
    assert [i["question"] for i in bst] == ["Where are smaller keys?", "Invented chunk id?"]
    assert bst[0]["answer"] == "right" and bst[0]["chunk_id"] == bst_chunk
    assert "chunk_id" not in bst[1]  # an invented id is dropped, never kept
    assert [i["id"] for i in bst] == ["q_binary_search_tree_1", "q_binary_search_tree_2"]
    for item in out["items"]:
        assert item["answer"] in item["options"]

    g = out["generation"]
    assert g["model"] == "m-test" and g["prompt_version"] == "quiz_v1"
    assert g["temperature"] == 0.0
    assert g["skipped"] == {
        "answer_not_in_options": 1,
        "no_items_list": 1,
        "no_question": 1,
        "not_an_object": 1,
        "reply_not_json": 1,
    }
    assert {"recursion", "trees"} <= set(g["concepts_without_items"])
    # every concept with chunks got exactly one call, versioned and at temperature 0
    assert all(kw["prompt_version"] == "quiz_v1" and kw["temperature"] == 0.0 for _, kw in prompts)
    bst_prompt = next(p for p, _ in prompts if "CONCEPT ID:\nbinary_search_tree\n" in p)
    assert f"[{bst_chunk}]" in bst_prompt


def test_cli_writes_quiz_items_for_any_course(monkeypatch, tmp_path):
    fake_llm(monkeypatch, {"trees": {"items": [good("What is a tree?", chunk="none")]}})
    out = tmp_path / "quiz_items.json"
    quiz.main(
        [
            "--concepts",
            str(EXAMPLES / "concepts.json"),
            "--chunks",
            str(EXAMPLES / "chunks.jsonl"),
            "--course-id",
            "any_course_42",
            "--out",
            str(out),
            "--prompt-version",
            "quiz_v1",
        ]
    )
    written = read_json(out)
    assert written["course_id"] == "any_course_42"
    assert [i["concept_id"] for i in written["items"]] == ["trees"]


def test_learning_path_cli_generates_quiz_when_no_quiz_given(monkeypatch, tmp_path):
    from cdlp.learning_path import __main__ as cli
    from cdlp.shared.validate import check_file

    monkeypatch.setattr(quiz, "PROMPT_VERSION", "quiz_v1")
    fake_llm(
        monkeypatch,
        {c: {"items": [good(f"About {c}?")]} for c in ["trees", "binary_tree", "avl_tree"]},
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_path",
            "--graph",
            str(EXAMPLES / "validated_graph.json"),
            "--concepts",
            str(EXAMPLES / "concepts.json"),
            "--chunks",
            str(EXAMPLES / "chunks.jsonl"),
            "--num-students",
            "3",
            "--out-dir",
            str(tmp_path),
        ],
    )
    cli.main()
    for name in ["quiz_items.json", "student_state.json", "learning_path.json"]:
        assert check_file(tmp_path / name) == []
    assert len(read_json(tmp_path / "quiz_items.json")["items"]) == 3
