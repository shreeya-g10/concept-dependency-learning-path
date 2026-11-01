"""Necessity test with every LLM role mocked (keyed by prompt_version)."""

import json
import re
import sys

import pytest

from cdlp.validation import necessity_test as nt

CONCEPTS = {
    "concepts": [
        {"id": "king_moves", "name": "How the King Moves", "sources": [{"chunk_id": "c1"}]},
        {
            "id": "rook_moves",
            "name": "How the Rook Moves",
            "aliases": ["Rook"],
            "description": "A rook slides along rows and columns.",
            "sources": [{"chunk_id": "c2"}],
        },
        {"id": "castling", "name": "Castling", "sources": [{"chunk_id": "c3"}]},
        {"id": "endgames", "name": "Endgames", "sources": [{"chunk_id": "c4"}]},
    ]
}
CHUNKS = [
    {"chunk_id": f"c{i}", "text": t}
    for i, t in enumerate(
        ["The king moves one square.", "A rook slides.", "Castling moves king and rook.", "End."],
        1,
    )
]
RELATIONSHIPS = {
    "course_id": "chess101",
    "relationships": [{"id": "r1", "source": "rook_moves", "target": "castling"}],
}
QUESTIONS = [
    {"question": f"Q{i}?", "reference_answer": f"ref {i}", "chunk_id": "c3"} for i in (1, 2, 3)
]


@pytest.fixture
def llm(monkeypatch):
    """Role replies; records every call's prompt and kwargs."""
    calls = []
    replies = {
        "necessity_questions_v1": {"questions": QUESTIONS},
        "necessity_learner_without_v1": {"answers": ["no idea", "the king moves", "a rook!"]},
        "necessity_learner_with_v1": {"answers": ["a", "b", "c"]},
    }
    grader = {}  # answer text -> grade

    def fake_chat_json(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        version = kwargs["prompt_version"]
        if version == "necessity_grader_v1":
            students = re.findall(r'Student: "(.*)"', prompt)
            return {
                "grades": [{"grade": grader.get(s, "correct"), "reason": "r"} for s in students]
            }
        reply = replies[version]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(nt, "chat_json", fake_chat_json)
    fake_chat_json.calls, fake_chat_json.replies, fake_chat_json.grader = calls, replies, grader
    return fake_chat_json


def run(**kwargs):
    return nt.run(RELATIONSHIPS, CONCEPTS, CHUNKS, **kwargs)["results"][0]


def test_gap_scores_and_grade(llm):
    llm.grader.update({"no idea": "incorrect", "the king moves": "partial", "a rook!": "incorrect"})

    r = run()

    assert (r["score_without"], r["score_with"]) == (pytest.approx(1 / 6, abs=1e-4), 1.0)
    assert r["necessity_gap"] == pytest.approx(5 / 6, abs=1e-4)
    assert r["necessity"] == "strong"


@pytest.mark.parametrize(
    "gap, grade",
    [
        (-0.5, "none"),
        (0.0, "none"),
        (0.1, "none"),
        (1 / 6, "weak"),
        (1 / 3, "medium"),
        (0.5, "strong"),
        (None, "none"),
    ],
)
def test_gap_thresholds_come_from_config(gap, grade):
    assert nt.gap_grade(gap, nt.load_config()["thresholds"]) == grade


def test_five_calls_per_edge_seeded_at_temperature_zero(llm):
    run()

    versions = [c["prompt_version"] for c in llm.calls]
    assert versions == [
        "necessity_questions_v1",
        "necessity_learner_without_v1",
        "necessity_learner_with_v1",
        "necessity_grader_v1",
        "necessity_grader_v1",
    ]
    assert all(c["temperature"] == 0.0 and c["seed"] == 42 for c in llm.calls)


def test_learners_get_the_right_knowledge(llm):
    r = run()
    without, with_a = (c["prompt"] for c in llm.calls[1:3])

    assert r["known_without"] == ["king_moves"]  # taught before castling, never A or B
    assert 'NEVER learned "How the Rook Moves"' in without
    assert "Endgames" not in without  # taught after B
    assert 'You have also learned "How the Rook Moves": A rook slides' in with_a
    assert "Your lesson" not in without  # learner_sees_lesson is false by default


def test_grader_is_blind_to_the_run(llm):
    run()

    for call in llm.calls[3:]:
        assert "NEVER" not in call["prompt"] and "How the Rook Moves" not in call["prompt"]


def test_leakage_flags_forbidden_terms_and_stems(llm):
    r = run()

    assert r["leakage"]["flagged_answers"] == [2]  # "a rook!" uses the alias
    assert r["leakage"]["rate"] == pytest.approx(1 / 3, abs=1e-4)


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Traversals are defined recursively.", ["recursively"]),  # stem
        ("A binary search tree keeps order.", []),  # target's own name is masked
        ("A binary search tree is a binary tree with order.", ["binary tree"]),
        ("Nothing relevant here.", []),
    ],
)
def test_leaks(answer, expected):
    recursion = {"id": "recursion", "name": "Recursion"}
    binary_tree = {"id": "binary_tree", "name": "Binary Tree", "aliases": ["Binary Trees"]}
    bst = {"id": "binary_search_tree", "name": "Binary Search Tree", "aliases": ["BST"]}
    forbidden = recursion if expected == ["recursively"] else binary_tree

    assert nt.leaks(answer, forbidden, bst) == expected


def test_stemming_copy_matches_discovery():
    from cdlp.discovery import candidates

    for a, b in [
        ("recursion", "recursively"),
        ("trees", "tree"),
        ("query", "queries"),
        ("recursion", "recurrence"),
        ("graph", "paragraphs"),
    ]:
        assert nt._words_match(a, b) == candidates._words_match(a, b), (a, b)


@pytest.mark.parametrize("bad", [{}, {"questions": "x"}, ValueError("not JSON")])
def test_no_questions_gives_none_without_more_calls(llm, bad):
    llm.replies["necessity_questions_v1"] = bad

    r = run()

    assert (r["status"], r["necessity"], r["necessity_gap"]) == ("no_questions", "none", None)
    assert len(llm.calls) == 1


def test_missing_answers_and_bad_grades_count_as_incorrect(llm):
    llm.replies["necessity_learner_with_v1"] = {"answers": ["only one"]}
    llm.grader["only one"] = "excellent"  # not a grade

    r = run()

    assert r["answers_with"] == ["only one", "", ""]
    assert [g["grade"] for g in r["grades_with"]] == ["incorrect"] * 3


def test_cli_writes_results_and_only_filter(llm, tmp_path, monkeypatch):
    files = {}
    for name, data in [("r.json", RELATIONSHIPS), ("c.json", CONCEPTS)]:
        files[name] = tmp_path / name
        files[name].write_text(json.dumps(data))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("".join(json.dumps(c) + "\n" for c in CHUNKS))
    out = tmp_path / "necessity.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["necessity_test", "--relationships", str(files["r.json"]), "--concepts"]
        + [str(files["c.json"]), "--chunks", str(chunks), "--out", str(out), "--only", "r1"],
    )

    nt.main()

    data = json.loads(out.read_text())
    assert [r["relationship_id"] for r in data["results"]] == ["r1"]
    assert {
        "model",
        "prompt_versions",
        "seed",
        "temperature",
        "date",
        "leakage_rate",
    } <= data.keys()


def test_prompts_have_no_course_concepts():
    terms = ["tree", "recursion", "graph", "avl", "vector", "matri", "regression", "gradient"]
    for path in sorted(nt.PROMPT_DIR.glob("necessity_*_v1.txt")):
        text = path.read_text().lower()
        for term in terms:
            assert term not in text, (path.name, term)
