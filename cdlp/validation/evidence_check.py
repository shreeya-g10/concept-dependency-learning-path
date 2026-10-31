"""Evidence check: does the course material support learning A before B?

For each relationship A -> B we collect the chunks discovery cited as evidence plus
the top-k chunks retrieved by embedding similarity, then ask the validator model
(LLM_VALIDATOR_MODEL, a different model from discovery) to grade the support as
strong / medium / weak / none and quote the text it relied on.

Quotes are kept only if they appear verbatim in the chunk they cite, so every quote
shown to a user is traceable to a doc and page. A strong or medium grade with no
verifiable quote is capped at weak.

    python -m cdlp.validation.evidence_check --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --chunks outputs/chunks.jsonl \
        --out outputs/evidence_check.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from cdlp.shared.io import read_json, read_jsonl
from cdlp.shared.llm import chat_json

load_dotenv()

PROMPT_VERSION = "evidence_v1"
PROMPT_FILE = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt"
LEVELS = ("strong", "medium", "weak", "none")
TEMPERATURE = 0.0
DEFAULT_K = 3

Embedder = Callable[[list[str]], list[list[float]]]


def sentence_transformer_embedder(model_name: str | None = None) -> Embedder:
    """Embed with sentence-transformers (EMBEDDING_MODEL in .env). Imported lazily
    so tests and the light CI install don't need the model."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    return lambda texts: model.encode(texts, normalize_embeddings=True).tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class ChunkIndex:
    """Embeds every chunk once; exact cosine search is enough at course scale."""

    def __init__(self, chunks: list[dict], embed: Embedder):
        self.chunks = chunks
        self.by_id = {c["chunk_id"]: c for c in chunks}
        self.embed = embed
        self.vectors = embed([_chunk_text(c) for c in chunks]) if chunks else []

    def search(self, query: str, k: int) -> list[dict]:
        if not self.chunks or k <= 0:
            return []
        q = self.embed([query])[0]
        ranked = sorted(
            zip(self.chunks, self.vectors, strict=True),
            key=lambda cv: _cosine(q, cv[1]),
            reverse=True,
        )
        return [c for c, _ in ranked[:k]]


def _chunk_text(chunk: dict) -> str:
    heading = chunk.get("heading") or ""
    return f"{heading}. {chunk['text']}" if heading else chunk["text"]


def _describe(concept: dict) -> tuple[str, str]:
    aliases = ", ".join(concept.get("aliases") or []) or "no aliases"
    return concept["name"], aliases


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def gather_chunks(relationship: dict, concepts: dict, index: ChunkIndex, k: int) -> list[dict]:
    """Evidence chunks cited by discovery first, then the top-k retrieved, without duplicates."""
    picked: dict[str, dict] = {}
    for ev in relationship.get("evidence", []):
        chunk = index.by_id.get(ev.get("chunk_id"))
        if chunk:
            picked[chunk["chunk_id"]] = chunk
    src, tgt = concepts[relationship["source"]], concepts[relationship["target"]]
    query = (
        f"{src['name']} {tgt['name']}. {src.get('description', '')} {tgt.get('description', '')}"
    )
    for chunk in index.search(query, k):
        picked.setdefault(chunk["chunk_id"], chunk)
    return list(picked.values())


def build_prompt(relationship: dict, concepts: dict, chunks: list[dict]) -> str:
    src_name, src_aliases = _describe(concepts[relationship["source"]])
    tgt_name, tgt_aliases = _describe(concepts[relationship["target"]])
    excerpts = "\n".join(
        f'[{c["chunk_id"]}] {c["doc"]} p.{c["page"]}: "{_chunk_text(c)}"' for c in chunks
    )
    replacements = {
        "{source_name}": src_name,
        "{source_aliases}": src_aliases,
        "{target_name}": tgt_name,
        "{target_aliases}": tgt_aliases,
        "{chunks}": excerpts or "(no excerpts found)",
    }
    prompt = PROMPT_FILE.read_text()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def verify_quotes(raw_quotes: object, chunks: list[dict]) -> list[dict]:
    """Keep only quotes that occur verbatim (ignoring case/whitespace) in the cited chunk."""
    by_id = {c["chunk_id"]: c for c in chunks}
    verified, seen = [], set()
    for q in raw_quotes if isinstance(raw_quotes, list) else []:
        if not isinstance(q, dict):
            continue
        chunk, text = by_id.get(q.get("chunk_id")), str(q.get("quote", "")).strip()
        if not chunk or not text or _normalise(text) not in _normalise(_chunk_text(chunk)):
            continue
        if (chunk["chunk_id"], _normalise(text)) in seen:
            continue
        seen.add((chunk["chunk_id"], _normalise(text)))
        verified.append(
            {
                "chunk_id": chunk["chunk_id"],
                "doc": chunk["doc"],
                "page": chunk["page"],
                "quote": text,
            }
        )
    return verified


def check_relationship(
    relationship: dict, concepts: dict, index: ChunkIndex, *, k: int = DEFAULT_K, model: str
) -> dict:
    chunks = gather_chunks(relationship, concepts, index, k)
    response = chat_json(
        build_prompt(relationship, concepts, chunks),
        system="You are a careful course-material reviewer. Reply in JSON only.",
        model=model,
        temperature=TEMPERATURE,
        prompt_version=PROMPT_VERSION,
    )
    support = str(response.get("support", "")).strip().lower()
    support = support if support in LEVELS else "none"
    quotes = verify_quotes(response.get("quotes"), chunks) if support != "none" else []
    if support in ("strong", "medium") and not quotes:
        support = "weak"
    return {
        "relationship_id": relationship["id"],
        "source": relationship["source"],
        "target": relationship["target"],
        "evidence": support,
        "quotes": quotes,
        "rationale": str(response.get("rationale", "")),
        "retrieved_chunk_ids": [c["chunk_id"] for c in chunks],
    }


def run(
    relationships: dict,
    concepts: dict,
    chunks: list[dict],
    *,
    k: int = DEFAULT_K,
    model: str | None = None,
    embed: Embedder | None = None,
) -> dict:
    model = model or os.getenv("LLM_VALIDATOR_MODEL", "llama3.1:8b")
    concept_map = {c["id"]: c for c in concepts["concepts"]}
    index = ChunkIndex(chunks, embed or sentence_transformer_embedder())
    return {
        "course_id": relationships["course_id"],
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "temperature": TEMPERATURE,
        "k": k,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        "results": [
            check_relationship(r, concept_map, index, k=k, model=model)
            for r in relationships["relationships"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    args = parser.parse_args()

    result = run(
        read_json(args.relationships),
        read_json(args.concepts),
        read_jsonl(args.chunks),
        k=args.k,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
