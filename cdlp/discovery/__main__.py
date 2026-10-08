import argparse
from pathlib import Path

from cdlp.discovery.candidates import generate_candidates
from cdlp.discovery.llm_discovery import (
    build_contract_relationships,
    discover_candidates,
)
from cdlp.discovery.quiz import generate_quiz_items
from cdlp.discovery.sim_students import (
    generate_simulated_students,
)
from cdlp.shared.io import read_json, read_jsonl, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run discovery on concepts and chunks."
    )

    parser.add_argument(
        "--concepts",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--chunks",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    args.out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    concepts_data = read_json(
        args.concepts
    )

    concepts = concepts_data["concepts"]

    chunks = read_jsonl(
        args.chunks
    )

    candidates = generate_candidates(
        concepts_data,
        chunks,
    )

    relationships = discover_candidates(
        candidates,
        concepts,
        chunks,
    )

    contract_relationships = build_contract_relationships(
        relationships,
        concepts,
        chunks,
    )

    write_json(
        args.out_dir / "relationships.json",
        {
            "schema_version": "1.0",
            "course_id": concepts_data["course_id"],
            "relationships": contract_relationships,
        },
    )

    quiz_items = generate_quiz_items(
        concepts,
        chunks,
    )

    write_json(
        args.out_dir / "quiz_items.json",
        {
            "schema_version": "1.0",
            "course_id": concepts_data["course_id"],
            "items": quiz_items,
        },
    )

    sim_students = generate_simulated_students(
        concepts,
        contract_relationships,
        count=500,
        seed=42,
    )

    write_json(
        args.out_dir / "sim_students.json",
        {
            "schema_version": "1.0",
            "course_id": concepts_data["course_id"],
            "students": sim_students,
        },
    )


if __name__ == "__main__":
    main()