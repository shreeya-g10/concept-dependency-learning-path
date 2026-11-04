"""quiz_v2: focused excerpts, word-for-word quotes, and a second model that must agree."""

from __future__ import annotations

import json

import pytest

from cdlp.learning_path import quiz
from cdlp.shared.validate import check

CHUNKS = [
    {
        "chunk_id": "c1",
        "course_id": "x",
        "doc": "b.pdf",
        "page": 1,
        "heading": "Graphs",
        "text": "A graph has nodes. An AVL tree is mentioned once here.",
    },
    {
        "chunk_id": "c2",
        "course_id": "x",
        "doc": "b.pdf",
        "page": 2,
        "heading": "AVL Trees",
        "text": "An AVL tree is a binary search tree where subtree heights differ by at most one.",
    },
]
AVL = {"id": "avl_tree", "name": "AVL Tree", "aliases": ["AVL"], "description": "balanced tree"}
DATA = {"schema_version": "1.0", "course_id": "x", "concepts": [AVL]}
QUOTE = "subtree heights differ by at most one"
RIGHT = "Subtree heights differ by at most one"
RIGHT_2 = "It is a kind of binary search tree"


@pytest.fixture(autouse=True)
def _quiz_v2_is_kept_for_the_record(monkeypatch):
    """quiz_v3 became the default (test_quiz_v3.py); these tests keep testing v2."""
    monkeypatch.setattr(quiz, "PROMPT_VERSION", "quiz_v2")


def item(question="What is true of an AVL tree?", answer=RIGHT, quote=QUOTE):
    return {
        "question": question,
        "options": [RIGHT, "Every node is red", "Keys are unsorted", "It has no root"],
        "correct_answer": answer,
        "source_quote": quote,
        "chunk_id": "c2",
    }


def sound_verdict(prompt):
    """A checker's reply for an item that passes: one true option, which the quote proves."""
    options = [
        line.split(". ", 1)[1]
        for line in prompt.split("OPTIONS:\n", 1)[1].splitlines()
        if line[:2] in ("A.", "B.", "C.", "D.")
    ]
    letters = "ABCD"[: len(options)]
    return {
        "verdicts": {
            letter: option in (RIGHT, RIGHT_2)
            for letter, option in zip(letters, options, strict=True)
        },
        "quote_proves": next(
            letter
            for letter, option in zip(letters, options, strict=True)
            if option in (RIGHT, RIGHT_2)
        ),
        "same_subject": True,
        "about_topic": True,
    }


def fake(monkeypatch, items, verdict=None, retry_items=()):
    calls = []

    def chat_json(prompt, **kwargs):
        calls.append((prompt, kwargs))
        if kwargs["prompt_version"] == "quiz_check_v2":
            return verdict(prompt) if callable(verdict) else verdict or sound_verdict(prompt)
        if kwargs["prompt_version"] == "quiz_retry_v1":
            return {"items": list(retry_items)}
        return {"items": items}

    monkeypatch.setattr(quiz, "chat_json", chat_json)
    return calls


def test_good_item_is_kept_with_its_quote_and_source(monkeypatch):
    calls = fake(monkeypatch, [item()])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert check(out, "quiz_items") == []
    kept = out["items"][0]
    assert kept["source_quote"] == QUOTE and kept["chunk_id"] == "c2"
    assert out["generation"]["prompt_version"] == "quiz_v2"
    assert out["generation"]["items_checked"] == 1
    # one item is below the minimum, so the topic also got its retry (which added nothing)
    assert [kw["prompt_version"] for _, kw in calls] == [
        "quiz_v2",
        "quiz_check_v2",
        "quiz_retry_v1",
    ]


def test_checker_is_never_told_the_answer(monkeypatch):
    """The prompt is the same whichever option the draft marks as correct."""
    calls = fake(monkeypatch, [item()])
    quiz.generate_quiz_items(DATA, CHUNKS, check_version=quiz.OLD_CHECK_VERSION)
    first = calls[1][0]
    calls = fake(monkeypatch, [item(answer="Keys are unsorted")])
    quiz.generate_quiz_items(DATA, CHUNKS, check_version=quiz.OLD_CHECK_VERSION)
    assert calls[1][1]["prompt_version"] == "quiz_check_v2"
    assert calls[1][0] == first
    assert "correct_answer" not in first
    assert QUOTE in first  # the quote is shown, to judge whether it proves an option


def test_bad_items_are_dropped_and_counted(monkeypatch):
    fake(
        monkeypatch,
        [
            item(question="According to the course evidence, what is an AVL tree?"),
            item(question="What is a heap?", answer="Every node is red"),
            item(quote="this sentence was never in the book at all"),
            item(quote="short"),
        ],
    )
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert out["items"] == []
    assert out["generation"]["skipped"] == {
        "mentions_the_source": 1,
        "not_about_topic": 1,
        "quote_not_in_book": 1,
        "no_source_quote": 1,
    }
    assert out["generation"]["concepts_without_items"] == ["avl_tree"]


def test_second_model_can_veto(monkeypatch):
    def verdict(right="A", **changes):
        base = {
            "verdicts": {letter: letter == right for letter in "ABCD"},
            "quote_proves": right,
            "same_subject": True,
            "about_topic": True,
        }
        return {**base, **changes}

    # the options sort as: every node..., it has..., keys..., subtree heights... (RIGHT is D)
    for reply, reason in [
        (verdict("D", about_topic=False), "check_off_topic"),
        (verdict("A"), "check_disagrees"),
        (verdict("D", verdicts=dict.fromkeys("ABCD", False)), "check_none_true"),
        (
            verdict("D", verdicts={"A": True, "B": False, "C": False, "D": True}),
            "check_several_true",
        ),
        (verdict("D", same_subject=False), "check_quote_other_subject"),
        (verdict("D", quote_proves="NONE"), "check_quote_no_proof"),
        (verdict("D", quote_proves="A"), "check_quote_no_proof"),
        (verdict("D", verdicts={"D": True}), "check_bad_verdicts"),
        (
            verdict("D", verdicts={"A": False, "B": False, "C": False, "D": "maybe"}),
            "check_bad_verdicts",
        ),
        (verdict("D", verdicts=["D"]), "check_bad_verdicts"),
        ("not a dict", "check_reply_not_json"),
    ]:
        fake(monkeypatch, [item()], lambda _prompt, r=reply: r)
        out = quiz.generate_quiz_items(DATA, CHUNKS)
        assert out["items"] == [] and out["generation"]["skipped"] == {reason: 1}, reason


def test_a_sound_verdict_written_as_text_is_understood(monkeypatch):
    reply = {
        "verdicts": {"a": "false", "b": "False", "c": "false", "d": "TRUE"},
        "quote_proves": "d",
        "same_subject": "true",
        "about_topic": True,
    }
    fake(monkeypatch, [item()], reply)
    assert len(quiz.generate_quiz_items(DATA, CHUNKS)["items"]) == 1


def test_focused_chunks_prefer_the_topic_over_a_passing_mention():
    assert [c["chunk_id"] for c in quiz.focused_chunks(AVL, CHUNKS)] == ["c2", "c1"]


def test_only_graph_limits_concepts(monkeypatch, tmp_path):
    graph = tmp_path / "validated_graph.json"
    edges = [
        {"source": "a", "target": "avl_tree", "decision": "ACCEPT"},
        {"source": "b", "target": "c", "decision": "REJECT"},
    ]
    graph.write_text(json.dumps({"edges": edges}))
    concepts = tmp_path / "concepts.json"
    concepts.write_text(json.dumps({**DATA, "concepts": [AVL, {"id": "c", "name": "C"}]}))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("\n".join(json.dumps(c) for c in CHUNKS))
    fake(monkeypatch, [item()])
    out = tmp_path / "quiz_items.json"
    quiz.main(
        [
            "--concepts",
            str(concepts),
            "--chunks",
            str(chunks),
            "--out",
            str(out),
            "--only-graph",
            str(graph),
        ]
    )
    assert json.loads(out.read_text())["generation"]["concepts"] == 1


def second():
    """A second good item, with its own question, answer and quote."""
    return {
        **item(
            question="What kind of tree is an AVL tree?", quote="An AVL tree is a binary search"
        ),
        "options": [RIGHT_2, "It is a kind of heap", "It is a graph", "It is a list"],
        "correct_answer": RIGHT_2,
    }


def test_retry_says_why_drafts_failed_and_its_items_are_kept(monkeypatch):
    rejected = item(question="What is a heap?", answer="Every node is red")
    calls = fake(monkeypatch, [rejected, item()], retry_items=[second()])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    g = out["generation"]

    assert [i["id"] for i in out["items"]] == ["q_avl_tree_1", "q_avl_tree_2"]
    assert check(out, "quiz_items") == []
    assert g["topics_retried"] == ["avl_tree"] and g["retry_prompt_version"] == "quiz_retry_v1"
    assert g["min_items_per_topic"] == quiz.MIN_ITEMS_PER_TOPIC
    assert g["items_checked"] == 2  # the retry's draft was checked too
    assert g["skipped"] == {"not_about_topic": 1}  # the count survives the retry
    assert g["skipped_on_retry"] == {}

    prompt = next(p for p, kw in calls if kw["prompt_version"] == "quiz_retry_v1")
    assert '"What is a heap?"' in prompt and quiz.FAILURE_ADVICE["not_about_topic"] in prompt
    assert f"- {item()['question']}" in prompt  # already accepted, so not to be repeated
    assert "EXCERPTS FROM THE STUDENT'S BOOK" in prompt and QUOTE in prompt


def test_each_topic_gets_at_most_one_retry(monkeypatch):
    calls = fake(monkeypatch, [], retry_items=[])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    versions = [kw["prompt_version"] for _, kw in calls]
    assert versions == ["quiz_v2", "quiz_retry_v1"]
    assert out["generation"]["concepts_without_items"] == ["avl_tree"]


def test_enough_items_means_no_retry(monkeypatch):
    calls = fake(monkeypatch, [item(), second()])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert len(out["items"]) == 2 and out["generation"]["topics_retried"] == []
    assert "quiz_retry_v1" not in [kw["prompt_version"] for _, kw in calls]


def test_retry_drafts_face_the_same_checks(monkeypatch):
    """The retry never loosens a check: bad drafts stay out, and are counted as such."""
    invented = {**second(), "source_quote": "this sentence was never in the book at all"}
    off_topic = item(question="What is a heap?", answer="Every node is red")
    duplicate = item()
    fake(monkeypatch, [item()], retry_items=[invented, off_topic, duplicate])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert [i["id"] for i in out["items"]] == ["q_avl_tree_1"]
    expected = {"quote_not_in_book": 1, "not_about_topic": 1, "near_duplicate": 1}
    assert out["generation"]["skipped"] == expected
    assert out["generation"]["skipped_on_retry"] == expected


def test_second_model_vetoes_retry_drafts_too(monkeypatch):
    def only_first(prompt):
        return sound_verdict(prompt) if "What is true of" in prompt else {"about_topic": False}

    fake(monkeypatch, [item()], only_first, retry_items=[second()])
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert [i["question"] for i in out["items"]] == [item()["question"]]
    assert out["generation"]["skipped_on_retry"] == {"check_off_topic": 1}
    assert out["generation"]["items_checked"] == 2


def test_bad_reply_is_counted_and_retried(monkeypatch):
    def chat_json(prompt, **kwargs):
        if kwargs["prompt_version"] == "quiz_v2":
            raise json.JSONDecodeError("bad", "doc", 0)
        if kwargs["prompt_version"] == "quiz_retry_v1":
            assert quiz.FAILURE_ADVICE["reply_not_json"] in prompt
            return {"items": [item(), second()]}
        return sound_verdict(prompt)

    monkeypatch.setattr(quiz, "chat_json", chat_json)
    out = quiz.generate_quiz_items(DATA, CHUNKS)
    assert len(out["items"]) == 2 and out["generation"]["skipped"] == {"reply_not_json": 1}


def test_retry_prompt_survives_a_reason_with_no_advice():
    topic = {
        "concept": AVL,
        "evidence": CHUNKS,
        "items": [],
        "failures": [("Q?", "a_new_reason")],
    }
    prompt = quiz._retry_prompt(
        topic, quiz.load_prompt("quiz_v2"), quiz.load_prompt("quiz_retry_v1")
    )
    assert '- "Q?": It failed a check.' in prompt


@pytest.mark.parametrize(
    "name", ["quiz.json", "ds101_review.json", "my_concepts.json", "items.txt"]
)
def test_bad_out_name_stops_before_any_llm_call(monkeypatch, tmp_path, name, capsys):
    def no_llm(*args, **kwargs):
        raise AssertionError("no LLM call may start")

    monkeypatch.setattr(quiz, "chat_json", no_llm)
    concepts = tmp_path / "concepts.json"
    concepts.write_text(json.dumps(DATA))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("\n".join(json.dumps(c) for c in CHUNKS))
    args = ["--concepts", str(concepts), "--chunks", str(chunks), "--out", str(tmp_path / name)]
    with pytest.raises(SystemExit) as stopped:
        quiz.main(args)
    assert stopped.value.code == 2
    assert "must end in quiz_items.json" in capsys.readouterr().err
    assert not (tmp_path / name).exists()


@pytest.mark.parametrize("name", ["quiz_items.json", "ds101_review_quiz_items.json"])
def test_good_out_name_is_saved(monkeypatch, tmp_path, name):
    fake(monkeypatch, [item(), second()])
    concepts = tmp_path / "concepts.json"
    concepts.write_text(json.dumps(DATA))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("\n".join(json.dumps(c) for c in CHUNKS))
    out = tmp_path / name
    quiz.main(["--concepts", str(concepts), "--chunks", str(chunks), "--out", str(out)])
    assert len(json.loads(out.read_text())["items"]) == 2
