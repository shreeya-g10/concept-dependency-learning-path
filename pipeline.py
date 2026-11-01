"""Run the whole pipeline end to end. Owner: Shreeya (lead) — do not edit.

    python pipeline.py --course ds101 --target avl_tree

Reads course files from data/raw/<course>/ and writes to outputs/<course>/.
Root-cause tracing runs only when outputs/<course>/student_answers.json exists.
Each step calls one module's CLI and checks its output against the contract.
Modules never import each other; they only exchange the files in outputs/<course>/.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from cdlp.shared.io import EXAMPLES
from cdlp.shared.validate import check_file


def run(module: str, *args: str) -> None:
    print(f"\n==> {module}")
    subprocess.run([sys.executable, "-m", module, *args], check=True)


def produced_or_example(out: Path, name: str) -> Path:
    """out/<name> if a module wrote it, else the shared example (with a note)."""
    if (out / name).exists():
        return out / name
    print(f"note: no {out / name}, using {EXAMPLES / name}")
    return EXAMPLES / name


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
    # discovery no longer writes quiz_items.json or sim_students.json; until
    # learning_path builds them, fall back to the shared examples
    quiz_items = produced_or_example(out, "quiz_items.json")
    sim_students = produced_or_example(out, "sim_students.json")
    run(
        "cdlp.learning_path",
        "--graph",
        str(out / "validated_graph.json"),
        "--quiz",
        str(quiz_items),
        "--students",
        str(sim_students),
        "--target",
        args.target,
        "--out-dir",
        str(out),
    )
    if (out / "student_answers.json").exists():
        run(
            "cdlp.root_cause",
            "--graph",
            str(out / "validated_graph.json"),
            "--quiz",
            str(quiz_items),
            "--answers",
            str(out / "student_answers.json"),
            "--out",
            str(out / "root_cause.json"),
        )
    else:
        print("\n==> cdlp.root_cause skipped (no student_answers.json)")

    print("\n==> contract check")
    failed = False
    for path in sorted(out.iterdir()):
        errors = check_file(path)
        print(f"[{'OK' if not errors else 'FAIL'}] {path}")
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
