"""learning_path — validated graph + quiz items + students -> student_state.json, learning_path.json

    python -m cdlp.learning_path --graph outputs/validated_graph.json \
        --quiz outputs/quiz_items.json --students outputs/sim_students.json \
        --target avl_tree --out-dir outputs
"""

import argparse
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--students", type=Path, required=True)
    parser.add_argument("--target", required=True, help="target concept id, e.g. avl_tree")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Shrestha): build the graph from ACCEPT edges, run adaptive diagnosis
    # for each student, then compute the personalized path.
    write_json(args.out_dir / "student_state.json", read_json(EXAMPLES / "student_state.json"))
    write_json(args.out_dir / "learning_path.json", read_json(EXAMPLES / "learning_path.json"))


if __name__ == "__main__":
    main()
