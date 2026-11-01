"""LLM discovery: ask the LLM whether each candidate pair is a direct prerequisite.

Discovery only proposes edges. It never rewrites or drops an edge for graph
reasons by default: cycles, duplicates and transitive redundancy are the
validator's graph check (cdlp/validation/graph_checks.py).
"""

from pathlib import Path

from cdlp.shared.llm import chat_json

PROMPT_VERSION = "discover_v2"  # discover_v1 is kept for the record; it leaked gold pairs
TEMPERATURE = 0.0

# The prompt asks for a confidence *label*; the contract needs a number in [0, 1].
# These values are a fixed, arbitrary ordinal mapping, not calibrated probabilities.
# Unknown or missing labels get LOW. Change them only together with PROMPT_VERSION.
CONFIDENCE_SCORES = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5}
DEFAULT_CONFIDENCE = CONFIDENCE_SCORES["LOW"]


def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (Path(__file__).parent / "prompts" / f"{version}.txt").read_text()


def confidence_score(label) -> float:
    """Map the LLM's HIGH/MEDIUM/LOW label to a number; tolerate numbers and junk."""
    if isinstance(label, (int, float)) and not isinstance(label, bool) and 0 <= label <= 1:
        return float(label)
    if isinstance(label, str):
        return CONFIDENCE_SCORES.get(label.strip().upper(), DEFAULT_CONFIDENCE)
    return DEFAULT_CONFIDENCE


def _normalise_result(result, source_id: str, target_id: str, allowed_chunks: set) -> dict:
    """Turn whatever the LLM returned into one well-formed record. Malformed -> NONE."""
    if not isinstance(result, dict):
        result = {}
    relationship = str(result.get("relationship", "NONE")).strip().upper()
    strength = str(result.get("strength", "NONE")).strip().lower()
    if relationship != "DIRECT" or strength not in {"hard", "soft"}:
        relationship, strength = "NONE", "none"
    chunk_ids = result.get("evidence_chunk_ids")
    if not isinstance(chunk_ids, list):
        chunk_ids = []
    return {
        "source": source_id,  # always ours, never the LLM's
        "target": target_id,
        "relationship": relationship,
        "strength": strength,
        "confidence": confidence_score(result.get("confidence")),
        # only chunks we actually showed the LLM count as evidence
        "evidence_chunk_ids": [c for c in chunk_ids if c in allowed_chunks],
    }


def discover_relationship(
    source: dict,
    target: dict,
    evidence: list[dict],
    candidate_reasons: list[str],
    prompt_version: str = PROMPT_VERSION,
) -> dict:
    evidence_text = "\n".join(f"Chunk ID: {item['chunk_id']}\n{item['text']}" for item in evidence)
    prompt = load_prompt(prompt_version).format(
        source_id=source["id"],
        source_name=source["name"],
        source_description=source.get("description", ""),
        target_id=target["id"],
        target_name=target["name"],
        target_description=target.get("description", ""),
        candidate_reasons=", ".join(candidate_reasons),
        evidence=evidence_text,
    )
    try:
        result = chat_json(prompt, prompt_version=prompt_version, temperature=TEMPERATURE)
    except ValueError:  # the model returned text that is not JSON
        result = {}
    return _normalise_result(
        result, source["id"], target["id"], {item["chunk_id"] for item in evidence}
    )


def _evidence_for(source: dict, target: dict, chunk_map: dict) -> list[dict]:
    evidence = []
    for concept in (source, target):
        for source_info in concept.get("sources", []):
            chunk = chunk_map.get(source_info.get("chunk_id"))
            if chunk is not None and chunk not in evidence:
                evidence.append(chunk)
    return evidence


def _merge_both_directions(forward: dict, backward: dict) -> dict:
    """A tied pair was asked both ways. Keep ONE record, never two opposite edges."""
    forward_direct = forward["relationship"] == "DIRECT"
    backward_direct = backward["relationship"] == "DIRECT"
    if forward_direct and backward_direct:
        # the stronger-confidence direction is kept; ties keep the alphabetical one
        kept, other = (
            (backward, forward)
            if backward["confidence"] > forward["confidence"]
            else (
                forward,
                backward,
            )
        )
        return {
            **kept,
            "bidirectional": True,
            "reverse_strength": other["strength"],
            "reverse_confidence": other["confidence"],
        }
    return backward if backward_direct else forward


def transitive_edges(relationships: list[dict]) -> set:
    """DIRECT edges implied by a longer path of other DIRECT edges (any length).

    Pure Python (CI has no networkx). An edge u -> v is redundant if v is still
    reachable from u without that edge. Only used behind --remove-transitive.
    """
    edges = {(r["source"], r["target"]) for r in relationships if r.get("relationship") == "DIRECT"}
    successors: dict[str, set] = {}
    for u, v in edges:
        successors.setdefault(u, set()).add(v)

    def reachable_without(u: str, v: str) -> bool:
        stack, seen = [w for w in successors.get(u, ()) if w != v], set()
        while stack:
            node = stack.pop()
            if node == v:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(successors.get(node, ()))
        return False

    if any(reachable_without(v, u) or (v, u) in edges for u, v in edges):
        return set()  # cyclic: redundancy is undefined; leave it to the validator
    return {(u, v) for u, v in edges if reachable_without(u, v)}


def discover_candidates(
    candidates: list,
    concepts: list[dict],
    chunks: list[dict],
    remove_transitive: bool = False,
    prompt_version: str = PROMPT_VERSION,
) -> list[dict]:
    concept_map = {concept["id"]: concept for concept in concepts}
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}

    relationships = []
    for candidate in candidates:
        source = concept_map[candidate.source]
        target = concept_map[candidate.target]
        evidence = _evidence_for(source, target, chunk_map)
        forward = discover_relationship(source, target, evidence, candidate.reasons, prompt_version)
        if getattr(candidate, "tied", False):
            backward = discover_relationship(
                target, source, evidence, candidate.reasons, prompt_version
            )
            forward = _merge_both_directions(forward, backward)
        relationships.append(forward)

    if remove_transitive:
        # opt-in only: redundant edges are left out of the output; no record is rewritten
        redundant = transitive_edges(relationships)
        relationships = [r for r in relationships if (r["source"], r["target"]) not in redundant]
    return relationships


def build_contract_relationships(
    relationships: list[dict],
    concepts: list[dict],
    chunks: list[dict],
    prompt_version: str = PROMPT_VERSION,
) -> list[dict]:
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    contract = []
    for relationship in relationships:
        if relationship.get("relationship") != "DIRECT":
            continue
        strength = str(relationship.get("strength", "")).lower()
        if strength not in {"hard", "soft"}:
            continue

        evidence = []
        for chunk_id in relationship.get("evidence_chunk_ids", []):
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            item = {"chunk_id": chunk_id, "quote": chunk.get("text", "")[:200]}
            if chunk.get("doc"):
                item["doc"] = chunk["doc"]
            if isinstance(chunk.get("page"), int) and chunk["page"] >= 1:
                item["page"] = chunk["page"]  # schema: page >= 1, so never write a fake 0
            evidence.append(item)

        edge = {
            "id": f"r{len(contract) + 1}",
            "source": relationship["source"],
            "target": relationship["target"],
            "type": "PREREQUISITE",
            "strength": strength,
            "confidence": confidence_score(relationship.get("confidence")),
            "evidence": evidence,
            "method": f"llm_{prompt_version}",
        }
        if relationship.get("bidirectional"):
            edge["bidirectional"] = True
            edge["reverse_strength"] = relationship["reverse_strength"]
            edge["reverse_confidence"] = relationship["reverse_confidence"]
        contract.append(edge)
    return contract
