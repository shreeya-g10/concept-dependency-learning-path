"""Count the LLM calls of a full course run per call type, and estimate its time. No LLM calls.

    python scripts/recount_course_run.py --concepts outputs/ds101/filtered/concepts.json \
        --chunks outputs/ds101/chunks.jsonl --necessity-sample 40 \
        --bias cdlp/discovery/results/order_bias_ds101.json \
        --speed-cache ../concept-dependency-learning-path/.cache/llm \
        --out cdlp/discovery/results/stage3_recount_ds101.json

Discovery asks are counted for real, and each is looked up in the LLM cache by the real code path.
The number of edges is unknown until discovery runs, so it is estimated from the order-bias
sample (non-gold pairs only), with a seeded bootstrap for its range. Speeds come from measured
calls: the time between neighbouring cached calls of one prompt, and the seconds the order-bias
run recorded. All of this is an estimate for planning, not a result.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from cdlp.discovery import llm_discovery as ld
from cdlp.discovery.candidates import generate_candidates
from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl

BOOTSTRAPS = 10_000
SEED = 42
EDGES_PER_AGREEMENT = {"same": 1, "flip_to_neither": 1, "position_followed": 2}


class NotCached(Exception):
    pass


def count_cached_asks(concepts: dict, chunks: list[dict], pairs: list[tuple[str, str]]) -> int:
    """Asks a real both-orders run would read from the cache. Nothing is sent or written."""
    chunk_map = {c["chunk_id"]: c for c in chunks}
    version = ld.PROMPT_VERSION

    def refuse(*args, **kwargs):
        raise NotCached

    real_post, llm.requests.post = llm.requests.post, refuse
    cached = 0
    try:
        for x, y in pairs:
            a, b = ld.neutral_order(concepts[x], concepts[y], version)
            evidence = ld.select_neutral_evidence(*sorted((a, b), key=lambda c: c["id"]), chunk_map)
            for first, second in ((a, b), (b, a)):
                prompt = ld.format_neutral_prompt(first, second, evidence, version)
                try:
                    llm.chat_json(prompt, prompt_version=version, temperature=ld.TEMPERATURE)
                    cached += 1
                except NotCached:
                    pass
                except ValueError:
                    cached += 1  # a cached reply that was not JSON: still no call
    finally:
        llm.requests.post = real_post
    return cached


def edges_per_pair(bias: dict) -> dict:
    rows = [p for p in bias["pairs"] if p["group"] == "sample"]
    edges = [
        0
        if p["comparison"] == "same" and p["asks"][0]["says"] == "NEITHER"
        else EDGES_PER_AGREEMENT[p["comparison"]]
        for p in rows
    ]
    rng = random.Random(SEED)
    means = sorted(sum(rng.choices(edges, k=len(edges))) / len(edges) for _ in range(BOOTSTRAPS))
    return {
        "sample_pairs": len(edges),
        "edges_in_sample": sum(edges),
        "reversed_pairs_in_sample": sum(p["comparison"] == "position_followed" for p in rows),
        "point": sum(edges) / len(edges),
        "low_2_5": means[int(0.025 * BOOTSTRAPS)],
        "high_97_5": means[int(0.975 * BOOTSTRAPS)],
    }


def speeds(cache_dir: Path) -> dict:
    rows = [json.loads(p.read_text()) for p in cache_dir.glob("*.json")]
    rows = sorted((r for r in rows if r.get("created")), key=lambda r: r["created"])
    gaps = defaultdict(list)
    for before, after in zip(rows, rows[1:], strict=False):
        gap = after["created"] - before["created"]
        same = (before["prompt_version"], before["model"]) == (
            after["prompt_version"],
            after["model"],
        )
        if same and 0 < gap < 300:
            gaps[after["prompt_version"]].append(gap)
    return {
        version: {"n": len(v), "median": statistics.median(v), "mean": statistics.mean(v)}
        for version, v in gaps.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--bias", type=Path, required=True)
    parser.add_argument("--speed-cache", type=Path, required=True)
    parser.add_argument("--necessity-sample", type=int, default=40)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    data = read_json(args.concepts)
    concepts = {c["id"]: c for c in data["concepts"]}
    chunks = read_jsonl(args.chunks)
    pairs = sorted({tuple(sorted((c.source, c.target))) for c in generate_candidates(data, chunks)})
    bias = json.loads(args.bias.read_text())
    asks = 2 * len(pairs)
    cached = count_cached_asks(concepts, chunks, pairs)
    to_ask = asks - cached
    disc = sorted(a["seconds"] for p in bias["pairs"] for a in p["asks"] if a["seconds"] > 0)
    disc_low, disc_high = statistics.mean(disc), disc[int(0.9 * len(disc)) - 1]

    rate = edges_per_pair(bias)
    edges = {k: round(rate[k] * len(pairs)) for k in ("point", "low_2_5", "high_97_5")}
    speed = speeds(args.speed_cache)
    ev, se = speed["evidence_v1"], speed["semantic_v2"]
    learner, grader = speed["necessity_learner_without_v1"], speed["necessity_grader_v1"]
    writer_seconds = 36  # CLAUDE.local.md: long reply, no neighbouring writer calls to measure
    # per edge: writer (up to 2 more if it names A), 3 learners, 3 graders
    necessity_low = writer_seconds + 3 * learner["median"] + 3 * grader["median"]
    necessity_high = 3 * writer_seconds + 3 * learner["mean"] + 3 * grader["mean"]
    hours = lambda seconds: round(seconds / 3600, 1)  # noqa: E731
    result = {
        "note": "Planning estimate from measured speeds. Not a result.",
        "concepts": len(concepts),
        "candidate_pairs": len(pairs),
        "discovery": {
            "model": llm.DEFAULT_MODEL,
            "asks": asks,
            "cached": cached,
            "to_ask": to_ask,
            "seconds_per_call": {"mean": disc_low, "p90": disc_high, "n": len(disc)},
            "hours": [hours(to_ask * disc_low), hours(to_ask * disc_high)],
        },
        "edges_per_pair": rate,
        "edges_estimate": edges,
        "reversed_edges_estimate": round(
            rate["reversed_pairs_in_sample"] / rate["sample_pairs"] * len(pairs) * 2
        ),
        "evidence_check": {
            "calls": edges,
            "seconds_per_call": ev,
            "hours": [
                hours(edges["low_2_5"] * ev["median"]),
                hours(edges["high_97_5"] * ev["mean"]),
            ],
        },
        "semantic_check": {
            "calls": edges,
            "seconds_per_call": se,
            "hours": [
                hours(edges["low_2_5"] * se["median"]),
                hours(edges["high_97_5"] * se["mean"]),
            ],
        },
        "necessity": {
            "edges": args.necessity_sample,
            "calls_low": 7 * args.necessity_sample,
            "calls_high": 9 * args.necessity_sample,
            "seconds_per_edge": [necessity_low, necessity_high],
            "learner_seconds": learner,
            "grader_seconds": grader,
            "writer_seconds_assumed": writer_seconds,
            "hours": [
                hours(args.necessity_sample * necessity_low),
                hours(args.necessity_sample * necessity_high),
            ],
        },
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
