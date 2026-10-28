
"""CLI for generating student states and personalized learning paths."""

import argparse
from pathlib import Path

from cdlp.shared.io import read_json, write_json
from cdlp.learning_path import api


def main():
    parser = argparse.ArgumentParser(
        description="Generate adaptive learning paths for simulated students."
    )
    parser.add_argument(
        "--graph",
        default="cdlp/shared/examples/validated_graph.json",
    )
    parser.add_argument(
        "--quiz",
        default="cdlp/shared/examples/quiz_items.json",
    )
    parser.add_argument(
        "--students",
        default="cdlp/shared/examples/sim_students.json",
    )
    parser.add_argument("--out", default="outputs")
    args = parser.parse_args()

    graph = read_json(Path(args.graph))
    quiz = read_json(Path(args.quiz))
    students_data = read_json(Path(args.students))

    students = (
        students_data
        if isinstance(students_data, list)
        else students_data.get("students", [])
    )

    states = []
    paths = []

    for student in students:
        student_id = student["id"]
        true_mastery = student.get("mastery", {})
        target = student.get("target", "avl_tree")

        mastery = {
            concept: 0.5
            for concept in api.prerequisite_order(graph, target)
        }

        answers = []
        asked_ids = []

        for _ in range(10):
            question = api.next_question(
                graph,
                quiz,
                {**mastery, "__asked__": asked_ids},
                target,
            )

            if question is None:
                break

            concept = question["concept_id"]
            correct = true_mastery.get(concept, 0.5) > 0.5

            mastery = api.update_mastery(
                graph, mastery, concept, correct
            )

            asked_ids.append(question["id"])
            answers.append(
                {
                    "item_id": question["id"],
                    "correct": correct,
                }
            )

        states.append(
            {
                "student_id": student_id,
                "target": target,
                "mastery": mastery,
                "answers": answers,
            }
        )

        paths.append(
            {
                "student_id": student_id,
                "target": target,
                "steps": api.personalized_path(
                    graph, mastery, target
                ),
            }
        )

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    write_json(output_dir / "student_state.json", {"students": states})
    write_json(output_dir / "learning_path.json", {"paths": paths})

    print(
        f"Generated {len(states)} student states "
        f"and {len(paths)} personalized paths"
    )


if __name__ == "__main__":
    main()
