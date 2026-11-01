"""learning_path — graph + quiz -> sim_students.json + student_state.json + learning_path.json

Owner: Vaidehi (inherited from Shrestha).
Usage:
    python -m cdlp.learning_path --graph outputs/validated_graph.json \
        --quiz outputs/quiz_items.json --out-dir outputs
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cdlp.learning_path import api
from cdlp.learning_path.sim_students import generate_simulated_students
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
        default=None,
        help="path to sim_students.json (if omitted or not found, generated from validated graph)",
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
    parser.add_argument(
        "--num-students",
        type=int,
        default=50,
        help="number of simulated students to generate",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = read_json(args.graph)
    quiz = read_json(args.quiz)

    course_id = graph.get("course_id") or "ds101"

    # Always ensure sim_students.json is generated from ACCEPT edges in validated_graph.json
    sim_students_out = out_dir / "sim_students.json"
    students_data = None
    if args.students and Path(args.students).exists() and Path(args.students) != sim_students_out:
        try:
            loaded = read_json(args.students)
            if isinstance(loaded, dict) and "students" in loaded and loaded["students"]:
                students_data = loaded
        except Exception:
            students_data = None

    if students_data is None:
        students_data = generate_simulated_students(
            graph,
            num_students=args.num_students,
            course_id=course_id,
        )

    # Save sim_students.json to output directory
    write_json(sim_students_out, students_data)

    students = (
        students_data if isinstance(students_data, list) else students_data.get("students", [])
    )

    student_states = []
    learning_paths = []

    for student in students:
        student_id = student.get("student_id") or student.get("id", "s01")
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
                    "concept_id": concept,
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
