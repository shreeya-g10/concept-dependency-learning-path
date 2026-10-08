from pathlib import Path

from cdlp.shared.llm import chat_json


def load_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompts" / "discover_v1.txt"
    return prompt_path.read_text()


def discover_relationship(
    source: dict,
    target: dict,
    evidence: list[dict],
    candidate_reasons: list[str],
) -> dict:
    prompt_template = load_prompt()

    evidence_text = "\n".join(
        f"Chunk ID: {item['chunk_id']}\n{item['text']}"
        for item in evidence
    )

    prompt = prompt_template.format(
        source_id=source["id"],
        source_name=source["name"],
        source_description=source.get("description", ""),
        target_id=target["id"],
        target_name=target["name"],
        target_description=target.get("description", ""),
        candidate_reasons=", ".join(candidate_reasons),
        evidence=evidence_text,
    )

    result = chat_json(
        prompt,
        prompt_version="discover_v1",
        temperature=0.0,
    )

    result["source"] = source["id"]
    result["target"] = target["id"]

    return result


def _remove_transitive_relationships(
    relationships: list[dict],
) -> list[dict]:
    direct_edges = {
        (
            relationship["source"],
            relationship["target"],
        )
        for relationship in relationships
        if relationship.get("relationship") == "DIRECT"
    }

    transitive_edges = set()

    for source, target in direct_edges:
        for middle_source, middle_target in direct_edges:
            if middle_source != target:
                continue

            if source == middle_target:
                continue

            if (source, middle_target) in direct_edges:
                transitive_edges.add(
                    (source, middle_target)
                )

    filtered = []

    for relationship in relationships:
        pair = (
            relationship["source"],
            relationship["target"],
        )

        if pair in transitive_edges:
            relationship = dict(relationship)
            relationship["relationship"] = "NONE"
            relationship["strength"] = "NONE"

        filtered.append(relationship)

    return filtered


def discover_candidates(
    candidates: list,
    concepts: list[dict],
    chunks: list[dict],
) -> list[dict]:
    concept_map = {
        concept["id"]: concept
        for concept in concepts
    }

    chunk_map = {
        chunk["chunk_id"]: chunk
        for chunk in chunks
    }

    relationships = []

    for candidate in candidates:
        source = concept_map[candidate.source]
        target = concept_map[candidate.target]

        evidence = []

        for concept in (source, target):
            for source_info in concept.get("sources", []):
                chunk_id = source_info["chunk_id"]

                if chunk_id in chunk_map:
                    chunk = chunk_map[chunk_id]

                    if chunk not in evidence:
                        evidence.append(chunk)

        result = discover_relationship(
            source,
            target,
            evidence,
            candidate.reasons,
        )

        relationships.append(result)

    return _remove_transitive_relationships(
        relationships
    )


def build_contract_relationships(
    relationships: list[dict],
    concepts: list[dict],
    chunks: list[dict],
) -> list[dict]:
    chunk_map = {
        chunk["chunk_id"]: chunk
        for chunk in chunks
    }

    contract_relationships = []

    for index, relationship in enumerate(
        relationships,
        start=1,
    ):
        if relationship.get("relationship") != "DIRECT":
            continue

        strength = relationship.get(
            "strength",
            "",
        ).lower()

        if strength not in {"hard", "soft"}:
            continue

        confidence = relationship.get("confidence")

        if isinstance(confidence, str):
            confidence_map = {
                "HIGH": 0.90,
                "MEDIUM": 0.70,
                "LOW": 0.50,
            }

            confidence = confidence_map.get(
                confidence.upper(),
                0.50,
            )

        if confidence is None:
            confidence = 0.50

        evidence_items = []

        for chunk_id in relationship.get(
            "evidence_chunk_ids",
            [],
        ):
            chunk = chunk_map.get(chunk_id)

            if chunk is None:
                continue

            evidence_items.append(
                {
                    "chunk_id": chunk_id,
                    "doc": chunk.get("doc", ""),
                    "page": chunk.get("page", 0),
                    "quote": chunk.get("text", "")[:200],
                }
            )

        contract_relationships.append(
            {
                "id": f"r{index}",
                "source": relationship["source"],
                "target": relationship["target"],
                "type": "PREREQUISITE",
                "strength": strength,
                "confidence": float(confidence),
                "evidence": evidence_items,
                "method": "llm_discovery_v1",
            }
        )

    return contract_relationships