"""quiz_v3: one question per level, the same checks as before, drop rates per level. No LLM."""

from pathlib import Path

from cdlp.learning_path import quiz
from cdlp.shared.validate import check

PROMPTS = Path(quiz.__file__).parent / "prompts"
TEXT = (
    "An AVL tree is a binary search tree. Subtree heights in an AVL tree differ by at most one. "
    "Each insert into an AVL tree may need a rotation. A red black tree allows more imbalance."
)
CHUNKS = [
    {"chunk_id": "c1", "course_id": "x", "doc": "b.pdf", "page": 1, "heading": "AVL", "text": TEXT}
]
AVL = {"id": "avl_tree", "name": "AVL Tree", "aliases": ["AVL"], "description": "balanced"}
DATA = {"schema_version": "1.0", "course_id": "x", "concepts": [AVL]}


def draft(question, answer, quote, level):
    return {
        "question": question,
        "options": [answer, "Wrong one", "Wrong two", "Wrong three"],
        "correct_answer": answer,
        "source_quote": quote,
        "chunk_id": "c1",
        **({"difficulty": level} if level else {}),
    }


EASY = draft("What is an AVL tree?", "A binary search tree", "AVL tree is a binary search", "easy")
MEDIUM = draft(
    "How far can AVL tree subtree heights differ?",
    "At most one",
    "heights in an AVL tree differ by at most one",
    "medium",
)
HARD = draft(
    "After an insert, what may an AVL tree need?",
    "A rotation",
    "insert into an AVL tree may need a rotation",
    "hard",
)


def fake(monkeypatch, drafts, failing=()):
    calls = []

    def chat_json(prompt, **kwargs):
        calls.append(kwargs["prompt_version"])
        if kwargs["prompt_version"] != "quiz_check_v2":
            return {"items": drafts}
        lines = prompt.split("OPTIONS:\n", 1)[1].splitlines()
        options = [ln.split(". ", 1)[1] for ln in lines if ln[:2] in ("A.", "B.", "C.", "D.")]
        right = next(i for i, o in enumerate(options) if not o.startswith("Wrong"))
        fail = any(d["question"] in prompt for d in failing)
        return {
            "verdicts": {"ABCD"[i]: i == right and not fail for i in range(len(options))},
            "quote_proves": "ABCD"[right],
            "same_subject": True,
            "about_topic": True,
        }

    monkeypatch.setattr(quiz, "chat_json", chat_json)
    return calls


def test_quiz_v3_is_the_default_and_quiz_v2_is_kept():
    assert quiz.PROMPT_VERSION == "quiz_v3"
    assert (PROMPTS / "quiz_v2.txt").is_file()
    assert "difficulty" not in (PROMPTS / "quiz_v2.txt").read_text()


def test_the_prompt_asks_for_each_level_and_keeps_the_v2_rules():
    text = (PROMPTS / "quiz_v3.txt").read_text()
    for word in ("one easy, one medium and one hard", "recalls", "applies", "compares", "traces"):
        assert word in text
    assert "word for word" in text and "source_quote" in text


def test_kept_items_carry_their_level_as_a_suggestion_only(monkeypatch):
    fake(monkeypatch, [EASY, MEDIUM, HARD])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert check(out, "quiz_items") == []
    assert out["schema_version"] == "1.13"
    assert [i["difficulty"] for i in out["items"]] == ["easy", "medium", "hard"]
    assert {i["difficulty_source"] for i in out["items"]} == {"ai_suggestion"}
    assert out["generation"]["prompt_version"] == "quiz_v3"
    assert out["generation"]["concepts_missing_level"] == {"easy": [], "medium": [], "hard": []}


def test_the_drop_rate_is_reported_per_level(monkeypatch):
    fake(monkeypatch, [EASY, MEDIUM, HARD], failing=[HARD])
    g = quiz.generate_quiz_items(DATA, CHUNKS)["generation"]
    rates = g["drop_rate_by_level"]
    assert rates["easy"] == {"drafted": 1, "kept": 1, "dropped": 0, "drop_rate": 0.0}
    assert rates["hard"] == {"drafted": 1, "kept": 0, "dropped": 1, "drop_rate": 1.0}
    assert rates["unlabelled"]["drop_rate"] is None
    assert g["concepts_missing_level"]["hard"] == ["avl_tree"]
    assert g["skipped"] == {"check_none_true": 1}


def test_no_check_is_loosened_for_a_hard_question(monkeypatch):
    """Each check that drops a medium question also drops the same question marked hard."""
    no_quote = draft(
        "What may an AVL tree need?", "A rotation", "this quote is not in the book", ""
    )
    unsupported = draft(
        "Which tree allows more imbalance than an AVL tree?",
        "Something else entirely different",
        "A red black tree allows more imbalance",
        "",
    )
    off_topic = draft("What is a red black tree?", "A tree", "red black tree allows more", "")
    for bad in (no_quote, unsupported, off_topic):
        reasons = []
        for level in ("medium", "hard"):
            fake(monkeypatch, [EASY, {**bad, "difficulty": level}])
            out = quiz.generate_quiz_items(DATA, CHUNKS)
            first = [d for d in out["generation"]["dropped"] if d["question"] == bad["question"]]
            reasons.append(first[0]["reason"] if first else None)
            assert all(i["question"] != bad["question"] for i in out["items"])
        assert reasons[0] == reasons[1] and reasons[0]


def test_two_questions_on_one_quote_are_still_dropped(monkeypatch):
    twin = draft(
        "Does an AVL tree balance by height?", "Yes it does", MEDIUM["source_quote"], "hard"
    )
    fake(monkeypatch, [MEDIUM, twin])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert out["generation"]["skipped"]["near_duplicate"] == 1
    assert out["generation"]["drop_rate_by_level"]["hard"]["drop_rate"] == 1.0


def test_a_missing_or_odd_label_keeps_the_item_unlabelled(monkeypatch):
    fake(monkeypatch, [{**EASY, "difficulty": "impossible"}, {**MEDIUM, "difficulty": " HARD "}])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert "difficulty" not in out["items"][0] and "difficulty_source" not in out["items"][0]
    assert out["items"][1]["difficulty"] == "hard"
    assert out["generation"]["drop_rate_by_level"]["unlabelled"]["kept"] == 1
    assert check(out, "quiz_items") == []


def test_quiz_v2_runs_write_no_levels(monkeypatch):
    fake(monkeypatch, [EASY, MEDIUM])
    out = quiz.generate_quiz_items(DATA, CHUNKS, prompt_version="quiz_v2")
    assert all("difficulty" not in i for i in out["items"])
    assert "drop_rate_by_level" not in out["generation"]


def test_a_retry_asks_for_three_new_questions(monkeypatch):
    calls = []

    def chat_json(prompt, **kwargs):
        calls.append((kwargs["prompt_version"], prompt))
        return {"items": []}

    monkeypatch.setattr(quiz, "chat_json", chat_json)
    quiz.generate_quiz_items(DATA, CHUNKS)
    assert [c[0] for c in calls] == ["quiz_v3", "quiz_retry_v1"]
    assert "Write 3 new questions" in calls[1][1]
