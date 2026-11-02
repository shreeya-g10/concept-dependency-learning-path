"""discovery: concepts + chunks -> relationships.json (+ relationships_baseline.json)

    python -m cdlp.discovery --concepts outputs/concepts.json \
        --chunks outputs/chunks.jsonl --out-dir outputs [--baseline | --baseline-only]

--baseline also writes relationships_baseline.json: one LLM call with the full
concept list and no candidate filter (the RQ1 baseline), in the same format.
--baseline-only writes just relationships_baseline.json and skips the candidate
filter and every per-pair call (cheap ablation runs).

Discovery writes only relationships.json. Quiz items and simulated students are
built by the learning_path module (cdlp/learning_path/quiz.py, sim_students.py).
"""

import argparse
import sys
from pathlib import Path

from cdlp.discovery.baseline import BASELINE_PROMPT_VERSION, discover_baseline
from cdlp.discovery.candidates import candidate_stats, generate_candidates
from cdlp.discovery.llm_discovery import (
    PROMPT_VERSION,
    build_contract_relationships,
    discover_candidates,
)
from cdlp.shared.io import read_json, read_jsonl, write_json

# 1.2 adds the optional bidirectional / reverse_* fields (cdlp/shared/CHANGELOG.md)
RELATIONSHIPS_SCHEMA_VERSION = "1.2"
BASELINE_SCHEMA_VERSION = "1.3"  # relationships_baseline.json is new in 1.3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
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
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    concepts_data = read_json(args.concepts)
    course_id = concepts_data["course_id"]
    concepts = concepts_data["concepts"]
    chunks = read_jsonl(args.chunks)

    if args.baseline_only:
        write_baseline(args.out_dir, course_id, concepts, args.baseline_prompt_version)
        return

    candidates = generate_candidates(concepts_data, chunks)
    stats = candidate_stats(candidates, len(concepts))
    print(
        f"candidates: {stats['candidates']} of {stats['unordered_pairs']} pairs "
        f"({stats['tied']} tied, asked both ways) -> {stats['llm_calls']} LLM calls",
        file=sys.stderr,
    )

    relationships = discover_candidates(
        candidates,
        concepts,
        chunks,
        remove_transitive=args.remove_transitive,
        prompt_version=args.prompt_version,
    )
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
        write_baseline(args.out_dir, course_id, concepts, args.baseline_prompt_version)


def write_baseline(out_dir: Path, course_id: str, concepts: list, prompt_version: str) -> None:
    write_json(
        out_dir / "relationships_baseline.json",
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "course_id": course_id,
            "relationships": discover_baseline(concepts, prompt_version),
        },
    )


if __name__ == "__main__":
    main()
