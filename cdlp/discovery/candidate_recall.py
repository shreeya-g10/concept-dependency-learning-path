"""Candidate recall: what share of gold prerequisite edges survive the candidate filter.

    python -m cdlp.discovery.candidate_recall --concepts outputs/ds101/concepts.json \
        --chunks outputs/ds101/chunks.jsonl --gold data/gold/gold_edges.csv

Writes cdlp/discovery/results/candidate_recall_<course_id>.json. No LLM call is
made; this is the recall ceiling of discovery, since an edge that is never a
candidate is never asked about.

- recall_directed: gold hard/soft edge is a candidate in the gold direction.
- recall_any_direction: the pair is a candidate in either direction (a reversed
  candidate can still be found if it is tied, i.e. asked both ways).
Gold edges whose concepts are not in this course's concept list are reported
under missing_concepts and count as misses.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from cdlp.discovery.candidates import EMBEDDING_MODEL, generate_candidates
from cdlp.discovery.evaluate import POSITIVE_LABELS, load_gold

RESULTS = Path(__file__).parent / "results"


def candidate_recall(candidates: list, gold: list[dict], concept_ids: set) -> dict:
    directed = {(c.source, c.target) for c in candidates}
    undirected = {frozenset(pair) for pair in directed}
    positives = sorted(
        (row["source"], row["target"], row["label"].strip().lower())
        for row in gold
        if row["label"].strip().lower() in POSITIVE_LABELS
    )

    hits_directed = hits_any = 0
    missed, missing_concepts = [], []
    for source, target, label in positives:
        if source not in concept_ids or target not in concept_ids:
            missing_concepts.append({"source": source, "target": target, "gold": label})
            continue
        if (source, target) in directed:
            hits_directed += 1
        if frozenset((source, target)) in undirected:
            hits_any += 1
        else:
            missed.append({"source": source, "target": target, "gold": label})

    total = len(positives)
    return {
        "gold_positive_edges": total,
        "candidates": len(candidates),
        "hits_directed": hits_directed,
        "hits_any_direction": hits_any,
        "recall_directed": hits_directed / total if total else 0.0,
        "recall_any_direction": hits_any / total if total else 0.0,
        "missed": missed,
        "missing_concepts": missing_concepts,
    }


def main() -> None:
    from cdlp.discovery.llm_discovery import PROMPT_VERSION
    from cdlp.shared.io import read_json, read_jsonl
    from cdlp.shared.llm import DEFAULT_MODEL, DEFAULT_SEED

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--gold", type=Path, default=Path("data/gold/gold_edges.csv"))
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--embedding-threshold", type=float, default=0.55)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM the run is paired with")
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    concepts_data = read_json(args.concepts)
    course_id = concepts_data["course_id"]
    candidates = generate_candidates(
        concepts_data, read_jsonl(args.chunks), embedding_threshold=args.embedding_threshold
    )
    metrics = candidate_recall(
        candidates, load_gold(args.gold), {c["id"] for c in concepts_data["concepts"]}
    )
    result = {
        "config": {
            "course_id": course_id,
            "concepts": str(args.concepts),
            "chunks": str(args.chunks),
            "gold": str(args.gold),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_threshold": args.embedding_threshold,
            # the filter itself makes no LLM call; these pair the result with a discovery run
            "model": args.model,
            "prompt_version": args.prompt_version,
            "seed": args.seed,
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "metrics": metrics,
    }
    out = args.out_dir / f"candidate_recall_{course_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"candidate recall ({course_id}): {metrics['hits_directed']}/"
        f"{metrics['gold_positive_edges']} directed, {metrics['hits_any_direction']}/"
        f"{metrics['gold_positive_edges']} any direction -> {out}"
    )


if __name__ == "__main__":
    main()
