"""root_cause — validated graph + quiz items + student answers -> root_cause.json

    python -m cdlp.root_cause --graph outputs/validated_graph.json \
        --quiz outputs/quiz_items.json --answers outputs/student_answers.json \
        --out outputs/root_cause.json
"""

import argparse
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Shreeya): call api.trace for every wrong answer in student_answers.json,
    # using each student's mastery, -> root_cause.json
    write_json(args.out, read_json(EXAMPLES / "root_cause.json"))


if __name__ == "__main__":
    main()
