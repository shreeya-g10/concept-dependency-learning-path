from dataclasses import dataclass
import re

import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass
class Candidate:
    source: str
    target: str
    reasons: list


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _terms(concept: dict) -> list:
    return [
        _normalise(concept["name"]),
        *[_normalise(alias) for alias in concept.get("aliases", [])],
    ]


def _course_position(
    concepts: list,
    chunks: list,
) -> dict:
    chunk_position = {
        chunk["chunk_id"]: index
        for index, chunk in enumerate(chunks)
    }

    positions = {}

    for concept in concepts:
        source_positions = [
            chunk_position[source["chunk_id"]]
            for source in concept.get("sources", [])
            if source["chunk_id"] in chunk_position
        ]

        positions[concept["id"]] = (
            min(source_positions)
            if source_positions
            else float("inf")
        )

    return positions


def _same_chunk_pairs(
    concepts: list,
) -> set:
    chunk_to_concepts = {}

    for concept in concepts:
        for source in concept.get("sources", []):
            chunk_to_concepts.setdefault(
                source["chunk_id"],
                [],
            ).append(concept["id"])

    pairs = set()

    for concept_ids in chunk_to_concepts.values():
        for i in range(len(concept_ids)):
            for j in range(i + 1, len(concept_ids)):
                pairs.add(
                    (concept_ids[i], concept_ids[j])
                )

    return pairs


def _name_in_definition(
    concepts: list,
) -> set:
    candidates = set()

    for source in concepts:
        source_terms = _terms(source)

        for target in concepts:
            if source["id"] == target["id"]:
                continue

            description = _normalise(
                target.get("description", "")
            )

            for term in source_terms:
                if term and re.search(
                    rf"\b{re.escape(term)}\b",
                    description,
                ):
                    candidates.add(
                        (source["id"], target["id"])
                    )
                    break

    return candidates


def _embedding_pairs(
    concepts: list,
    threshold: float = 0.55,
) -> set:
    model = SentenceTransformer(
        "all-MiniLM-L6-v2"
    )

    texts = [
        f"{concept['name']}. {concept.get('description', '')}"
        for concept in concepts
    ]

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    similarities = np.matmul(
        embeddings,
        embeddings.T,
    )

    pairs = set()

    for i in range(len(concepts)):
        for j in range(i + 1, len(concepts)):
            if similarities[i][j] >= threshold:
                pairs.add(
                    (
                        concepts[i]["id"],
                        concepts[j]["id"],
                    )
                )

    return pairs


def generate_candidates(
    concepts,
    chunks: list,
    embedding_threshold: float = 0.55,
) -> list:
    if isinstance(concepts, dict):
        concepts = concepts["concepts"]

    positions = _course_position(
        concepts,
        chunks,
    )

    signals = {}

    def add_signal(
        pair,
        reason: str,
    ) -> None:
        source, target = pair

        if source == target:
            return

        if positions[source] <= positions[target]:
            oriented = (source, target)
        else:
            oriented = (target, source)

        signals.setdefault(
            oriented,
            set(),
        ).add(reason)

    for pair in _same_chunk_pairs(concepts):
        add_signal(
            pair,
            "same_chunk",
        )

    for pair in _name_in_definition(concepts):
        add_signal(
            pair,
            "name_in_definition",
        )

    for pair in _embedding_pairs(
        concepts,
        embedding_threshold,
    ):
        add_signal(
            pair,
            "embedding_similarity",
        )

    for source in concepts:
        for target in concepts:
            if source["id"] == target["id"]:
                continue

            if positions[source["id"]] < positions[target["id"]]:
                add_signal(
                    (
                        source["id"],
                        target["id"],
                    ),
                    "course_order",
                )

    return [
        Candidate(
            source=source,
            target=target,
            reasons=sorted(reasons),
        )
        for (source, target), reasons in sorted(
            signals.items()
        )
    ]