"""Candidate filter: pick the concept pairs worth sending to the LLM.

A pair becomes a candidate only if at least one *content* signal links the two
concepts (same chunk, one's name in the other's definition, or embedding
similarity). Course order is never enough on its own: it only orients the pair
(earlier concept = source) and is then recorded as a weak extra reason.

If both concepts sit at the same course position, there is no order to orient
by, so the candidate is marked ``tied`` and discovery asks about both directions.
"""

import re
from dataclasses import dataclass

import numpy as np

CONTENT_SIGNALS = ("same_chunk", "name_in_definition", "embedding_similarity")


@dataclass
class Candidate:
    source: str
    target: str
    reasons: list
    tied: bool = False  # same course position: ask the LLM about both directions


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _terms(concept: dict) -> list:
    return [
        _normalise(concept["name"]),
        *[_normalise(alias) for alias in concept.get("aliases", [])],
    ]


def _course_position(concepts: list, chunks: list) -> dict:
    """Index of the first chunk a concept appears in; inf if it has no known chunk."""
    chunk_position = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks)}
    positions = {}
    for concept in concepts:
        source_positions = [
            chunk_position[source["chunk_id"]]
            for source in concept.get("sources", [])
            if source.get("chunk_id") in chunk_position
        ]
        positions[concept["id"]] = min(source_positions) if source_positions else float("inf")
    return positions


def _same_chunk_pairs(concepts: list) -> set:
    chunk_to_concepts = {}
    for concept in concepts:
        for source in concept.get("sources", []):
            if source.get("chunk_id"):
                chunk_to_concepts.setdefault(source["chunk_id"], []).append(concept["id"])

    pairs = set()
    for concept_ids in chunk_to_concepts.values():
        for i in range(len(concept_ids)):
            for j in range(i + 1, len(concept_ids)):
                pairs.add((concept_ids[i], concept_ids[j]))
    return pairs


def _name_in_definition(concepts: list) -> set:
    """(source, target) where a name or alias of source appears in target's description."""
    candidates = set()
    for source in concepts:
        source_terms = _terms(source)
        for target in concepts:
            if source["id"] == target["id"]:
                continue
            description = _normalise(target.get("description", ""))
            for term in source_terms:
                if term and re.search(rf"\b{re.escape(term)}\b", description):
                    candidates.add((source["id"], target["id"]))
                    break
    return candidates


def _embedding_pairs(concepts: list, threshold: float = 0.55) -> set:
    from sentence_transformers import SentenceTransformer  # heavy; not installed in CI

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [f"{concept['name']}. {concept.get('description', '')}" for concept in concepts]
    embeddings = model.encode(texts, normalize_embeddings=True)
    similarities = np.matmul(embeddings, embeddings.T)

    pairs = set()
    for i in range(len(concepts)):
        for j in range(i + 1, len(concepts)):
            if similarities[i][j] >= threshold:
                pairs.add((concepts[i]["id"], concepts[j]["id"]))
    return pairs


def generate_candidates(concepts, chunks: list, embedding_threshold: float = 0.55) -> list:
    if isinstance(concepts, dict):
        concepts = concepts["concepts"]

    positions = _course_position(concepts, chunks)

    # Content signals per unordered pair; the direction is decided afterwards.
    signals: dict[tuple, set] = {}

    def add_signal(pair, reason: str) -> None:
        a, b = pair
        if a != b:
            signals.setdefault(tuple(sorted((a, b))), set()).add(reason)

    for pair in _same_chunk_pairs(concepts):
        add_signal(pair, "same_chunk")
    for pair in _name_in_definition(concepts):
        add_signal(pair, "name_in_definition")
    for pair in _embedding_pairs(concepts, embedding_threshold):
        add_signal(pair, "embedding_similarity")

    candidates = []
    for (a, b), reasons in sorted(signals.items()):
        if positions[a] == positions[b]:
            candidates.append(Candidate(source=a, target=b, reasons=sorted(reasons), tied=True))
            continue
        source, target = (a, b) if positions[a] < positions[b] else (b, a)
        # course order is only a weak extra reason, attached to a pair that already has one
        candidates.append(
            Candidate(source=source, target=target, reasons=sorted(reasons | {"course_order"}))
        )
    return candidates


def candidate_stats(candidates: list, n_concepts: int) -> dict:
    """How many of the n(n-1)/2 unordered pairs became candidates."""
    total = n_concepts * (n_concepts - 1) // 2
    return {
        "concepts": n_concepts,
        "unordered_pairs": total,
        "candidates": len(candidates),
        "tied": sum(candidate.tied for candidate in candidates),
        "llm_calls": len(candidates) + sum(candidate.tied for candidate in candidates),
    }
