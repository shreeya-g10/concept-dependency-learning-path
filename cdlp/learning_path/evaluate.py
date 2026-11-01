"""Evaluation and experimental benchmarking for RQ2 and RQ4.

Owner: Vaidehi (inherited from Shrestha).
Measures:
- RQ2: Adaptive diagnosis vs Ask-Every-Concept vs Random-Order on 500 simulated students.
- RQ4: Personalized paths vs Generic baseline paths (length, gap coverage, order mistakes).

Usage:
    python -m cdlp.learning_path.evaluate
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from cdlp.discovery.quiz import get_quiz_items
from cdlp.discovery.sim_students import generate_simulated_students
from cdlp.learning_path import api
from cdlp.learning_path.graph import generic_path, load_graph
from cdlp.shared.io import EXAMPLES, read_json

RESULTS_DIR = Path("cdlp/learning_path/results")


def simulate_student_answer(
    rng: random.Random,
    true_mastery: float,
    slip: float = 0.10,
    guess: float = 0.15,
) -> bool:
    """Simulate a noisy student answer given their true latent mastery."""
    if true_mastery >= 0.7:
        # High mastery: correct unless slip
        return rng.random() > slip
    else:
        # Low mastery: incorrect unless lucky guess
        return rng.random() < guess


def run_adaptive_diagnosis(
    graph_data: dict,
    quiz_items: list[dict],
    true_states: dict[str, float],
    target: str,
    max_questions: int = 10,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], int]:
    """Run adaptive graph-guided diagnosis."""
    rng = rng or random.Random(42)
    mastery: dict[str, float] = {}
    questions_asked = 0

    while questions_asked < max_questions:
        q = api.next_question(graph_data, quiz_items, mastery, target)
        if not q:
            break

        c_id = q.get("concept_id", "")
        true_m = true_states.get(c_id, 0.5)
        is_correct = simulate_student_answer(rng, true_m)

        mastery = api.update_mastery(graph_data, mastery, c_id, is_correct)
        questions_asked += 1

    return mastery, questions_asked


def run_ask_all_diagnosis(
    graph_data: dict,
    quiz_items: list[dict],
    true_states: dict[str, float],
    target: str,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], int]:
    """Run baseline diagnosis asking about every prerequisite."""
    rng = rng or random.Random(42)
    G = load_graph(graph_data)
    order = generic_path(G, target)
    mastery: dict[str, float] = {}
    questions_asked = 0

    for concept in order:
        q = next((item for item in quiz_items if item.get("concept_id") == concept), None)
        if not q:
            continue

        true_m = true_states.get(concept, 0.5)
        is_correct = simulate_student_answer(rng, true_m)
        mastery = api.update_mastery(graph_data, mastery, concept, is_correct)
        questions_asked += 1

    return mastery, questions_asked


def run_random_diagnosis(
    graph_data: dict,
    quiz_items: list[dict],
    true_states: dict[str, float],
    target: str,
    budget: int = 5,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], int]:
    """Run baseline diagnosis asking random questions."""
    rng = rng or random.Random(42)
    G = load_graph(graph_data)
    prereqs = set(generic_path(G, target))
    relevant_items = [q for q in quiz_items if q.get("concept_id") in prereqs]
    shuffled = list(relevant_items)
    rng.shuffle(shuffled)

    mastery: dict[str, float] = {}
    questions_asked = 0

    for q in shuffled[:budget]:
        c_id = q.get("concept_id", "")
        true_m = true_states.get(c_id, 0.5)
        is_correct = simulate_student_answer(rng, true_m)
        mastery = api.update_mastery(graph_data, mastery, c_id, is_correct)
        questions_asked += 1

    return mastery, questions_asked


def evaluate_accuracy(estimated: dict[str, float], ground_truth: dict[str, float]) -> float:
    """Compute binary classification accuracy between estimated and true mastery."""
    correct = 0
    total = 0
    for concept, true_val in ground_truth.items():
        if concept in estimated:
            est_known = estimated[concept] >= 0.7
            true_known = true_val >= 0.7
            if est_known == true_known:
                correct += 1
            total += 1
    return (correct / total) if total > 0 else 1.0


def evaluate_rq2_and_rq4(
    graph_data: dict,
    quiz_items: list[dict],
    simulated_students: list[dict],
    target: str = "avl_tree",
) -> dict[str, Any]:
    """Run experiments for Research Questions 2 and 4."""
    rng = random.Random(42)

    adaptive_q_counts = []
    adaptive_accs = []
    ask_all_q_counts = []
    ask_all_accs = []
    random_q_counts = []
    random_accs = []

    personalized_lengths = []
    generic_lengths = []
    gap_coverages = []
    order_mistakes = []

    G = load_graph(graph_data)
    baseline_generic = generic_path(G, target)
    generic_len = len(baseline_generic)

    for student in simulated_students:
        true_states = student.get("mastery", {})

        # RQ2: Adaptive
        est_ad, q_ad = run_adaptive_diagnosis(graph_data, quiz_items, true_states, target, rng=rng)
        adaptive_q_counts.append(q_ad)
        adaptive_accs.append(evaluate_accuracy(est_ad, true_states))

        # RQ2: Ask All
        est_all, q_all = run_ask_all_diagnosis(graph_data, quiz_items, true_states, target, rng=rng)
        ask_all_q_counts.append(q_all)
        ask_all_accs.append(evaluate_accuracy(est_all, true_states))

        # RQ2: Random (matched budget to adaptive)
        est_rnd, q_rnd = run_random_diagnosis(
            graph_data, quiz_items, true_states, target, budget=q_ad, rng=rng
        )
        random_q_counts.append(q_rnd)
        random_accs.append(evaluate_accuracy(est_rnd, true_states))

        # RQ4: Personalized Path
        pers_path = api.personalized_path(graph_data, est_ad, target)
        pers_len = len(pers_path)
        personalized_lengths.append(pers_len)
        generic_lengths.append(generic_len)

        # Check gap coverage: are all truly unmastered concepts in the path?
        unmastered = {c for c, m in true_states.items() if m < 0.7 and c in baseline_generic}
        path_concepts = {step["concept_id"] for step in pers_path}
        covered = len(unmastered & path_concepts)
        gap_coverages.append(covered / len(unmastered) if unmastered else 1.0)

        # Check topological ordering
        indices = [baseline_generic.index(step["concept_id"]) for step in pers_path]
        mistakes = sum(1 for i in range(len(indices) - 1) if indices[i] > indices[i + 1])
        order_mistakes.append(mistakes)

    n = len(simulated_students)
    return {
        "num_students": n,
        "target_concept": target,
        "rq2_diagnosis": {
            "adaptive": {
                "avg_questions": sum(adaptive_q_counts) / n,
                "accuracy": sum(adaptive_accs) / n,
            },
            "ask_all": {
                "avg_questions": sum(ask_all_q_counts) / n,
                "accuracy": sum(ask_all_accs) / n,
            },
            "random": {
                "avg_questions": sum(random_q_counts) / n,
                "accuracy": sum(random_accs) / n,
            },
            "question_reduction_pct": (
                (sum(ask_all_q_counts) - sum(adaptive_q_counts)) / sum(ask_all_q_counts) * 100
                if sum(ask_all_q_counts) > 0
                else 0.0
            ),
        },
        "rq4_learning_path": {
            "generic_avg_length": sum(generic_lengths) / n,
            "personalized_avg_length": sum(personalized_lengths) / n,
            "path_length_reduction_pct": (
                (sum(generic_lengths) - sum(personalized_lengths)) / sum(generic_lengths) * 100
                if sum(generic_lengths) > 0
                else 0.0
            ),
            "avg_gap_coverage": sum(gap_coverages) / n,
            "total_order_mistakes": sum(order_mistakes),
        },
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    graph_data = read_json(EXAMPLES / "validated_graph.json")

    # Generate 500 simulated students
    sim_data = generate_simulated_students(graph_data, num_students=500, seed=42)
    students = sim_data["students"]

    # Load quiz items
    quiz_data = get_quiz_items(course_id="ds101")
    quiz_items = quiz_data["items"]

    results = evaluate_rq2_and_rq4(graph_data, quiz_items, students, target="avl_tree")

    out_file = RESULTS_DIR / "rq2_rq4_results.json"
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print("=" * 60)
    print("EXPERIMENT RESULTS: RQ2 & RQ4 (500 Simulated Students)")
    print("=" * 60)
    print(f"Target Concept: {results['target_concept']}")
    print(f"Simulated Students: {results['num_students']}")
    print("\n--- RQ2: Adaptive Diagnosis Comparison ---")
    diag = results["rq2_diagnosis"]
    print(
        f"Adaptive:   {diag['adaptive']['avg_questions']:.1f} questions, "
        f"{diag['adaptive']['accuracy']:.1%} accuracy"
    )
    print(
        f"Ask-All:    {diag['ask_all']['avg_questions']:.1f} questions, "
        f"{diag['ask_all']['accuracy']:.1%} accuracy"
    )
    print(
        f"Random:     {diag['random']['avg_questions']:.1f} questions, "
        f"{diag['random']['accuracy']:.1%} accuracy"
    )
    print(f"Question Reduction vs Ask-All: {diag['question_reduction_pct']:.1f}%")

    print("\n--- RQ4: Personalized vs Generic Paths ---")
    path_res = results["rq4_learning_path"]
    print(f"Generic Path Average Length:      {path_res['generic_avg_length']:.1f} steps")
    print(f"Personalized Path Average Length:  {path_res['personalized_avg_length']:.1f} steps")
    print(f"Path Length Reduction:            {path_res['path_length_reduction_pct']:.1f}%")
    print(f"Knowledge Gap Coverage:           {path_res['avg_gap_coverage']:.1%}")
    print(f"Total Topological Order Mistakes: {path_res['total_order_mistakes']}")
    print("=" * 60)
    print(f"Results saved to: {out_file}")


if __name__ == "__main__":
    main()
