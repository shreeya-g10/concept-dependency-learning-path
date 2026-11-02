"""quiz_v2: focused excerpts, word-for-word quotes, and a second model that must agree."""

from __future__ import annotations

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


def item(question="What is true of an AVL tree?", answer=RIGHT, quote=QUOTE):
    return {
        "question": question,
        "options": [RIGHT, "Every node is red", "Keys are unsorted", "It has no root"],
        "correct_answer": answer,
        "source_quote": quote,
        "chunk_id": "c2",
    }


def fake(monkeypatch, items, verdict=None):
    calls = []

    def chat_json(prompt, **kwargs):
        calls.append((prompt, kwargs))
        if kwargs["prompt_version"] == "quiz_check_v1":
            options = [
                line.split(". ", 1)[1]
                for line in prompt.split("OPTIONS:\n", 1)[1].splitlines()
                if line[:2] in ("A.", "B.", "C.", "D.")
            ]
            letter = "ABCD"[options.index(RIGHT)]
            return verdict or {
                "correct_letter": letter,
                "only_one_correct": True,
                "about_topic": True,
            }
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
    assert [kw["prompt_version"] for _, kw in calls] == ["quiz_v2", "quiz_check_v1"]


def test_checker_never_sees_the_answer_label_or_the_quote(monkeypatch):
    calls = fake(monkeypatch, [item()])
    quiz.generate_quiz_items(DATA, CHUNKS)
    check_prompt = calls[1][0]
    assert "correct_answer" not in check_prompt and "source_quote" not in check_prompt


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
    for verdict, reason in [
        (
            {"correct_letter": "NONE", "only_one_correct": True, "about_topic": True},
            "check_disagrees",
        ),
        (
            {"correct_letter": "A", "only_one_correct": False, "about_topic": True},
            "check_not_one_answer",
        ),
        (
            {"correct_letter": "A", "only_one_correct": True, "about_topic": False},
            "check_off_topic",
        ),
    ]:
        fake(monkeypatch, [item()], verdict)
        out = quiz.generate_quiz_items(DATA, CHUNKS)
        assert out["items"] == [] and out["generation"]["skipped"] == {reason: 1}


def test_focused_chunks_prefer_the_topic_over_a_passing_mention():
    assert [c["chunk_id"] for c in quiz.focused_chunks(AVL, CHUNKS)] == ["c2", "c1"]


def test_only_graph_limits_concepts(monkeypatch, tmp_path):
    import json

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
