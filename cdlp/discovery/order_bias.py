"""Does the answer under a neutral prompt depend on which concept is called A?

    python -m cdlp.discovery.order_bias --concepts outputs/ds101/filtered/concepts.json \
        --chunks outputs/ds101/chunks.jsonl --pairs-file <file> --prepare
    python -m cdlp.discovery.order_bias --concepts ... --chunks ... --pairs-file <file> \
        --out cdlp/discovery/results/order_bias_ds101.json [--limit 2]

--prepare writes the pairs (the positive gold pairs plus a seeded sample of other candidates)
and exits, so the embedding model has left memory before Ollama loads. The next step asks every
pair twice, A and B swapped, with the same evidence and the real prompt. This only measures: no
gold label reaches the model, and nothing here changes a prompt or a setting.

flip: the two orders give different concept-level answers. Either the direction reverses
(position_followed: the same letter answer both times) or one order says NEITHER.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import time
from collections import Counter
from datetime import date
from pathlib import Path

from cdlp.discovery.llm_discovery import (
    PAIR_ORDER_RULES,
    TEMPERATURE,
    _normalise_neutral_result,
    format_neutral_prompt,
    load_prompt,
    neutral_order,
    select_neutral_evidence,
)
from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl
from cdlp.shared.llm import chat_json

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "order_bias_ds101.json"
NOTE = "Measurement only. Nothing was changed based on it."


def gold_pairs(cfg: dict) -> tuple[list[list[str]], set[frozenset]]:
    """(positive pairs as [source, target], every labelled pair)."""
    rename = cfg["gold_id_to_concept"]
    with open(cfg["gold_edges"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    named = [
        (rename.get(r["source"], r["source"]), rename.get(r["target"], r["target"]), r)
        for r in rows
    ]
    positive = [[s, t] for s, t, r in named if r["label"] in {"hard", "soft"}]
    return positive, {frozenset((s, t)) for s, t, _ in named}


def prepare(concepts_data: dict, chunks: list, cfg: dict) -> dict:
    from cdlp.discovery.candidates import generate_candidates

    candidates = generate_candidates(concepts_data, chunks)
    positive, labelled = gold_pairs(cfg)
    known = {c["id"] for c in concepts_data["concepts"]}
    missing = sorted({x for pair in positive for x in pair} - known)
    if missing:
        raise SystemExit(f"gold concepts not in the concept list: {missing}")
    unordered = sorted({tuple(sorted((c.source, c.target))) for c in candidates})
    others = [list(pair) for pair in unordered if frozenset(pair) not in labelled]
    sample = random.Random(cfg["seed"]).sample(others, cfg["sample_size"])
    return {
        "candidate_pairs": len(unordered),
        "gold_positive": positive,
        "sample": sample,
        "gold_positive_in_candidates": sum(tuple(sorted(p)) in unordered for p in positive),
    }


def ask(a: dict, b: dict, evidence: list[dict], version: str) -> dict:
    prompt = format_neutral_prompt(a, b, evidence, version)
    started = time.perf_counter()
    try:
        reply = chat_json(prompt, prompt_version=version, temperature=TEMPERATURE)
    except ValueError:
        reply = {}
    record = _normalise_neutral_result(reply, a, b, {e["chunk_id"] for e in evidence})
    return {
        "a": a["id"],
        "b": b["id"],
        "answer": record["answer"],
        "strength": record["strength"],
        "confidence": record["confidence"],
        "on_topic": record["on_topic"],
        # concept-level answer, comparable between the two orders
        "says": f"{record['source']}->{record['target']}"
        if record["answer"] != "NEITHER"
        else "NEITHER",
        "prompt_chars": len(prompt),
        "seconds": round(time.perf_counter() - started, 1),
    }


def compare(first: dict, second: dict) -> str:
    if first["says"] == second["says"]:
        return "same"
    if first["says"] == "NEITHER" or second["says"] == "NEITHER":
        return "flip_to_neither"
    return "position_followed"


def summarize(rows: list[dict]) -> dict:
    asks = [ask_ for row in rows for ask_ in row["asks"]]
    hash_asks = [row["asks"][0] for row in rows]
    return {
        "pairs": len(rows),
        "answers_all_asks": dict(Counter(a["answer"] for a in asks)),
        "answers_hash_order_only": dict(Counter(a["answer"] for a in hash_asks)),
        "off_topic_asks": sum(not a["on_topic"] for a in asks),
        "both_orders": dict(Counter(row["comparison"] for row in rows)),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--pairs-file", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int, help="first N pairs only (a speed check)")
    args = parser.parse_args(argv)

    cfg = json.loads(args.config.read_text())
    concepts_data = read_json(args.concepts)
    chunks = read_jsonl(args.chunks)
    if args.prepare:
        pairs = prepare(concepts_data, chunks, cfg)
        args.pairs_file.write_text(json.dumps(pairs, indent=2) + "\n")
        print({k: pairs[k] for k in ("candidate_pairs", "gold_positive_in_candidates")})
        return
    if not args.out:
        parser.error("--out is required unless --prepare is given")

    pairs = json.loads(args.pairs_file.read_text())
    version = cfg["prompt_version"]
    concepts = {c["id"]: c for c in concepts_data["concepts"]}
    chunk_map = {c["chunk_id"]: c for c in chunks}
    todo = [("gold_positive", p) for p in pairs["gold_positive"]]
    todo += [("sample", p) for p in pairs["sample"]]
    rows = []
    for group, (x, y) in todo[: args.limit] if args.limit else todo:
        # the hash order first: it is the order a real run asks, so its answer is cached for one
        a, b = neutral_order(concepts[x], concepts[y], version)
        evidence = select_neutral_evidence(*sorted((a, b), key=lambda c: c["id"]), chunk_map)
        first, second = ask(a, b, evidence, version), ask(b, a, evidence, version)
        rows.append(
            {
                "group": group,
                "pair": [x, y],
                "comparison": compare(first, second),
                "asks": [first, second],
            }
        )
        print(
            group,
            x,
            y,
            first["says"],
            "|",
            second["says"],
            first["seconds"],
            second["seconds"],
            flush=True,
        )
    result = {
        "note": NOTE,
        "date": date.today().isoformat(),
        "model": llm.DEFAULT_MODEL,
        "prompt_version": version,
        "prompt_sha256": hashlib.sha256(load_prompt(version).encode()).hexdigest(),
        "pair_order_rule_for_first_ask": PAIR_ORDER_RULES[version],
        "temperature": TEMPERATURE,
        "seed": llm.DEFAULT_SEED,
        "config": cfg,
        "concepts_sha256": hashlib.sha256(args.concepts.read_bytes()).hexdigest(),
        "chunks_sha256": hashlib.sha256(args.chunks.read_bytes()).hexdigest(),
        "candidate_pairs": pairs["candidate_pairs"],
        "llm_stats": llm.get_stats(),
        "gold_positive": summarize([r for r in rows if r["group"] == "gold_positive"]),
        "sample": summarize([r for r in rows if r["group"] == "sample"]),
        "all": summarize(rows),
        "pairs": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(result["all"], result["llm_stats"])


if __name__ == "__main__":
    main()
