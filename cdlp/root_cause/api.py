"""Public API used by the website. Owner: Shreeya.

Keep this function signature stable; change everything behind it freely.
`graph` and `quiz_item` are parsed contract data (validated_graph.json and one
item of quiz_items.json). `mastery` maps concept id -> probability the student knows it.
"""


def trace(graph: dict, quiz_item: dict, answer: str, mastery: dict[str, float]) -> dict:
    """Return the most likely concept behind a wrong answer.

    Shape matches one entry of root_cause.json without `student_id`:
    {item_id, answer, traced_concept, candidates [{concept_id, score}], confidence, explanation}.
    """
    # TODO(Shreeya): LLM reads the wrong answer plus the item concept's prerequisite
    # chain (ACCEPT edges) and ranks candidate concepts. Until then this is the
    # "blame the target" baseline.
    concept = quiz_item["concept_id"]
    return {
        "item_id": quiz_item["id"],
        "answer": answer,
        "traced_concept": concept,
        "candidates": [{"concept_id": concept, "score": 1.0}],
        "confidence": 0.0,
        "explanation": "Stub: blames the item's own concept (baseline).",
    }
