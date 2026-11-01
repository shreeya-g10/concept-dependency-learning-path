"""RQ3 baselines. No LLM. Same return shape as api.trace.

- blame_target: always the item's own concept, then its prerequisites nearest first.
- blame_nearest: the direct ACCEPT prerequisite with the lowest mastery (hard before
  soft on ties, then id), then the other direct prerequisites, then the target, then the
  rest of the chain. With no prerequisites it falls back to the target.

Both rank the whole chain so top-3 accuracy is defined. Scores are rank-based
(1/rank, normalised to sum 1) and only encode the order; confidence is the top score.
"""

from __future__ import annotations

from cdlp.root_cause.chain import UNKNOWN_MASTERY, prerequisite_chain


def rank_scores(order: list[str]) -> list[dict]:
    raw = [1 / (i + 1) for i in range(len(order))]
    total = sum(raw)
    return [
        {"concept_id": c, "score": round(r / total, 4)} for c, r in zip(order, raw, strict=True)
    ]


def result(quiz_item: dict, answer: str, order: list[str], explanation: str) -> dict:
    candidates = rank_scores(order)
    return {
        "item_id": quiz_item["id"],
        "answer": answer,
        "traced_concept": order[0],
        "candidates": candidates,
        "confidence": candidates[0]["score"],
        "explanation": explanation,
    }


def blame_target(graph: dict, quiz_item: dict, answer: str, mastery: dict[str, float]) -> dict:
    target = quiz_item["concept_id"]
    order = [c["concept_id"] for c in prerequisite_chain(graph, target)]
    return result(quiz_item, answer, order, f"Baseline: blames the item's own concept {target}.")


def blame_nearest(graph: dict, quiz_item: dict, answer: str, mastery: dict[str, float]) -> dict:
    target = quiz_item["concept_id"]
    chain = prerequisite_chain(graph, target)
    strength_rank = {"hard": 0, "soft": 1}

    def direct_key(c: dict) -> tuple:
        strength = next(p["strength"] for p in c["prerequisite_of"] if p["concept_id"] == target)
        m = mastery.get(c["concept_id"], UNKNOWN_MASTERY)
        return (m, strength_rank.get(strength, 2), c["concept_id"])

    direct = sorted((c for c in chain if c["distance"] == 1), key=direct_key)
    rest = [c for c in chain if c["distance"] > 1]
    order = [c["concept_id"] for c in direct] + [target] + [c["concept_id"] for c in rest]
    if direct:
        top = direct[0]["concept_id"]
        why = (
            f"Baseline: blames {top}, the direct prerequisite of {target} with the lowest mastery."
        )
    else:
        why = f"Baseline: {target} has no prerequisites, so it blames {target}."
    return result(quiz_item, answer, order, why)


METHODS = {"target": blame_target, "nearest": blame_nearest}
