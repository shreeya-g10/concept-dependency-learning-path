from cdlp.discovery import quiz
from cdlp.discovery.quiz import generate_quiz_items


def fake_chat_json(prompt, **kwargs):
    """Stands in for the LLM: three well-formed items, as quiz_v1.txt asks for."""
    return {
        "items": [
            {
                "question": f"Question {n} about recursion?",
                "options": ["A base case", "A loop", "A global", "A counter"],
                "correct_answer": "A base case",
                "explanation": "Recursion stops at a base case.",
                "evidence_chunk_ids": ["ch1"],
            }
            for n in range(1, 4)
        ]
    }


def test_quiz_items_structure(monkeypatch):
    monkeypatch.setattr(quiz, "chat_json", fake_chat_json)

    concepts = [
        {
            "id": "recursion",
            "name": "Recursion",
            "description": "A function defined in terms of itself.",
            "sources": [
                {
                    "chunk_id": "ch1",
                }
            ],
        }
    ]

    chunks = [
        {
            "chunk_id": "ch1",
            "doc": "test.pdf",
            "page": 1,
            "text": (
                "A recursive function calls itself on a smaller input until it reaches a base case."
            ),
        }
    ]

    items = generate_quiz_items(
        concepts,
        chunks,
    )

    assert len(items) == 3

    for item in items:
        assert item["id"]
        assert item["concept_id"] == "recursion"
        assert item["question"]
        assert len(item["options"]) == 4
        assert item["answer"]
        assert item["explanation"]
        assert item["evidence_chunk_ids"]

        assert item["answer"] in item["options"]

        for chunk_id in item["evidence_chunk_ids"]:
            assert chunk_id == "ch1"
