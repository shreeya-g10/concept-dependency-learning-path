"""Evidence filter: keep the concepts the course material itself supports.

The LLM extracts concepts chunk by chunk, so one passing remark, one exercise or one code
call can become a concept. This filter uses only concepts.json, chunks.jsonl and
configs/concept_filter.json. It never reads data/gold.

Evidence per concept (exercise and summary sections never count, because they are full of
asides such as "Treque" or "Splay Tree" that the course does not teach):
- heading: its name or a specific alias is in a section heading
- source_chunks: chunks the LLM extracted it from
- mention_chunks / mention_docs: chunks and documents whose text contains the name or a
  specific alias. An alias is specific if no other concept uses it and it is not a single
  ordinary word: the LLM's aliases include "Add", "Tree" and "u", which would make any
  concept look well supported.

Decision, first match wins:
1. generic_word: the name is on the generic_names list. Removed even under a heading.
2. Kept: it is in a heading, or source_chunks >= strong_source_chunks.
3. code_name: the name is a call such as gather(u), or the text almost only uses it as one
   (push_black(u) appears as "push black(u)"), also after dropping "method" / "function".
4. Kept: mention_chunks >= min_mention_chunks, or source_chunks and mention_chunks are both
   high enough, or it is mentioned in several chunks across several documents.
5. exercise_only (all its sources are exercise or summary chunks), otherwise weak_evidence.

Kept concepts are copied unchanged, so ids, aliases, descriptions and sources stay stable.
Courses below min_chunks_to_apply are too small to judge, and a result below
min_concepts_after means the settings do not fit this course; both keep every concept and
say so in the report.

Usage:
    python -m cdlp.extraction.concept_filter --concepts outputs/ds101/concepts.json \
        --chunks outputs/ds101/chunks.jsonl --out-dir outputs/ds101/filtered
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from cdlp.shared.io import read_json, read_jsonl, write_json

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "concept_filter.json"
CALL_IN_NAME = re.compile(r"\w\(")


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Lowercase; fold ligatures; hyphens, underscores and line breaks become one space."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[-_\s]+", " ", text).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(text))


def strip_parenthetical(name: str) -> str:
    """'Abstract Data Type (ADT)' -> 'Abstract Data Type'."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", name).strip()


def term_pattern(term: str) -> re.Pattern | None:
    """Whole-phrase match with an optional plural, also written as one word (ArrayStack)."""
    phrase = normalize(strip_parenthetical(term))
    if len(phrase) < 2:
        return None
    forms = [re.escape(phrase)]
    if " " in phrase:
        forms.append(re.escape(phrase.replace(" ", "")))
    return re.compile(rf"(?<![a-z0-9])(?:{'|'.join(forms)})(?:s|es)?(?![a-z0-9])")


def call_pattern(term: str) -> re.Pattern:
    """Match a term with parentheses, with or without spaces between its characters."""
    chars = [re.escape(ch) for ch in normalize(term) if ch != " "]
    return re.compile(r"(?<![a-z0-9])" + r" ?".join(chars))


def is_specific_alias(alias: str, alias_users: Counter) -> bool:
    """True for 'Double-Ended Queue', 'BST' or 'DLList'; False for 'Add' or a shared alias."""
    if alias_users[compact(alias)] > 1:
        return False
    if len(normalize(alias).split()) > 1:
        return True
    return len(alias) >= 3 and alias != alias.lower() and alias[1:] != alias[1:].lower()


def is_code_name(concept: dict, texts: list[str], config: dict) -> bool:
    """True if the name is a call, or the course text nearly always writes it as a call."""
    name = concept["name"]
    if CALL_IN_NAME.search(name):
        return True
    # "Find X" with the alias find(x)
    for alias in concept.get("aliases", []):
        if CALL_IN_NAME.search(alias) and compact(alias) == compact(name):
            return True
    phrase = normalize(strip_parenthetical(name))
    words = phrase.split()
    if len(words) > 1 and words[-1] in config["code_suffixes"]:
        phrase = " ".join(words[:-1])
    used = re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?:s|es)?(?![a-z0-9])")
    call = re.compile(rf"(?<![a-z0-9]){re.escape(phrase)} ?\(")
    total = sum(len(used.findall(t)) for t in texts)
    calls = sum(len(call.findall(t)) for t in texts)
    return calls >= config["code_min_calls"] and calls / max(total, 1) >= config["code_call_share"]


def filter_concepts(
    concepts_data: dict[str, Any], chunks: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (filtered concepts.json data, report). The input is not modified."""
    concepts = concepts_data["concepts"]
    aside = re.compile(config["aside_heading_pattern"], re.I)
    is_aside = {c["chunk_id"]: bool(aside.search(c.get("heading") or "")) for c in chunks}
    main_chunks = [c for c in chunks if not is_aside[c["chunk_id"]]]
    all_texts = [normalize(c.get("text") or "") for c in chunks]
    main_texts = [normalize(c.get("text") or "") for c in main_chunks]
    headings = {normalize(c.get("heading") or "") for c in main_chunks}

    alias_users: Counter = Counter()
    for concept in concepts:
        alias_users.update(
            {compact(t) for t in [strip_parenthetical(concept["name"])] + _aliases(concept)}
        )
    generic = {normalize(n) for n in config["generic_names"]}

    rows, kept = [], []
    for concept in concepts:
        terms = [concept["name"]] + [
            a for a in _aliases(concept) if is_specific_alias(a, alias_users)
        ]
        patterns = [p for p in map(term_pattern, terms) if p]
        # O(log n) is written O(logn) in the text, so spaces inside a call are optional
        literals = [call_pattern(t) for t in terms if "(" in t]

        mention_idx = {
            i
            for i, text in enumerate(main_texts)
            if any(p.search(text) for p in patterns) or any(lit.search(text) for lit in literals)
        }
        source_ids = {s.get("chunk_id") or f"{s['doc']}#{s['page']}" for s in concept["sources"]}
        main_sources = {s for s in source_ids if not is_aside.get(s, False)}
        evidence = {
            "heading": any(p.search(h) for p in patterns for h in headings),
            "source_chunks": len(main_sources),
            "source_chunks_all": len(source_ids),
            "mention_chunks": len(mention_idx),
            "mention_docs": len({main_chunks[i]["doc"] for i in mention_idx}),
        }
        decision, reason = _decide(concept, evidence, generic, all_texts, config)
        rows.append(
            {
                "id": concept["id"],
                "name": concept["name"],
                "decision": decision,
                "reason": reason,
                **evidence,
            }
        )
        if decision == "keep":
            kept.append(concept)

    note = ""
    if len(chunks) < config["min_chunks_to_apply"]:
        note = f"not applied: only {len(chunks)} chunks, too few to judge concepts by evidence"
    elif len(kept) < config["min_concepts_after"]:
        note = f"not applied: only {len(kept)} concepts would remain; check the settings"
    if note:
        kept = list(concepts)

    report = {
        "filter_version": config["version"],
        "config": config,
        "course_id": concepts_data.get("course_id"),
        "applied": not note,
        "note": note,
        "concepts_before": len(concepts),
        "concepts_after": len(kept),
        "reasons": dict(sorted(Counter(r["reason"] for r in rows).items())),
        "concepts": rows,
    }
    return {**concepts_data, "concepts": kept}, report


def _aliases(concept: dict) -> list[str]:
    return list(concept.get("aliases") or [])


def _decide(
    concept: dict, evidence: dict, generic: set[str], texts: list[str], config: dict
) -> tuple[str, str]:
    name = normalize(strip_parenthetical(concept["name"]))
    if name in generic or name.removesuffix("s") in generic:
        return "remove", "generic_word"
    if evidence["heading"]:
        return "keep", "heading"
    if evidence["source_chunks"] >= config["strong_source_chunks"]:
        return "keep", "many_source_chunks"
    if is_code_name(concept, texts, config):
        return "remove", "code_name"
    mentions, docs = evidence["mention_chunks"], evidence["mention_docs"]
    if mentions >= config["min_mention_chunks"]:
        return "keep", "many_mentions"
    if evidence["source_chunks"] >= config["min_source_chunks_with_mention"] and mentions >= 1:
        return "keep", "sources_and_mentions"
    if mentions >= config["min_mention_chunks_across_docs"] and docs >= config["min_mention_docs"]:
        return "keep", "several_documents"
    return "remove", "exercise_only" if evidence["source_chunks"] == 0 else "weak_evidence"


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True, help="gets concepts.json + report")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    filtered, report = filter_concepts(
        read_json(args.concepts), read_jsonl(args.chunks), load_config(args.config)
    )
    report["input_sha256"] = {
        "concepts": file_sha256(args.concepts),
        "chunks": file_sha256(args.chunks),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "concepts.json", filtered)
    (args.out_dir / "concept_filter_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{report['concepts_before']} -> {report['concepts_after']} concepts {report['reasons']}")


if __name__ == "__main__":
    main()
