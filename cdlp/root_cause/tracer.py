"""LLM root-cause tracing (prompt prompts/trace_v1.txt).

The LLM sees the question, its options, the correct and the student's answer, and the
item concept's prerequisite chain over ACCEPT edges with the student's mastery of each
concept. It returns ranked candidates with scores and a one-sentence explanation.

Post-processing keeps the output inside the chain: unknown ids are dropped, duplicates
keep their first score, scores are clamped to [0, 1] and normalised to sum 1, and chain
concepts the LLM left out are appended with score 0 (nearest first) so top-k is always
defined. If nothing usable comes back, the trace falls back to the nearest-prerequisite
baseline and the explanation starts with FALLBACK_PREFIX, so evaluation can count it.
Connection errors are not caught: a run with no LLM must fail loudly, not silently
turn into a baseline.

A chain with a single concept (no prerequisites) needs no LLM call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cdlp.root_cause.baselines import blame_nearest
from cdlp.root_cause.chain import prerequisite_chain
from cdlp.shared import llm

PROMPT_VERSION = "trace_v1"
PROMPT_FILE = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"
TEMPERATURE = 0.0
FALLBACK_PREFIX = "[fallback: nearest prerequisite]"


def model_id() -> str:
    return os.getenv("LLM_MODEL", llm.DEFAULT_MODEL)


def describe_chain(chain: list[dict], target: str, mastery: dict[str, float]) -> str:
    lines = []
    for c in chain:
        if c["concept_id"] == target:
            role = "the question's concept"
        else:
            role = ", ".join(
                f"{p['strength']} prerequisite of {p['concept_id']}" for p in c["prerequisite_of"]
            )
        m = mastery.get(c["concept_id"])
        shown = "unknown" if m is None else f"{m:.2f}"
        lines.append(f'- {c["concept_id"]} "{c["name"]}" ({role}), mastery {shown}')
    return "\n".join(lines)


def build_prompt(quiz_item: dict, answer: str, chain: list[dict], mastery: dict) -> str:
    target = quiz_item["concept_id"]
    replacements = {
        "{target}": target,
        "{question}": quiz_item.get("question", ""),
        "{options}": " | ".join(str(o) for o in quiz_item.get("options", [])) or "(open answer)",
        "{correct_answer}": str(quiz_item.get("answer", "(not given)")),
        "{student_answer}": answer,
        "{chain}": describe_chain(chain, target, mastery),
    }
    prompt = PROMPT_FILE.read_text()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def parse_candidates(raw: dict, chain_ids: list[str]) -> list[dict]:
    """Clean the LLM's candidate list; return [] if nothing usable is left."""
    seen: dict[str, float] = {}
    for cand in raw.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        cid = cand.get("concept_id")
        try:
            score = float(cand.get("score", 0))
        except (TypeError, ValueError):
            continue
        if cid in chain_ids and cid not in seen:
            seen[cid] = min(max(score, 0.0), 1.0)
    total = sum(seen.values())
    if total <= 0:
        return []
    ranked = sorted(seen.items(), key=lambda kv: -kv[1])  # stable: LLM order on ties
    out = [{"concept_id": c, "score": round(s / total, 4)} for c, s in ranked]
    out += [{"concept_id": c, "score": 0.0} for c in chain_ids if c not in seen]
    return out


def llm_trace(graph: dict, quiz_item: dict, answer: str, mastery: dict[str, float]) -> dict:
    target = quiz_item["concept_id"]
    chain = prerequisite_chain(graph, target)
    chain_ids = [c["concept_id"] for c in chain]
    base = {"item_id": quiz_item["id"], "answer": answer}

    if len(chain) == 1:
        return {
            **base,
            "traced_concept": target,
            "candidates": [{"concept_id": target, "score": 1.0}],
            "confidence": 1.0,
            "explanation": f"{target} has no prerequisites in the graph, so the gap is in it.",
        }

    try:
        raw = llm.chat_json(
            build_prompt(quiz_item, answer, chain, mastery),
            system="You diagnose student misconceptions. Reply in JSON only.",
            model=model_id(),
            temperature=TEMPERATURE,
            prompt_version=PROMPT_VERSION,
        )
    except json.JSONDecodeError:
        raw = {}
    candidates = parse_candidates(raw if isinstance(raw, dict) else {}, chain_ids)
    if not candidates:
        fallback = blame_nearest(graph, quiz_item, answer, mastery)
        fallback["explanation"] = f"{FALLBACK_PREFIX} {fallback['explanation']}"
        return fallback

    explanation = raw.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        explanation = "(no explanation given)"
    return {
        **base,
        "traced_concept": candidates[0]["concept_id"],
        "candidates": candidates,
        "confidence": candidates[0]["score"],
        "explanation": " ".join(explanation.split()),
    }
