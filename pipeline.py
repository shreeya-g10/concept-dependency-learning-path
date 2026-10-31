"""Run the whole pipeline end to end. Owner: Shreeya (lead) — do not edit.

    python pipeline.py --course ds101 --target avl_tree

Reads course files from data/raw/<course>/ and writes to outputs/<course>/.
Each step calls one module's CLI and checks its output against the contract.
Modules never import each other; they only exchange the files in outputs/<course>/.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from cdlp.shared.validate import check_file


def run(module: str, *args: str) -> None:
    print(f"\n==> {module}")
    subprocess.run([sys.executable, "-m", module, *args], check=True)


def course_input(course: str) -> Path:
    """data/raw/<course>/, or data/raw/ while the course files still sit there."""
    folder = Path("data/raw") / course
    if folder.is_dir():
        return folder
    print(f"note: {folder} not found, reading data/raw/ instead")
    return Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="ds101")
    parser.add_argument("--input", help="default: data/raw/<course>/")
    parser.add_argument("--target", default="avl_tree")
    parser.add_argument("--out-dir", help="default: outputs/<course>/")
    args = parser.parse_args()
    raw = Path(args.input) if args.input else course_input(args.course)
    out = Path(args.out_dir) if args.out_dir else Path("outputs") / args.course
    out.mkdir(parents=True, exist_ok=True)

    run("cdlp.extraction", "--input", str(raw), "--out-dir", str(out))
    run(
        "cdlp.discovery",
        "--concepts",
        str(out / "concepts.json"),
        "--chunks",
        str(out / "chunks.jsonl"),
        "--out-dir",
        str(out),
    )
    run(
        "cdlp.validation",
        "--relationships",
        str(out / "relationships.json"),
        "--concepts",
        str(out / "concepts.json"),
        "--chunks",
        str(out / "chunks.jsonl"),
        "--out",
        str(out / "validated_graph.json"),
    )
    run(
        "cdlp.learning_path",
        "--graph",
        str(out / "validated_graph.json"),
        "--quiz",
        str(out / "quiz_items.json"),
        "--students",
        str(out / "sim_students.json"),
        "--target",
        args.target,
        "--out-dir",
        str(out),
    )

    print("\n==> contract check")
    failed = False
    for path in sorted(out.iterdir()):
        errors = check_file(path)
        print(f"[{'OK' if not errors else 'FAIL'}] {path}")
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
