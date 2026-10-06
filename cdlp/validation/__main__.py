"""validation — relationships + chunks -> validated_graph.json

    python -m cdlp.validation --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --chunks outputs/chunks.jsonl \
        --out outputs/validated_graph.json
"""

import argparse
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Shreeya): evidence, semantic, necessity (simulated learner) and graph
    # checks -> ACCEPT / REJECT / HUMAN_REVIEW for every relationship.
    write_json(args.out, read_json(EXAMPLES / "validated_graph.json"))


if __name__ == "__main__":
    main()
