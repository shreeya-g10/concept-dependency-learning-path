"""Replay saved quiz_v2 drafts through a version of the checks, recording the second model's reply.

    python -m cdlp.learning_path.replay_quiz_check --cache-dir ../cdlp-ui4/.cache/llm \
        --concepts outputs/ds101/filtered/concepts.json --chunks outputs/ds101/chunks.jsonl \
        --before cdlp/learning_path/results/quiz_check_v2_replay_ds101.json \
        --out cdlp/learning_path/results/quiz_check_v3_replay_ds101.json [--limit 3]

The drafts are the replies quiz_v2 gave in the 2026-11-03 review run, read from that run's LLM
cache. No draft is generated and no retry is asked. The no-LLM checks and check_item() are the
real ones from quiz.py; this file only records their inputs and the model's reply.

These questions shaped the checks (tests/quiz_dev_examples.json), so this is a working test.
No accuracy figure may come from it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path

from cdlp.learning_path import quiz, quiz_check_v3
from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl

NOTE = "Working test on the questions that shaped the checks. Not an accuracy result."


def read_cached_drafts(cache_dir: Path) -> dict[str, list]:
    """{concept id: raw drafts}, from the cached quiz_v2 replies. Sorted, so runs are stable."""
    drafts = {}
    for path in sorted(cache_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("prompt_version") == quiz.PROMPT_VERSION:
            concept_id = re.search(r"CONCEPT ID:\s*(\S+)", row["messages"][-1]["content"]).group(1)
            drafts[concept_id] = json.loads(row["response"])["items"]
    return dict(sorted(drafts.items()))


def replay(
    drafts: dict[str, list],
    concepts: dict,
    chunks: list,
    template: str,
    model,
    limit=None,
    check_version: str = quiz.CHECK_VERSION,
):
    """One row per raw draft: the no-LLM result, then the second model's reply and the verdict."""
    rows, to_check = [], []
    v3 = (
        quiz.v3_context(list(concepts.values()))
        if check_version != quiz.OLD_CHECK_VERSION
        else None
    )
    for concept_id, raw in drafts.items():
        topic = {
            "concept": concepts[concept_id],
            "evidence": quiz.focused_chunks(concepts[concept_id], chunks),
            "items": [],
            "failures": [],
            "excerpts": {},
            "numbered": 0,
        }
        if v3:
            topic["v3"] = v3
        passed = quiz._take_drafts(raw, topic, Counter())
        dropped = {d["question"]: d for d in topic.get("dropped", [])}
        by_question = {item["question"]: item for item in passed}
        for one in raw:
            question = one.get("question", "")
            row = {"concept_id": concept_id, "question": question, "draft": one}
            if question in by_question:
                item = by_question[question]
                row.update(item=item, excerpt=topic["excerpts"][item["id"]])
                to_check.append(row)
            else:
                row.update(
                    stage="no_llm",
                    final="drop",
                    reason=dropped[question]["reason"],
                    detail=dropped[question]["detail"],
                )
            rows.append(row)

    seconds = []
    for row in to_check[:limit] if limit else to_check:
        item = row["item"]
        reply: dict = {}
        started = time.perf_counter()
        reason = quiz.check_item(
            item, concepts[row["concept_id"]], row["excerpt"], template, model, record=reply
        )
        seconds.append(round(time.perf_counter() - started, 1))
        options = sorted(item["options"], key=quiz._norm)  # as check_item letters them
        row.update(
            stage="second_model",
            options_lettered=dict(zip("ABCDEF", options, strict=False)),
            answer_letter="ABCDEF"[options.index(item["answer"])],
            reply=reply,
            final="drop" if reason else "keep",
            reason=reason,
            seconds=seconds[-1],
        )
    return rows, len(to_check), seconds


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="ask the model about the first N drafts only")
    parser.add_argument("--check-version", default=quiz.CHECK_VERSION)
    parser.add_argument("--before", type=Path, help="an earlier replay: adds its verdict per draft")
    args = parser.parse_args(argv)

    concepts = {c["id"]: c for c in read_json(args.concepts)["concepts"]}
    template = quiz.load_prompt(quiz.CHECK_PROMPT_VERSION)
    model = os.getenv("LLM_VALIDATOR_MODEL") or None
    drafts = read_cached_drafts(args.cache_dir)
    rows, reached_model, seconds = replay(
        drafts, concepts, read_jsonl(args.chunks), template, model, args.limit, args.check_version
    )
    if args.before:
        before = {
            (d["concept_id"], d["question"]): d
            for d in json.loads(args.before.read_text(encoding="utf-8"))["drafts"]
        }
        for row in rows:
            old = before[(row["concept_id"], row["question"])]
            row["before"] = {
                "stage": old["stage"],
                "final": old["final"],
                "reason": old["reason"],
                "reply": old.get("reply"),
            }
    judged = [r for r in rows if r.get("final")]
    result = {
        "note": NOTE,
        "date": date.today().isoformat(),
        "check_model": model or llm.DEFAULT_MODEL,
        "check_version": args.check_version,
        "check_prompt_version": quiz.CHECK_PROMPT_VERSION,
        "check_config": quiz_check_v3.load_config()
        if args.check_version != quiz.OLD_CHECK_VERSION
        else None,
        "check_prompt_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "temperature": quiz.TEMPERATURE,
        "seed": llm.DEFAULT_SEED,
        "draft_prompt_version": quiz.PROMPT_VERSION,
        "drafts_from": "quiz_v2 replies of the 2026-11-03 ds101 review run (cached)",
        "chunks_sha256": hashlib.sha256(args.chunks.read_bytes()).hexdigest(),
        "concepts_sha256": hashlib.sha256(args.concepts.read_bytes()).hexdigest(),
        "raw_drafts": len(rows),
        "reached_second_model": reached_model,
        "model_calls_this_run": len(seconds),
        "seconds_per_call": seconds,
        "llm_stats": llm.get_stats(),
        "outcomes": dict(Counter(r["reason"] or "keep" for r in judged)),
        "drafts": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(seconds)} of {reached_model} checked, seconds {seconds}; {result['outcomes']}")


if __name__ == "__main__":
    main()
