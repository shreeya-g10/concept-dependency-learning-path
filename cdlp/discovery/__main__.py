"""discovery: concepts + chunks -> relationships.json (+ relationships_baseline.json)

    python -m cdlp.discovery --concepts outputs/concepts.json \
        --chunks outputs/chunks.jsonl --out-dir outputs [--baseline | --baseline-only]
    python -m cdlp.discovery --concepts outputs/benchmarks/X/sample_concepts.json \
        --pairs outputs/benchmarks/X/sample_pairs.csv --out-dir outputs/rq1/X

--pairs asks about exactly the listed pairs (CSV with source,target columns) instead of
running the candidate filter: for benchmarks, which have labelled pairs but no course
text. By default each pair is asked in BOTH directions (like a tied candidate), so the
gold file's orientation never tells the model the answer; --pairs-direction given asks
only the listed direction (half the calls). --chunks is optional with --pairs.

--prompt-version discover_v3 asks one neutral question per unordered pair (A before B, B
before A, or neither), so the direction comes from the model and not from the candidate's
course order. Tied candidates and --pairs-direction make no difference: one call per pair.

--baseline also writes relationships_baseline.json: one LLM call with the full
concept list and no candidate filter (the RQ1 baseline), in the same format.
--baseline-only writes just relationships_baseline.json and skips the candidate
filter and every per-pair call (cheap ablation runs).

Discovery writes only relationships.json. Quiz items and simulated students are
built by the learning_path module (cdlp/learning_path/quiz.py, sim_students.py).
--stats writes the run's LLM call counts.
"""

import argparse
import csv
import sys
from pathlib import Path

from cdlp.discovery.baseline import BASELINE_PROMPT_VERSION, discover_baseline
from cdlp.discovery.candidates import Candidate, candidate_stats, generate_candidates
from cdlp.discovery.llm_discovery import (
    NEUTRAL_PROMPT_VERSIONS,
    PROMPT_VERSION,
    build_contract_relationships,
    discover_candidates,
    neutral_summary,
)
from cdlp.shared import llm
from cdlp.shared.io import read_json, read_jsonl, write_json

# 1.2 adds the optional bidirectional / reverse_* fields (cdlp/shared/CHANGELOG.md)
RELATIONSHIPS_SCHEMA_VERSION = "1.2"
BASELINE_SCHEMA_VERSION = "1.3"  # relationships_baseline.json is new in 1.3


def read_pairs(path: Path, direction: str = "both") -> list:
    """Candidates for exactly the listed pairs; 'both' asks each pair both ways."""
    with Path(path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    if rows and not {"source", "target"} <= set(rows[0]):
        raise SystemExit(f"{path}: needs source and target columns")
    seen, out = set(), []
    for row in rows:
        a, b = row["source"].strip(), row["target"].strip()
        key = frozenset((a, b)) if direction == "both" else (a, b)
        if a == b or key in seen:
            continue
        seen.add(key)
        out.append(Candidate(source=a, target=b, reasons=["listed_pair"], tied=direction == "both"))
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, help="required unless --pairs is given")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--remove-transitive",
        action="store_true",
        help="leave out edges implied by a longer path (off: the validator handles redundancy)",
    )
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--baseline",
        action="store_true",
        help="also write relationships_baseline.json (one call, full concept list, no filter)",
    )
    mode.add_argument(
        "--baseline-only",
        action="store_true",
        help="write only relationships_baseline.json; no candidates, no per-pair calls",
    )
    parser.add_argument("--baseline-prompt-version", default=BASELINE_PROMPT_VERSION)
    parser.add_argument("--pairs", type=Path, help="ask exactly these pairs (benchmarks)")
    parser.add_argument("--pairs-direction", choices=["both", "given"], default="both")
    parser.add_argument("--num-ctx", type=int, help="Ollama context size for the baseline call")
    parser.add_argument("--stats", type=Path, help="write this run's LLM call counts here")
    args = parser.parse_args(argv)
    if not args.chunks and not args.pairs:
        parser.error("--chunks is required unless --pairs is given")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    concepts_data = read_json(args.concepts)
    course_id = concepts_data["course_id"]
    concepts = concepts_data["concepts"]
    chunks = read_jsonl(args.chunks) if args.chunks else []

    if args.baseline_only:
        write_baseline(
            args.out_dir, course_id, concepts, args.baseline_prompt_version, args.num_ctx
        )
        _write_stats(args.stats)
        return

    if args.pairs:
        known = {c["id"] for c in concepts}
        candidates = read_pairs(args.pairs, args.pairs_direction)
        missing = {x for c in candidates for x in (c.source, c.target)} - known
        if missing:
            raise SystemExit(
                f"{args.pairs}: concepts not in {args.concepts}: {sorted(missing)[:5]}"
            )
    else:
        candidates = generate_candidates(concepts_data, chunks)
    stats = candidate_stats(candidates, len(concepts))
    neutral = args.prompt_version in NEUTRAL_PROMPT_VERSIONS
    if neutral:
        n_pairs = len({frozenset((c.source, c.target)) for c in candidates})
        asked = f"(one neutral question each) -> {n_pairs} LLM calls"
    else:
        asked = f"({stats['tied']} tied, asked both ways) -> {stats['llm_calls']} LLM calls"
    print(
        f"candidates: {stats['candidates']} of {stats['unordered_pairs']} pairs {asked}",
        file=sys.stderr,
    )

    relationships = discover_candidates(
        candidates,
        concepts,
        chunks,
        remove_transitive=args.remove_transitive,
        prompt_version=args.prompt_version,
    )
    if neutral:
        print(f"{args.prompt_version} answers: {neutral_summary(relationships)}", file=sys.stderr)
    write_json(
        args.out_dir / "relationships.json",
        {
            "schema_version": RELATIONSHIPS_SCHEMA_VERSION,
            "course_id": course_id,
            "relationships": build_contract_relationships(
                relationships, concepts, chunks, args.prompt_version
            ),
        },
    )

    if args.baseline:
        write_baseline(
            args.out_dir, course_id, concepts, args.baseline_prompt_version, args.num_ctx
        )
    _write_stats(args.stats)


def _write_stats(path: Path | None) -> None:
    if path:
        stats = llm.write_stats(path)
        print(
            f"{stats['llm_calls']} LLM calls, {stats['cache_hits']} cache hits -> {path}",
            file=sys.stderr,
        )


def write_baseline(
    out_dir: Path, course_id: str, concepts: list, prompt_version: str, num_ctx=None
) -> None:
    write_json(
        out_dir / "relationships_baseline.json",
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "course_id": course_id,
            "relationships": discover_baseline(concepts, prompt_version, num_ctx),
        },
    )


if __name__ == "__main__":
    main()
