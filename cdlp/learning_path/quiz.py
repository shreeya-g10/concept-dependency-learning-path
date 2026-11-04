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

quiz_v2 adds a word-for-word quote, a second model (prompts/quiz_check_v2.txt) and one
retry per topic that ends up with too few items. The checks in quiz_check_v2 were designed
from real ds101 failures (tests/quiz_dev_examples.json). Those are development examples:
any accuracy figure for the checks must come from questions not used to design them.

quiz_v3 asks for one easy, one medium and one hard question per topic. Every draft passes the same
checks: none is loosened to keep hard questions, and generation reports the drop rate per level.
The model's difficulty is stored as an "ai_suggestion" until a teacher approves it. A topic left
missing a level also gets the one retry (prompts/quiz_retry_v2.txt), which says which level is
missing and why its drafts failed. It is still one retry per topic, under the same checks.
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

from cdlp.learning_path import quiz_check_v3
from cdlp.learning_path.quiz_check_v3 import _name_forms
from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl, write_json
from cdlp.shared.llm import chat_json
from cdlp.shared.validate import schema_for

logger = logging.getLogger(__name__)

PROMPT_VERSION = "quiz_v3"  # quiz_v2 is kept for the record
LEVELLED_PROMPTS = frozenset({"quiz_v3"})
LEVELS = ("easy", "medium", "hard")
N_LEVELLED_QUESTIONS = 3
CHECK_PROMPT_VERSION = "quiz_check_v2"  # quiz_check_v1 is kept for the record
# The checks as a whole. quiz_check_v3 is v2's prompt with no-LLM checks added (quiz_check_v3.py).
CHECK_VERSION = "quiz_check_v3"
OLD_CHECK_VERSION = "quiz_check_v2"
RETRY_PROMPT_VERSION = "quiz_retry_v1"
LEVELLED_RETRY_PROMPT_VERSION = "quiz_retry_v2"
CHECK_ITEMS = True  # a second model must confirm every item (quiz_v2)
N_QUESTIONS = 4
# Below this a topic gets one retry. One question cannot tell a slip from a real gap.
MIN_ITEMS_PER_TOPIC = 2
MAX_FAILURES_SHOWN = 8  # rejected questions listed in a retry prompt
# Questions this alike ask the same thing. Short answers such as "O(log n)" are not compared:
# two different questions can share one.
SAME_QUESTION_OVERLAP = 0.7
SAME_ANSWER_OVERLAP = 0.6
MIN_ANSWER_WORDS = 4
MIN_QUOTE_CHARS = 20
TEMPERATURE = 0.0
MAX_CHUNKS = 3  # evidence chunks shown per concept
MAX_CHUNK_CHARS = 1200  # each chunk is cut to this length in the prompt
MIN_OPTIONS, MAX_OPTIONS = 2, 6
SCHEMA_VERSION = "1.13"

# A student never sees the excerpts, so a question must not lean on them.
LEAKED_WORDING = re.compile(
    r"course evidence|the evidence|excerpt|according to|as (described|mentioned|stated)"
    r"|in the (text|course|material|passage|lecture)|provided (text|evidence)"
    r"|(all|none) of the above",
    re.IGNORECASE,
)


COMMON_WORDS = frozenset(
    "a an and are be by can could do does for from how in is it its of on or that the their "
    "they this to what when where which why will with would".split()
)

# What a retry prompt tells the model about each rejection reason.
FAILURE_ADVICE = {
    "reply_not_json": "The reply was not valid JSON.",
    "no_items_list": 'The reply had no "items" list.',
    "not_an_object": "An item was not a JSON object.",
    "no_question": "The question was empty.",
    "bad_options": "It did not have 2 to 6 non-empty options.",
    "duplicate_options": "Two options were the same.",
    "no_answer": 'It had no "correct_answer".',
    "answer_not_in_options": '"correct_answer" was not the full text of one option.',
    "mentions_the_source": "It mentioned the text or used a phrase such as 'all of the above'.",
    "not_about_topic": "Neither the question nor the answer named the topic.",
    "no_source_quote": '"source_quote" was missing or too short to prove anything.',
    "quote_not_in_book": '"source_quote" was not copied word for word from one excerpt.',
    "near_duplicate": "It asked the same thing as another question, or used the same quote.",
    "subject_not_in_source": "It named something the quote and its section never mention.",
    "answer_not_supported": "The quote did not state the correct answer in its own words.",
    "check_reply_not_json": "A checker could not judge it. Make it simpler and clearer.",
    "check_bad_verdicts": "A checker could not judge it. Make it simpler and clearer.",
    "check_off_topic": "A checker found that it was really about a different topic.",
    "check_none_true": "A checker, reading only the excerpt, found no option that was correct.",
    "check_several_true": "A checker found more than one correct option. Make the others false.",
    "check_disagrees": "A checker, reading only the excerpt, found a different correct option.",
    "check_quote_other_subject": "The question and the quote were about different things.",
    "check_quote_no_proof": "The quote did not prove the correct answer.",
}


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


def names_topic(text: str, concept: dict) -> bool:
    """Does the text name the concept, or an alias, as whole words?

    Spaces, hyphens, underscores and case are ignored, and plurals count, so "BinarySearchTrees"
    and "binary-search tree" both name "Binary Search Tree". A longer word does not: "ArrayQueue"
    does not name "Queue". A name with symbols ("C++") is matched as written.
    """
    words = [w.casefold() for w in re.findall(r"[^\W_]+", text)]
    for name in [concept.get("name", ""), *concept.get("aliases", [])]:
        squashed = re.sub(r"[\s_\-\u2010-\u2015]+", "", name).casefold()
        if not squashed:
            continue
        if not squashed.isalnum():
            if re.search(rf"(?<![^\W_]){re.escape(name.strip())}(?![^\W_])", text, re.IGNORECASE):
                return True
            continue
        forms = _name_forms(squashed)
        most_words = len(re.findall(r"[^\W_]+", name)) + 1
        for start in range(len(words)):
            for end in range(start + 1, min(start + most_words, len(words)) + 1):
                if "".join(words[start:end]) in forms:
                    return True
    return False


def v2_problem(raw: dict, concept: dict, evidence: list[dict]) -> str | None:
    """Why a structurally valid quiz_v2 item must be dropped, or None. No LLM involved."""
    text = " ".join([raw.get("question", ""), *raw.get("options", [])])
    if LEAKED_WORDING.search(text):
        return "mentions_the_source"
    asked = f"{raw.get('question', '')} {raw.get('answer') or raw.get('correct_answer') or ''}"
    if not names_topic(asked, concept):
        return "not_about_topic"
    quote = raw.get("source_quote")
    if not isinstance(quote, str) or len(_norm(quote)) < MIN_QUOTE_CHARS:
        return "no_source_quote"
    if not quote_chunk(quote, evidence):
        return "quote_not_in_book"
    return None


def v3_problem(raw: dict, topic: dict) -> tuple[str, str] | None:
    """(reason, detail) if a structurally valid item must be dropped under quiz_check_v3."""
    concept, evidence, v3 = topic["concept"], topic["evidence"], topic["v3"]
    text = " ".join([raw.get("question", ""), *raw.get("options", [])])
    if LEAKED_WORDING.search(text):
        return "mentions_the_source", ""
    answer = raw.get("answer") or raw.get("correct_answer") or ""
    if not names_topic(f"{raw.get('question', '')} {answer}", concept):
        return "not_about_topic", ""
    quote = raw.get("source_quote")
    if not isinstance(quote, str) or len(_norm(quote)) < MIN_QUOTE_CHARS:
        return "no_source_quote", ""
    chunk = quiz_check_v3.quote_chunk(quote, evidence)
    if not chunk:
        return "quote_not_in_book", ""
    missing = quiz_check_v3.missing_subject(
        raw["question"], quote, chunk.get("text", ""), v3["terms"], v3["concepts"]
    )
    if missing:
        return "subject_not_in_source", missing
    support = quiz_check_v3.answer_support(answer, quote, v3["cfg"], COMMON_WORDS)
    if support < v3["cfg"]["min_answer_support"]:
        return (
            "answer_not_supported",
            f"{support:.2f} of the answer's content words are in the quote",
        )
    return None


def v3_context(concepts: list[dict]) -> dict:
    """What v3_problem needs: the whole course's concepts, not only the ones being asked about."""
    return {
        "cfg": quiz_check_v3.load_config(),
        "terms": quiz_check_v3.concept_terms(concepts),
        "concepts": {c["id"]: c for c in concepts},
    }


def _content_words(text: str) -> set[str]:
    words = {w.casefold() for w in re.findall(r"[^\W_]+", text)} - COMMON_WORDS
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def near_duplicate(item: dict, others: list[dict]) -> bool:
    """Same quote, nearly the same question, or the same long answer as an item in others."""
    question, answer = _content_words(item["question"]), _content_words(item["answer"])
    for other in others:
        if _norm(item["source_quote"]) == _norm(other["source_quote"]):
            return True
        if _overlap(question, _content_words(other["question"])) >= SAME_QUESTION_OVERLAP:
            return True
        other_answer = _content_words(other["answer"])
        if min(len(answer), len(other_answer)) >= MIN_ANSWER_WORDS:
            if _overlap(answer, other_answer) >= SAME_ANSWER_OVERLAP:
                return True
    return False


def quote_chunk(quote: str, evidence: list[dict]) -> dict | None:
    """The excerpt that really contains the quote: an invented quote finds none."""
    wanted = _norm(quote)
    return next((c for c in evidence if wanted in _norm(c.get("text", ""))), None)


def _truth(value: Any) -> bool | None:
    """True or False from a checker's reply; None for anything else."""
    if isinstance(value, bool):
        return value
    return {"true": True, "false": False}.get(str(value).strip().casefold())


def check_item(
    item: dict,
    concept: dict,
    excerpt: str,
    template: str,
    model: str | None,
    record: dict | None = None,
) -> str | None:
    """Ask a second model, which is never told the answer. Returns why it failed, or None.

    The model judges each option true or false from the excerpt, says which option the quote
    proves and whether the question and quote share a subject. This code compares that with
    the answer, so the model cannot just agree with it. A reply that cannot be read fails.
    The reply's fields are copied into `record` when one is given.
    """
    options = sorted(item["options"], key=_norm)  # the position must not hint at the answer
    letters = "ABCDEF"[: len(options)]
    prompt = template.format(
        concept_name=concept.get("name", concept["id"]),
        excerpt=excerpt[:MAX_CHUNK_CHARS],
        question=item["question"],
        options="\n".join(f"{letter}. {o}" for letter, o in zip(letters, options, strict=True)),
        quote=item["source_quote"],
    )
    try:
        reply = chat_json(
            prompt, model=model, temperature=TEMPERATURE, prompt_version=CHECK_PROMPT_VERSION
        )
    except json.JSONDecodeError:
        return "check_reply_not_json"
    if not isinstance(reply, dict):
        return "check_reply_not_json"
    if record is not None:
        for field in ("verdicts", "quote_proves", "same_subject", "about_topic"):
            record[field] = reply.get(field)
    if _truth(reply.get("about_topic")) is not True:
        return "check_off_topic"
    raw_verdicts = reply.get("verdicts")
    if not isinstance(raw_verdicts, dict):
        return "check_bad_verdicts"
    verdicts = {str(k).strip().upper(): _truth(v) for k, v in raw_verdicts.items()}
    if set(verdicts) != set(letters) or None in verdicts.values():
        return "check_bad_verdicts"
    true_options = [letter for letter in letters if verdicts[letter]]
    if not true_options:
        return "check_none_true"
    if len(true_options) > 1:
        return "check_several_true"
    answer_letter = letters[options.index(item["answer"])]
    if true_options[0] != answer_letter:
        return "check_disagrees"
    if _truth(reply.get("same_subject")) is not True:
        return "check_quote_other_subject"
    if str(reply.get("quote_proves", "")).strip().upper() != answer_letter:
        return "check_quote_no_proof"
    return None


# ---- generation ---------------------------------------------------------------


def _v2_prompt(concept: dict, evidence: list[dict], template: str) -> str:
    return template.format(
        concept_id=concept["id"],
        concept_name=concept.get("name", concept["id"]),
        concept_description=concept.get("description", "") or "(none)",
        evidence=format_evidence(evidence),
        n_questions=N_QUESTIONS,
    )


def missing_levels(topic: dict) -> list[str]:
    """The levels this topic has no kept item for, in level order."""
    have = {item.get("difficulty") for item in topic["items"]}
    return [level for level in LEVELS if level not in have]


def _levelled_failures(topic: dict, missing: list[str]) -> list[str]:
    """Why drafts failed, the missing levels first so the limit never cuts them."""
    level_of = topic.get("failure_levels", {})
    rows = sorted(topic["failures"], key=lambda f: level_of.get(f[0]) not in missing)
    lines = []
    for question, reason in rows[:MAX_FAILURES_SHOWN]:
        advice = FAILURE_ADVICE.get(reason, "It failed a check.")
        level = level_of.get(question)
        tag = f"{level} question " if level in LEVELS else ""
        lines.append(f'- {tag}"{question}": {advice}' if question else f"- {advice}")
    failed = {level_of.get(question) for question, _ in topic["failures"]}
    lines += [f"- No {level} question was written." for level in missing if level not in failed]
    return lines


def _retry_prompt(topic: dict, template: str, retry_template: str) -> str:
    """The first prompt, plus why the drafts failed and which questions to leave alone."""
    accepted = [f"- {item['question']}" for item in topic["items"]]
    if topic.get("levelled"):
        missing = missing_levels(topic)
        return retry_template.format(
            base_prompt=_v2_prompt(topic["concept"], topic["evidence"], template),
            concept_name=topic["concept"].get("name", topic["concept"]["id"]),
            missing_levels=", ".join(missing),
            failures="\n".join(_levelled_failures(topic, missing)) or "(none listed)",
            accepted="\n".join(accepted) or "(none yet)",
            n_questions=len(missing) or N_LEVELLED_QUESTIONS,
        )
    failures = []
    for question, reason in topic["failures"][:MAX_FAILURES_SHOWN]:
        advice = FAILURE_ADVICE.get(reason, "It failed a check.")  # never crash a long run
        failures.append(f'- "{question}": {advice}' if question else f"- {advice}")
    return retry_template.format(
        base_prompt=_v2_prompt(topic["concept"], topic["evidence"], template),
        concept_name=topic["concept"].get("name", topic["concept"]["id"]),
        failures="\n".join(failures) or "(none listed)",
        accepted="\n".join(accepted) or "(none yet)",
        n_questions=N_QUESTIONS,
    )


def _ask_for_drafts(prompt: str, topic: dict, version: str, model: str | None, skipped) -> list:
    """The reply's items list. A bad reply is counted and remembered for the retry."""
    try:
        reply = chat_json(prompt, model=model, temperature=TEMPERATURE, prompt_version=version)
    except json.JSONDecodeError:
        skipped["reply_not_json"] += 1
        topic["failures"].append(("", "reply_not_json"))
        logger.warning("quiz: reply for %s was not JSON; no items", topic["concept"]["id"])
        return []
    raw = reply.get("items") if isinstance(reply, dict) else None
    if not isinstance(raw, list):
        skipped["no_items_list"] += 1
        topic["failures"].append(("", "no_items_list"))
        return []
    return raw


def _draft_level(raw: Any) -> str:
    """The level the model gave a draft, or "unlabelled". A label is never a reason to drop."""
    level = raw.get("difficulty") if isinstance(raw, dict) else None
    level = level.strip().casefold() if isinstance(level, str) else None
    return level if level in LEVELS else "unlabelled"


def drop_rate_by_level(topics: list[dict]) -> dict[str, dict]:
    """Drafts, kept items and the share dropped per level, over every attempt."""
    drafted: Counter = Counter()
    kept: Counter = Counter()
    for topic in topics:
        drafted.update(topic.get("drafted", Counter()))
        kept.update(item.get("difficulty", "unlabelled") for item in topic["items"])
    return {
        level: {
            "drafted": drafted[level],
            "kept": kept[level],
            "dropped": drafted[level] - kept[level],
            "drop_rate": (
                round((drafted[level] - kept[level]) / drafted[level], 4)
                if drafted[level]
                else None
            ),
        }
        for level in [*LEVELS, "unlabelled"]
    }


def _take_drafts(raw: list, topic: dict, skipped: Counter) -> list[dict]:
    """Run the no-LLM checks and add the drafts that pass to the topic. Returns those drafts."""
    concept, evidence = topic["concept"], topic["evidence"]
    new = []
    for one in raw:
        question = one.get("question") if isinstance(one, dict) else None
        if topic.get("levelled"):
            topic.setdefault("drafted", Counter())[_draft_level(one)] += 1
        detail = ""
        v3 = topic.get("v3")
        problem = item_problem(one)
        if not problem and v3:
            problem, detail = v3_problem(one, topic) or (None, "")
        elif not problem:
            problem = v2_problem(one, concept, evidence)
        if not problem:
            source = (quiz_check_v3.quote_chunk if v3 else quote_chunk)(
                one["source_quote"], evidence
            )
            item = clean_item(
                {**one, "evidence_chunk_ids": [source["chunk_id"]]},
                concept["id"],
                "",
                [source["chunk_id"]],
            )
            item["source_quote"] = " ".join(one["source_quote"].split())
            if topic.get("levelled") and _draft_level(one) in LEVELS:
                item["difficulty"] = _draft_level(one)
                item["difficulty_source"] = "ai_suggestion"
            if near_duplicate(item, topic["items"]):
                problem = "near_duplicate"
        if problem:
            skipped[problem] += 1
            topic["failures"].append((question if isinstance(question, str) else "", problem))
            if topic.get("levelled") and isinstance(question, str):
                topic.setdefault("failure_levels", {})[question] = _draft_level(one)
            topic.setdefault("dropped", []).append(
                {
                    "concept_id": concept["id"],
                    "question": question if isinstance(question, str) else "",
                    "reason": problem,
                    "detail": detail,
                }
            )
            continue
        topic["numbered"] += 1
        item["id"] = f"q_{concept['id']}_{topic['numbered']}"
        topic["items"].append(item)
        new.append(item)
        topic["excerpts"][item["id"]] = source.get("text", "")
    return new


def _check_drafts(new: list[dict], topic: dict, template: str, model: str | None, skipped) -> None:
    for item in new:
        excerpt = topic["excerpts"][item["id"]]
        reply: dict = {}
        problem = check_item(item, topic["concept"], excerpt, template, model, record=reply)
        if topic.get("v3"):
            item["second_model"] = reply  # kept for the record: a pass proves little on its own
        if problem:
            skipped[problem] += 1
            topic["failures"].append((item["question"], problem))
            if topic.get("levelled"):
                level = item.get("difficulty", "unlabelled")
                topic.setdefault("failure_levels", {})[item["question"]] = level
            topic["items"].remove(item)
            topic.setdefault("dropped", []).append(
                {
                    "concept_id": topic["concept"]["id"],
                    "question": item["question"],
                    "reason": problem,
                    "detail": "",
                    "second_model": reply,
                }
            )


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
    check_version: str = CHECK_VERSION,
    all_concepts: list[dict] | None = None,
) -> dict[str, Any]:
    """quiz_items.json for any course: one LLM call per concept that has chunks.

    With quiz_v2 each item must also carry a word-for-word quote from the book, and a
    second model, shown only the excerpt and the quote, must judge the item sound. Items that
    fail are dropped and counted. A topic left with fewer than MIN_ITEMS_PER_TOPIC, or under
    quiz_v3 missing a level, gets one
    retry that says why its drafts failed, and the new drafts pass the same checks. A topic
    can still end up with no questions: it is then not ready.

    all_concepts: the whole course, when concepts_data holds only some of it. quiz_check_v3 uses
    it to see which concepts a question names.
    """
    prompt_version = prompt_version or PROMPT_VERSION
    check = CHECK_ITEMS if check is None else check
    is_v2 = prompt_version != "quiz_v1"
    check_model = check_model or os.getenv("LLM_VALIDATOR_MODEL") or None
    template = load_prompt(prompt_version)
    use_v3 = is_v2 and check_version != OLD_CHECK_VERSION
    v3 = v3_context(all_concepts or concepts_data["concepts"]) if use_v3 else None
    concepts = concepts_data["concepts"][:limit] if limit else concepts_data["concepts"]
    skipped: Counter = Counter()
    no_chunks, items = [], []
    topics: list[dict] = []
    new_drafts: list[tuple[list[dict], dict]] = []
    for concept in concepts:
        evidence = focused_chunks(concept, chunks) if is_v2 else concept_chunks(concept, chunks)
        if not evidence:
            no_chunks.append(concept["id"])
            continue
        if is_v2:
            topic = {
                "concept": concept,
                "evidence": evidence,
                "items": [],
                "failures": [],
                "excerpts": {},
                "numbered": 0,
                "dropped": [],
            }
            if v3:
                topic["v3"] = v3
            if prompt_version in LEVELLED_PROMPTS:
                topic["levelled"] = True
            topics.append(topic)
            raw = _ask_for_drafts(
                _v2_prompt(concept, evidence, template), topic, prompt_version, model, skipped
            )
            new_drafts.append((_take_drafts(raw, topic, skipped), topic))
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
    checked = 0
    retried: list[str] = []
    retried_only_for_level: list[str] = []
    skipped_first_try: Counter = Counter()
    if is_v2:
        check_template = load_prompt(CHECK_PROMPT_VERSION) if check else ""

        def run_checks(batches: list[tuple[list[dict], dict]]) -> int:
            # Run after all the drafts, so the two models are not swapped per concept.
            count = 0
            if check:
                for new, topic in batches:
                    count += len(new)
                    _check_drafts(new, topic, check_template, check_model, skipped)
            return count

        checked += run_checks(new_drafts)
        skipped_first_try = Counter(skipped)
        retry_version = (
            LEVELLED_RETRY_PROMPT_VERSION
            if prompt_version in LEVELLED_PROMPTS
            else RETRY_PROMPT_VERSION
        )
        retry_template = load_prompt(retry_version)
        retry_batches = []
        for topic in topics:
            too_few = len(topic["items"]) < MIN_ITEMS_PER_TOPIC
            missing = bool(topic.get("levelled") and missing_levels(topic))
            if too_few or missing:
                retried.append(topic["concept"]["id"])
                if not too_few:
                    retried_only_for_level.append(topic["concept"]["id"])
                raw = _ask_for_drafts(
                    _retry_prompt(topic, template, retry_template),
                    topic,
                    retry_version,
                    model,
                    skipped,
                )
                retry_batches.append((_take_drafts(raw, topic, skipped), topic))
        checked += run_checks(retry_batches)
        items = [item for topic in topics for item in topic["items"]]
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
            "check_version": check_version if is_v2 else None,
            "items_checked": checked,
            "min_items_per_topic": MIN_ITEMS_PER_TOPIC if is_v2 else None,
            "retry_prompt_version": (
                (
                    LEVELLED_RETRY_PROMPT_VERSION
                    if prompt_version in LEVELLED_PROMPTS
                    else RETRY_PROMPT_VERSION
                )
                if is_v2
                else None
            ),
            "topics_retried": retried,
            "concepts": len(concepts),
            "concepts_without_chunks": no_chunks,
            "concepts_without_items": sorted(
                {c["id"] for c in concepts} - {i["concept_id"] for i in items} - set(no_chunks)
            ),
            "skipped": dict(sorted(skipped.items())),  # every attempt, retries included
            "skipped_on_retry": dict(sorted((skipped - skipped_first_try).items())),
            "dropped": [row for topic in topics for row in topic.get("dropped", [])],
            **(
                {
                    "drop_rate_by_level": drop_rate_by_level(topics),
                    "retried_only_for_missing_level": retried_only_for_level,
                    "concepts_missing_level": {
                        level: sorted(
                            t["concept"]["id"]
                            for t in topics
                            if not any(i.get("difficulty") == level for i in t["items"])
                        )
                        for level in LEVELS
                    },
                }
                if prompt_version in LEVELLED_PROMPTS
                else {}
            ),
        },
    }


def _contract_of(path: Path) -> str | None:
    try:
        return schema_for(path)
    except ValueError:
        return None


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
    parser.add_argument("--check-version", default=CHECK_VERSION, help=f"default: {CHECK_VERSION}")
    args = parser.parse_args(argv)
    if _contract_of(args.out) != "quiz_items":  # before any LLM call: saving is the last step
        parser.error(f"--out {args.out}: the file name must end in quiz_items.json")
    concepts_data = read_json(args.concepts)
    all_concepts = concepts_data["concepts"]
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
        check_version=args.check_version,
        all_concepts=all_concepts,
    )
    write_json(args.out, quiz)
    g = quiz["generation"]
    print(
        f"quiz: {len(quiz['items'])} items for {g['concepts']} concepts -> {args.out}; "
        f"dropped {sum(g['skipped'].values())} items {g['skipped']}, "
        f"retried {len(g['topics_retried'])} topics, "
        f"{len(g['concepts_without_chunks'])} concepts had no chunks"
    )


if __name__ == "__main__":
    main()
