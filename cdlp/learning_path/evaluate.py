"""RQ2: reproducible simulated comparison of adaptive, random and exhaustive quiz policies."""
import argparse
import csv
import random
from pathlib import Path
from cdlp.shared.io import read_json
from cdlp.learning_path.api import prerequisite_order, next_question, update_mastery


def evaluate(graph, quiz, students, target, repeats=100, seed=42):
    required = prerequisite_order(graph, target)
    items = [q for q in quiz['items'] if q['concept_id'] in required]
    rows = []
    for method in ('adaptive', 'random', 'exhaustive'):
        for budget in range(len(items) + 1):
            errors, correct_class, total = [], 0, 0
            for rep in range(repeats):
                for student in students['students']:
                    rng = random.Random(seed + rep * 100003 + sum(ord(c) for c in student['student_id']))
                    truth = student['mastery']
                    mastery = {c: .5 for c in required}
                    asked = []
                    ordered = list(items)
                    if method == 'random':
                        rng.shuffle(ordered)
                    for _ in range(budget):
                        if method == 'adaptive':
                            item = next_question(graph, quiz, {**mastery, '__asked__': asked}, target)
                        else:
                            item = next((q for q in ordered if q['id'] not in asked), None)
                        if item is None:
                            break
                        c = item['concept_id']
                        true = float(truth.get(c, .5))
                        probability = true * (1-float(student.get('slip', .1))) + (1-true) * float(student.get('guess', .2))
                        mastery = update_mastery(graph, mastery, c, rng.random() < probability)
                        asked.append(item['id'])
                    for c in required:
                        actual = float(truth.get(c, .5))
                        predicted = mastery[c]
                        errors.append(abs(actual-predicted))
                        correct_class += int((predicted >= .8) == (actual >= .8))
                        total += 1
            rows.append({'method': method, 'question_budget': budget, 'mae': round(sum(errors)/len(errors), 5), 'classification_accuracy': round(correct_class/total, 5), 'trials': repeats * len(students['students'])})
    return rows


def main():
    parser = argparse.ArgumentParser()
    for name in ('graph', 'quiz', 'students'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--target', default='avl_tree')
    parser.add_argument('--repeats', type=int, default=100)
    parser.add_argument('--out', type=Path, default=Path('cdlp/learning_path/results/rq2_accuracy.csv'))
    args = parser.parse_args()
    rows = evaluate(*(read_json(getattr(args, n)) for n in ('graph','quiz','students')), args.target, args.repeats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} rows to {args.out}')

if __name__ == '__main__':
    main()
