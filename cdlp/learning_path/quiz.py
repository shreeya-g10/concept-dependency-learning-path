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
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl, write_json
from cdlp.shared.llm import chat_json

logger = logging.getLogger(__name__)

PROMPT_VERSION = "quiz_v2"
CHECK_PROMPT_VERSION = "quiz_check_v1"
CHECK_ITEMS = True  # a second model must confirm every item (quiz_v2)
N_QUESTIONS = 4
MIN_QUOTE_CHARS = 20
TEMPERATURE = 0.0
MAX_CHUNKS = 3  # evidence chunks shown per concept
MAX_CHUNK_CHARS = 1200  # each chunk is cut to this length in the prompt
MIN_OPTIONS, MAX_OPTIONS = 2, 6
SCHEMA_VERSION = "1.9"

# A student never sees the excerpts, so a question must not lean on them.
LEAKED_WORDING = re.compile(
    r"course evidence|the evidence|excerpt|according to|as (described|mentioned|stated)"
    r"|in the (text|course|material|passage|lecture)|provided (text|evidence)"
    r"|(all|none) of the above",
    re.IGNORECASE,
)


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


# ---- quiz_v2: focused excerpts, and checks on every item -------------------------


def _name_patterns(concept: dict) -> list[re.Pattern]:
    names = [concept.get("name", ""), *concept.get("aliases", [])]
    return [re.compile(rf"\b{re.escape(n.strip())}", re.IGNORECASE) for n in names if n.strip()]


def focused_chunks(concept: dict, chunks: list[dict], k: int = MAX_CHUNKS) -> list[dict]:
    """The chunks most about this concept: heading matches, then most mentions.

    A chunk that only mentions the concept in passing is what produced questions about
    the wrong topic under quiz_v1.
    """
    patterns = _name_patterns(concept)
    cited = {s.get("chunk_id") for s in concept.get("sources", [])}
    scored = []
    for position, chunk in enumerate(chunks):
        mentions = sum(len(p.findall(chunk.get("text", ""))) for p in patterns)
        in_heading = any(p.search(chunk.get("heading", "")) for p in patterns)
        if mentions or in_heading or chunk.get("chunk_id") in cited:
            score = 5 * in_heading + mentions + (chunk.get("chunk_id") in cited)
            scored.append((-score, position, chunk))
    return [chunk for _, _, chunk in sorted(scored, key=lambda x: x[:2])[:k]]


def v2_problem(raw: dict, concept: dict, evidence: list[dict]) -> str | None:
    """Why a structurally valid quiz_v2 item must be dropped, or None. No LLM involved."""
    text = " ".join([raw.get("question", ""), *raw.get("options", [])])
    if LEAKED_WORDING.search(text):
        return "mentions_the_source"
    asked = f"{raw.get('question', '')} {raw.get('answer') or raw.get('correct_answer') or ''}"
    if not any(p.search(asked) for p in _name_patterns(concept)):
        return "not_about_topic"
    quote = raw.get("source_quote")
    if not isinstance(quote, str) or len(_norm(quote)) < MIN_QUOTE_CHARS:
        return "no_source_quote"
    if not quote_chunk(quote, evidence):
        return "quote_not_in_book"
    return None


def quote_chunk(quote: str, evidence: list[dict]) -> dict | None:
    """The excerpt that really contains the quote: an invented quote finds none."""
    wanted = _norm(quote)
    return next((c for c in evidence if wanted in _norm(c.get("text", ""))), None)


def check_item(
    item: dict, concept: dict, excerpt: str, template: str, model: str | None
) -> str | None:
    """Ask a second model, which never saw the answer. Returns why it failed, or None."""
    options = sorted(item["options"], key=_norm)  # the position must not hint at the answer
    letters = "ABCDEF"
    prompt = template.format(
        concept_name=concept.get("name", concept["id"]),
        excerpt=excerpt[:MAX_CHUNK_CHARS],
        question=item["question"],
        options="\n".join(f"{letters[i]}. {o}" for i, o in enumerate(options)),
    )
    try:
        reply = chat_json(
            prompt, model=model, temperature=TEMPERATURE, prompt_version=CHECK_PROMPT_VERSION
        )
    except json.JSONDecodeError:
        return "check_reply_not_json"
    if not isinstance(reply, dict):
        return "check_reply_not_json"
    if reply.get("about_topic") is not True:
        return "check_off_topic"
    if reply.get("only_one_correct") is not True:
        return "check_not_one_answer"
    letter = str(reply.get("correct_letter", "")).strip().upper()[:1]
    position = letters.find(letter) if letter else -1
    if position < 0 or position >= len(options) or options[position] != item["answer"]:
        return "check_disagrees"
    return None


# ---- generation ---------------------------------------------------------------


def generate_quiz_items(
    concepts_data: dict,
    chunks: list[dict],
    *,
    course_id: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    limit: int | None = None,
    check: bool | None = None,
    check_model: str | None = None,
) -> dict[str, Any]:
    """quiz_items.json for any course: one LLM call per concept that has chunks.

    With quiz_v2 each item must also carry a word-for-word quote from the book, and a
    second model, shown only the excerpt, must reach the same answer. Items that fail are
    dropped and counted, so a topic can end up with no questions: it is then not ready.
    """
    prompt_version = prompt_version or PROMPT_VERSION
    check = CHECK_ITEMS if check is None else check
    is_v2 = prompt_version != "quiz_v1"
    check_model = check_model or os.getenv("LLM_VALIDATOR_MODEL") or None
    template = load_prompt(prompt_version)
    concepts = concepts_data["concepts"][:limit] if limit else concepts_data["concepts"]
    skipped: Counter = Counter()
    no_chunks, items = [], []
    to_check: list[tuple[dict, dict, str]] = []
    for concept in concepts:
        evidence = focused_chunks(concept, chunks) if is_v2 else concept_chunks(concept, chunks)
        if not evidence:
            no_chunks.append(concept["id"])
            continue
        try:
            reply = chat_json(
                build_prompt(concept, evidence, template)
                if not is_v2
                else template.format(
                    concept_id=concept["id"],
                    concept_name=concept.get("name", concept["id"]),
                    concept_description=concept.get("description", "") or "(none)",
                    evidence=format_evidence(evidence),
                    n_questions=N_QUESTIONS,
                ),
                model=model,
                temperature=TEMPERATURE,
                prompt_version=prompt_version,
            )
        except json.JSONDecodeError:
            skipped["reply_not_json"] += 1
            logger.warning("quiz: reply for %s was not JSON; no items", concept["id"])
            continue
        raw = reply.get("items") if isinstance(reply, dict) else None
        if not is_v2:
            items += clean_and_filter_quiz_items(
                raw, concept["id"], [c["chunk_id"] for c in evidence], skipped
            )
            continue
        if not isinstance(raw, list):
            skipped["no_items_list"] += 1
            continue
        number = 0
        for one in raw:
            problem = item_problem(one) or v2_problem(one, concept, evidence)
            if problem:
                skipped[problem] += 1
                continue
            number += 1
            source = quote_chunk(one["source_quote"], evidence)
            item = clean_item(
                {**one, "evidence_chunk_ids": [source["chunk_id"]]},
                concept["id"],
                f"q_{concept['id']}_{number}",
                [source["chunk_id"]],
            )
            item["source_quote"] = " ".join(one["source_quote"].split())
            items.append(item)
            to_check.append((item, concept, source.get("text", "")))
    checked = 0
    if is_v2 and check:
        # Second pass, so the two models are not swapped in and out of memory per concept.
        check_template = load_prompt(CHECK_PROMPT_VERSION)
        for item, concept, excerpt in to_check:
            checked += 1
            problem = check_item(item, concept, excerpt, check_template, check_model)
            if problem:
                skipped[problem] += 1
                items.remove(item)
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
            "check_model": (check_model or llm.DEFAULT_MODEL) if is_v2 and check else None,
            "check_prompt_version": CHECK_PROMPT_VERSION if is_v2 and check else None,
            "items_checked": checked,
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
    parser.add_argument("--prompt-version", help=f"default: {PROMPT_VERSION}")
    parser.add_argument("--no-check", action="store_true", help="skip the second-model check")
    parser.add_argument(
        "--only-graph",
        type=Path,
        help="only concepts on ACCEPT edges of this validated_graph.json (fewer LLM calls)",
    )
    args = parser.parse_args(argv)
    concepts_data = read_json(args.concepts)
    if args.only_graph:
        accepted = {
            end
            for edge in read_json(args.only_graph)["edges"]
            if edge["decision"] == "ACCEPT"
            for end in (edge["source"], edge["target"])
        }
        concepts_data["concepts"] = [c for c in concepts_data["concepts"] if c["id"] in accepted]
    quiz = generate_quiz_items(
        concepts_data,
        read_jsonl(args.chunks),
        course_id=args.course_id,
        model=args.model,
        limit=args.limit,
        prompt_version=args.prompt_version,
        check=False if args.no_check else None,
    )
    write_json(args.out, quiz)
    g = quiz["generation"]
    print(
        f"quiz: {len(quiz['items'])} items for {g['concepts']} concepts -> {args.out}; "
        f"dropped {sum(g['skipped'].values())} items {g['skipped']}, "
        f"{len(g['concepts_without_chunks'])} concepts had no chunks"
    )


if __name__ == "__main__":
    main()
