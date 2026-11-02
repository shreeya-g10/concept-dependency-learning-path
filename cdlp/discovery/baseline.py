"""Baseline for RQ1: one LLM call with the full concept list, no candidate filter.

The model sees every concept at once and returns all prerequisite pairs. The
output has the same format as relationships.json, so the same evaluation and the
validator can run on it, and it is written to relationships_baseline.json.
Evidence is empty: the baseline gets no course chunks, by design.
"""

from pathlib import Path

from cdlp.discovery.llm_discovery import TEMPERATURE, confidence_score
from cdlp.shared.llm import chat_json

BASELINE_PROMPT_VERSION = "baseline_v1"


def load_prompt(version: str = BASELINE_PROMPT_VERSION) -> str:
    return (Path(__file__).parent / "prompts" / f"{version}.txt").read_text()


def _concept_lines(concepts: list[dict]) -> str:
    return "\n".join(
        f"{concept['id']}: {concept['name']} - {concept.get('description', '')}".rstrip(" -")
        for concept in concepts
    )


def _clean(raw, concept_ids: set) -> list[dict]:
    """Keep well-formed pairs between known concepts; one record per unordered pair."""
    rows = raw.get("relationships") if isinstance(raw, dict) else None
    kept: dict[frozenset, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        source, target = row.get("source"), row.get("target")
        strength = str(row.get("strength", "")).strip().lower()
        if source not in concept_ids or target not in concept_ids or source == target:
            continue
        if strength not in {"hard", "soft"}:
            continue
        record = {
            "source": source,
            "target": target,
            "strength": strength,
            "confidence": confidence_score(row.get("confidence")),
        }
        pair = frozenset((source, target))
        previous = kept.get(pair)
        if previous is None:
            kept[pair] = record
        elif (previous["source"], previous["target"]) != (source, target):
            # both directions despite rule 3: keep one edge, flag it like discovery does
            stronger, weaker = (
                (record, previous)
                if record["confidence"] > previous["confidence"]
                else (previous, record)
            )
            kept[pair] = {
                **stronger,
                "bidirectional": True,
                "reverse_strength": weaker["strength"],
                "reverse_confidence": weaker["confidence"],
            }
    return list(kept.values())


def discover_baseline(
    concepts: list[dict],
    prompt_version: str = BASELINE_PROMPT_VERSION,
    num_ctx: int | None = None,
) -> list[dict]:
    """One LLM call; returns contract-format edges (relationships.json items).
    num_ctx: a full concept list plus its answer can exceed Ollama's default 4096 tokens."""
    prompt = load_prompt(prompt_version).format(concepts=_concept_lines(concepts))
    extra = {"num_ctx": num_ctx} if num_ctx else {}
    try:
        raw = chat_json(prompt, prompt_version=prompt_version, temperature=TEMPERATURE, **extra)
    except ValueError:  # not JSON
        raw = {}
    edges = []
    for n, record in enumerate(_clean(raw, {c["id"] for c in concepts}), start=1):
        edges.append(
            {
                "id": f"b{n}",
                "source": record.pop("source"),
                "target": record.pop("target"),
                "type": "PREREQUISITE",
                "strength": record.pop("strength"),
                "confidence": record.pop("confidence"),
                "evidence": [],
                "method": f"llm_{prompt_version}",
                **record,  # bidirectional fields, if any
            }
        )
    return edges
