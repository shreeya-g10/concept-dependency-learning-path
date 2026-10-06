"""discovery — concepts + chunks -> relationships.json, quiz_items.json, sim_students.json

    python -m cdlp.discovery --concepts outputs/concepts.json \
        --chunks outputs/chunks.jsonl --out-dir outputs
"""

import argparse
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Sneha): candidate filter + LLM discovery -> relationships.json
    write_json(args.out_dir / "relationships.json", read_json(EXAMPLES / "relationships.json"))
    # TODO(Sneha): LLM-generated quiz items per concept -> quiz_items.json
    write_json(args.out_dir / "quiz_items.json", read_json(EXAMPLES / "quiz_items.json"))
    # TODO(Sneha): synthetic students with known mastery -> sim_students.json
    write_json(args.out_dir / "sim_students.json", read_json(EXAMPLES / "sim_students.json"))


if __name__ == "__main__":
    main()
