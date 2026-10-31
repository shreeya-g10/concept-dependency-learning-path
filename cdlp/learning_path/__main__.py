"""learning_path — graph + quiz + students -> student_state.json + learning_path.json

Owner: Vaidehi (inherited from Shrestha).
Usage:
    python -m cdlp.learning_path --graph outputs/validated_graph.json \
        --quiz outputs/quiz_items.json --students outputs/sim_students.json \
        --target avl_tree --out-dir outputs
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cdlp.learning_path import api
from cdlp.shared.io import read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        required=True,
        help="path to validated_graph.json",
    )
    parser.add_argument(
        "--quiz",
        type=Path,
        required=True,
        help="path to quiz_items.json",
    )
    parser.add_argument(
        "--students",
        type=Path,
        required=True,
        help="path to sim_students.json",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="avl_tree",
        help="target concept slug",
    )
    parser.add_argument(
        "--out-dir",
        "--out",
        dest="out_dir",
        type=Path,
        required=True,
        help="output folder",
    )
    args = parser.parse_args()

    graph = read_json(args.graph)
    quiz = read_json(args.quiz)
    students_data = read_json(args.students)

    course_id = (
        graph.get("course_id")
        or (students_data.get("course_id") if isinstance(students_data, dict) else None)
        or "ds101"
    )

    students = (
        students_data if isinstance(students_data, list) else students_data.get("students", [])
    )

    student_states = []
    learning_paths = []

    for student in students:
        student_id = student.get("id", student.get("student_id", "s01"))
        true_mastery = student.get("mastery", {})
        target = student.get("target", args.target)

        # Initialize prior
        mastery = {concept: 0.5 for concept in api.prerequisite_order(graph, target)}

        answers = []
        asked_ids = []

        # Run diagnosis up to 10 questions
        for _ in range(10):
            question = api.next_question(
                graph,
                quiz,
                {**mastery, "__asked__": asked_ids},
                target,
            )
            if question is None:
                break

            q_id = question.get("id", question.get("item_id", f"q_{len(asked_ids)}"))
            concept = question["concept_id"]
            correct = true_mastery.get(concept, 0.5) > 0.5

            mastery = api.update_mastery(graph, mastery, concept, correct)
            asked_ids.append(q_id)
            answers.append(
                {
                    "item_id": q_id,
                    "correct": correct,
                }
            )

        clean_mastery = {k: v for k, v in mastery.items() if not k.startswith("__")}

        student_states.append(
            {
                "student_id": student_id,
                "target": target,
                "mastery": clean_mastery,
                "questions_asked": len(answers),
                "answers": answers,
            }
        )

        steps = api.personalized_path(graph, clean_mastery, target)
        learning_paths.append(
            {
                "student_id": student_id,
                "target": target,
                "steps": steps,
            }
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    state_doc = {
        "schema_version": "1.0",
        "course_id": course_id,
        "students": student_states,
    }
    path_doc = {
        "schema_version": "1.0",
        "course_id": course_id,
        "paths": learning_paths,
    }

    write_json(out_dir / "student_state.json", state_doc)
    write_json(out_dir / "learning_path.json", path_doc)

    print(
        f"Generated {len(student_states)} student states "
        f"and {len(learning_paths)} learning paths -> {out_dir}"
    )


if __name__ == "__main__":
    main()
