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


def fake(monkeypatch, drafts, failing=(), retry_drafts=(), prompts=None):
    calls = []
    prompts = [] if prompts is None else prompts
    retry_drafts = list(retry_drafts)

    def chat_json(prompt, **kwargs):
        calls.append(kwargs["prompt_version"])
        prompts.append(prompt)
        if kwargs["prompt_version"] == "quiz_retry_v2":
            return {"items": retry_drafts}
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
        "Which limit does an AVL tree put on heights?",
        "Differ by at most one",
        MEDIUM["source_quote"],
        "hard",
    )
    fake(monkeypatch, [MEDIUM, twin])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    dropped = next(d for d in out["generation"]["dropped"] if d["question"] == twin["question"])
    assert dropped["reason"] == "near_duplicate"
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


def test_no_retry_when_every_level_is_there(monkeypatch):
    calls = fake(monkeypatch, [EASY, MEDIUM, HARD])
    g = quiz.generate_quiz_items(DATA, CHUNKS)["generation"]
    assert "quiz_retry_v2" not in calls
    assert g["topics_retried"] == [] and g["retried_only_for_missing_level"] == []
    assert g["retry_prompt_version"] == "quiz_retry_v2"


def test_a_missing_level_gets_the_retry_even_with_enough_items(monkeypatch):
    """Two items were enough for the older rule, so this retry is an extra one."""
    calls = fake(monkeypatch, [EASY, MEDIUM], retry_drafts=[HARD])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    g = out["generation"]
    assert calls.count("quiz_retry_v2") == 1
    assert g["topics_retried"] == ["avl_tree"]
    assert g["retried_only_for_missing_level"] == ["avl_tree"]
    assert [i["difficulty"] for i in out["items"]] == ["easy", "medium", "hard"]
    assert g["concepts_missing_level"]["hard"] == []
    assert check(out, "quiz_items") == []


def test_the_retry_says_which_level_is_missing_and_why_its_draft_failed(monkeypatch):
    prompts = []
    fake(monkeypatch, [EASY, MEDIUM, HARD], failing=[HARD], prompts=prompts)
    quiz.generate_quiz_items(DATA, CHUNKS)
    retry = next(p for p in prompts if "SECOND ATTEMPT" in p)
    assert "left these levels with no good question: hard." in retry
    assert f'- hard question "{HARD["question"]}": ' in retry
    assert quiz.FAILURE_ADVICE["check_none_true"] in retry
    assert "Write 1 new questions, one for each missing level: hard." in retry
    assert EASY["question"] in retry and MEDIUM["question"] in retry  # the ones to leave alone


def test_the_retry_says_so_when_a_level_was_never_written(monkeypatch):
    prompts = []
    fake(monkeypatch, [EASY, MEDIUM], prompts=prompts)
    quiz.generate_quiz_items(DATA, CHUNKS)
    retry = next(p for p in prompts if "SECOND ATTEMPT" in p)
    assert "- No hard question was written." in retry


def test_missing_levels_are_shown_first_so_the_limit_never_cuts_them():
    topic = {
        "items": [
            {"question": "q", "difficulty": "easy"},
            {"question": "r", "difficulty": "medium"},
        ],
        "failures": [(f"easy {n}", "near_duplicate") for n in range(20)] + [("the hard one", "x")],
        "failure_levels": {**{f"easy {n}": "easy" for n in range(20)}, "the hard one": "hard"},
    }
    lines = quiz._levelled_failures(topic, ["hard"])
    assert lines[0].startswith('- hard question "the hard one"')
    assert len(lines) == quiz.MAX_FAILURES_SHOWN


def test_it_is_one_retry_per_topic_even_if_the_level_is_still_missing(monkeypatch):
    calls = fake(monkeypatch, [EASY, MEDIUM], retry_drafts=[])
    g = quiz.generate_quiz_items(DATA, CHUNKS)["generation"]
    assert calls.count("quiz_retry_v2") == 1
    assert g["concepts_missing_level"]["hard"] == ["avl_tree"]


def test_retry_drafts_pass_the_same_checks(monkeypatch):
    bad_hard = draft(
        "What may an AVL tree need?", "A rotation", "this quote is not in the book", "hard"
    )
    fake(monkeypatch, [EASY, MEDIUM], retry_drafts=[bad_hard])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    g = out["generation"]
    assert all(i["difficulty"] != "hard" for i in out["items"])
    assert g["skipped_on_retry"] == {"quote_not_in_book": 1}
    assert g["drop_rate_by_level"]["hard"] == {
        "drafted": 1,
        "kept": 0,
        "dropped": 1,
        "drop_rate": 1.0,
    }


def test_a_topic_with_nothing_kept_retries_for_every_level_and_is_not_an_extra_retry(monkeypatch):
    prompts = []
    calls = fake(monkeypatch, [], prompts=prompts)
    g = quiz.generate_quiz_items(DATA, CHUNKS)["generation"]
    assert calls == ["quiz_v3", "quiz_retry_v2"]
    assert g["retried_only_for_missing_level"] == []  # the older rule retried this one too
    assert "Write 3 new questions, one for each missing level: easy, medium, hard." in prompts[1]


def test_quiz_v2_keeps_its_own_retry_rule(monkeypatch):
    calls = fake(monkeypatch, [EASY, MEDIUM])
    g = quiz.generate_quiz_items(DATA, CHUNKS, prompt_version="quiz_v2")["generation"]
    assert "quiz_retry_v1" not in calls and "quiz_retry_v2" not in calls  # two items were enough
    assert g["retry_prompt_version"] == "quiz_retry_v1"
    assert (PROMPTS / "quiz_retry_v1.txt").is_file()
