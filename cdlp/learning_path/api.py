"""Public API used by the website (page 5). Owner: Shrestha.

Keep these three function signatures stable; change everything behind them freely.
Graph and quiz arguments are the parsed contract files (validated_graph.json,
quiz_items.json). `mastery` maps concept id -> probability the student knows it.
"""

from cdlp.shared.io import EXAMPLES, read_json


def next_question(graph: dict, quiz: dict, mastery: dict[str, float], target: str) -> dict | None:
    """Return the most informative quiz item to ask next, or None when diagnosis is done."""
    # TODO(Shrestha): information-gain selection over the target's prerequisite chain.
    return None


def update_mastery(
    graph: dict, mastery: dict[str, float], concept_id: str, correct: bool
) -> dict[str, float]:
    """Return new mastery after one answer (correct raises the concept and its ancestors)."""
    # TODO(Shrestha): real update rule.
    return {**mastery, concept_id: 0.9 if correct else 0.1}


def personalized_path(graph: dict, mastery: dict[str, float], target: str) -> list[dict]:
    """Return ordered steps [{concept_id, why, evidence}] from the student's gaps to the target."""
    # TODO(Shrestha): ancestors of target minus mastered concepts, topological order.
    example = read_json(EXAMPLES / "learning_path.json")["paths"][0]
    return (
        example["steps"]
        if target == example["target"]
        else [{"concept_id": target, "why": "Your target concept.", "evidence": []}]
    )
