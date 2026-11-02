"""Diagnostic quiz items generated from any course's material.

    python -m cdlp.learning_path.quiz --concepts outputs/<course>/concepts.json \
        --chunks outputs/<course>/chunks.jsonl --out outputs/<course>/quiz_items.json \
        [--course-id ml101] [--limit 3] [--model qwen2.5:7b-instruct]

For every concept, the LLM (prompts/quiz_v1.txt) writes multiple-choice items from
that concept's own chunks: the chunks its `sources` cite, then chunks that mention
its name or an alias, at most MAX_CHUNKS. A concept with no chunk gets no items
(nothing to ground them in). Every item is checked before it is kept:

- a non-empty question and 2-6 distinct, non-empty options;
- the answer matches exactly one option (case and surrounding spaces ignored);
  the stored answer is that option's text, so `answer in options` always holds;
- `concept_id` is the concept being generated, whatever the model wrote;
- `chunk_id` is the first cited chunk id that was actually supplied as evidence
  (an invented id is dropped, never kept).

Bad items are skipped and counted per reason in the file's `generation` block,
together with the model, prompt version, temperature and seed. All LLM calls go
through cdlp.shared.llm (cached). Initial code: Vaidehi (moved from cdlp/discovery/).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl, write_json
from cdlp.shared.llm import chat_json

logger = logging.getLogger(__name__)

PROMPT_VERSION = "quiz_v1"
TEMPERATURE = 0.0
MAX_CHUNKS = 3  # evidence chunks shown per concept
MAX_CHUNK_CHARS = 1200  # each chunk is cut to this length in the prompt
MIN_OPTIONS, MAX_OPTIONS = 2, 6
SCHEMA_VERSION = "1.6"


def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (Path(__file__).parent / "prompts" / f"{version}.txt").read_text(encoding="utf-8")


# ---- validation ---------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def item_problem(item: Any) -> str | None:
    """Why an item must be skipped, or None if it is usable. Never raises."""
    if not isinstance(item, dict):
        return "not_an_object"
    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        return "no_question"
    options = item.get("options")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        return "bad_options"
    cleaned = [o.strip() for o in options]
    if any(not o for o in cleaned) or not MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS:
        return "bad_options"
    if len({_norm(o) for o in cleaned}) != len(cleaned):
        return "duplicate_options"
    answer = item.get("answer") or item.get("correct_answer")
    if not isinstance(answer, str) or not answer.strip():
        return "no_answer"
    if sum(_norm(o) == _norm(answer) for o in cleaned) != 1:
        return "answer_not_in_options"
    return None


def validate_quiz_item(item: Any) -> bool:
    """True when the item can be kept: see item_problem()."""
    return item_problem(item) is None


def clean_item(raw: dict, concept_id: str, item_id: str, allowed_chunks: list[str]) -> dict:
    """Contract-shaped copy of a valid raw item (call validate_quiz_item first)."""
    options = [o.strip() for o in raw["options"]]
    answer = _norm(raw.get("answer") or raw.get("correct_answer"))
    item = {
        "id": item_id,
        "concept_id": concept_id,
        "question": raw["question"].strip(),
        "options": options,
        "answer": next(o for o in options if _norm(o) == answer),
    }
    cited = raw.get("evidence_chunk_ids") or ([raw["chunk_id"]] if raw.get("chunk_id") else [])
    if isinstance(cited, list):
        chunk = next((c for c in cited if isinstance(c, str) and c in allowed_chunks), None)
        if chunk:
            item["chunk_id"] = chunk
    return item


def clean_and_filter_quiz_items(
    raw_items: Any,
    default_concept_id: str = "",
    allowed_chunks: list[str] | None = None,
    skipped: Counter | None = None,
) -> list[dict[str, Any]]:
    """Keep the valid items, skip the rest (counted in `skipped` by reason).

    With `allowed_chunks` None, any string chunk id the item carries is kept.
    """
    if not isinstance(raw_items, list):
        if skipped is not None:
            skipped["no_items_list"] += 1
        return []
    kept = []
    for raw in raw_items:
        problem = item_problem(raw)
        if problem:
            if skipped is not None:
                skipped[problem] += 1
            continue
        concept_id = default_concept_id or str(raw.get("concept_id") or "concept")
        item_id = str(raw.get("id") or f"q_{concept_id}_{len(kept) + 1}")
        allowed = allowed_chunks
        if allowed is None:
            allowed = [c for c in [raw.get("chunk_id"), *(raw.get("evidence_chunk_ids") or [])]]
            allowed = [c for c in allowed if isinstance(c, str)]
        kept.append(clean_item(raw, concept_id, item_id, allowed))
    return kept


# ---- evidence -----------------------------------------------------------------


def concept_chunks(concept: dict, chunks: list[dict], k: int = MAX_CHUNKS) -> list[dict]:
    """The concept's own chunks: cited sources first, then chunks naming it, in course order."""
    by_id = {c["chunk_id"]: c for c in chunks}
    picked = []
    for source in concept.get("sources", []):
        chunk = by_id.get(source.get("chunk_id"))
        if chunk and chunk not in picked:
            picked.append(chunk)
    names = [concept.get("name", ""), *concept.get("aliases", [])]
    patterns = [re.compile(rf"\b{re.escape(n)}", re.IGNORECASE) for n in names if n.strip()]
    for chunk in chunks:
        if len(picked) >= k:
            break
        text = f"{chunk.get('heading', '')} {chunk.get('text', '')}"
        if chunk not in picked and any(p.search(text) for p in patterns):
            picked.append(chunk)
    return picked[:k]


def format_evidence(chunks: list[dict]) -> str:
    lines = []
    for c in chunks:
        where = f"{c.get('doc', '?')} p.{c.get('page', '?')}"
        lines.append(f"[{c['chunk_id']}] ({where}) {c.get('text', '')[:MAX_CHUNK_CHARS]}")
    return "\n".join(lines)


def build_prompt(concept: dict, chunks: list[dict], template: str) -> str:
    return template.format(
        concept_id=concept["id"],
        concept_name=concept.get("name", concept["id"]),
        concept_description=concept.get("description", "") or "(none)",
        evidence=format_evidence(chunks),
    )


# ---- generation ---------------------------------------------------------------


def generate_quiz_items(
    concepts_data: dict,
    chunks: list[dict],
    *,
    course_id: str | None = None,
    model: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    limit: int | None = None,
) -> dict[str, Any]:
    """quiz_items.json for any course: one LLM call per concept that has chunks."""
    template = load_prompt(prompt_version)
    concepts = concepts_data["concepts"][:limit] if limit else concepts_data["concepts"]
    skipped: Counter = Counter()
    no_chunks, items = [], []
    for concept in concepts:
        evidence = concept_chunks(concept, chunks)
        if not evidence:
            no_chunks.append(concept["id"])
            continue
        try:
            reply = chat_json(
                build_prompt(concept, evidence, template),
                model=model,
                temperature=TEMPERATURE,
                prompt_version=prompt_version,
            )
        except json.JSONDecodeError:
            skipped["reply_not_json"] += 1
            logger.warning("quiz: reply for %s was not JSON; no items", concept["id"])
            continue
        raw = reply.get("items") if isinstance(reply, dict) else None
        items += clean_and_filter_quiz_items(
            raw, concept["id"], [c["chunk_id"] for c in evidence], skipped
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": course_id or concepts_data["course_id"],
        "items": items,
        "generation": {
            "model": model or llm.DEFAULT_MODEL,
            "prompt_version": prompt_version,
            "temperature": TEMPERATURE,
            "seed": llm.DEFAULT_SEED,
            "max_chunks_per_concept": MAX_CHUNKS,
            "concepts": len(concepts),
            "concepts_without_chunks": no_chunks,
            "concepts_without_items": sorted(
                {c["id"] for c in concepts} - {i["concept_id"] for i in items} - set(no_chunks)
            ),
            "skipped": dict(sorted(skipped.items())),
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="quiz_items.json to write")
    parser.add_argument("--course-id", help="default: course_id in concepts.json")
    parser.add_argument("--model", help="default: LLM_MODEL from .env")
    parser.add_argument("--limit", type=int, help="only the first N concepts (cheap trial)")
    args = parser.parse_args(argv)
    quiz = generate_quiz_items(
        read_json(args.concepts),
        read_jsonl(args.chunks),
        course_id=args.course_id,
        model=args.model,
        limit=args.limit,
    )
    write_json(args.out, quiz)
    g = quiz["generation"]
    print(
        f"quiz: {len(quiz['items'])} items for {g['concepts']} concepts -> {args.out}; "
        f"skipped {sum(g['skipped'].values())} items, "
        f"{len(g['concepts_without_chunks'])} concepts had no chunks"
    )


if __name__ == "__main__":
    main()
