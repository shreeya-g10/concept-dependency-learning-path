"""Public API used by the website. Owner: Shreeya.

Keep this function signature stable; change everything behind it freely.
`graph` and `quiz_item` are parsed contract data (validated_graph.json and one
item of quiz_items.json). `mastery` maps concept id -> probability the student knows it.
"""

from cdlp.root_cause.tracer import llm_trace


def trace(graph: dict, quiz_item: dict, answer: str, mastery: dict[str, float]) -> dict:
    """Return the most likely concept behind a wrong answer.

    Shape matches one entry of root_cause.json without `student_id`:
    {item_id, answer, traced_concept, candidates [{concept_id, score}], confidence, explanation}.

    LLM tracing over the item concept's prerequisite chain (ACCEPT edges); see
    tracer.py. Baselines for RQ3 are in baselines.py.
    """
    return llm_trace(graph, quiz_item, answer, mastery)
