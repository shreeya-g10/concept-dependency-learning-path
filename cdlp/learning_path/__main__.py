"""Run simulated diagnosis and write contract-compliant student outputs."""
import argparse
import random
from pathlib import Path
from cdlp.shared.io import read_json, write_json
from cdlp.learning_path.api import prerequisite_order, next_question, update_mastery, personalized_path


def simulate(graph, quiz, students, target, budget=5, seed=42):
    rng = random.Random(seed)
    states, paths = [], []
    for student in students['students']:
        # The simulated student's true mastery is used ONLY to generate answers,
        # never as an input to the diagnostic model.
        truth = student['mastery']
        mastery = {c: 0.5 for c in prerequisite_order(graph, target)}
        answers = []
        for _ in range(budget):
            question = next_question(graph, quiz, {**mastery, '__asked__': [a['item_id'] for a in answers]}, target)
            if question is None:
                break
            c = question['concept_id']
            chance = float(truth.get(c, 0.5)) * (1-float(student.get('slip', .1))) + (1-float(truth.get(c, .5))) * float(student.get('guess', .2))
            correct = rng.random() < chance
            mastery = update_mastery(graph, mastery, c, correct)
            answers.append({'item_id': question['id'], 'correct': correct})
        states.append({'student_id': student['student_id'], 'target': target, 'mastery': mastery, 'questions_asked': len(answers), 'answers': answers})
        paths.append({'student_id': student['student_id'], 'target': target, 'steps': personalized_path(graph, mastery, target)})
    return states, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('graph', 'quiz', 'students'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=5)
    args = parser.parse_args()
    graph, quiz, students = (read_json(getattr(args, k)) for k in ('graph', 'quiz', 'students'))
    states, paths = simulate(graph, quiz, students, args.target, args.budget)
    write_json(args.out_dir / 'student_state.json', {'schema_version': '1.0', 'course_id': graph['course_id'], 'students': states})
    write_json(args.out_dir / 'learning_path.json', {'schema_version': '1.0', 'course_id': graph['course_id'], 'paths': paths})
    print(f'Generated {len(states)} student states and {len(paths)} personalized paths')

if __name__ == '__main__':
    main()
