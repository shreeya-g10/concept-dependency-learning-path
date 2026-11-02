"""Evaluation and experimental benchmarking for RQ2 and RQ4.

Owner: Vaidehi (inherited from Shrestha).
Measures:
- RQ2: Adaptive diagnosis vs Ask-Every-Concept vs Random-Order on 500 simulated students.
- RQ4: Personalized paths vs Generic baseline paths (length, gap coverage, order mistakes).
- Second question: adaptive diagnosis with and without a second question after a right answer
  (results in rq2_second_question.json; SECOND_QUESTION_RULE says when it is kept).

Usage:
    python -m cdlp.learning_path.evaluate
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from cdlp.learning_path import api
from cdlp.learning_path.graph import (
    MASTERY_THRESHOLD,
    ancestors,
    generic_path,
    is_mastered,
    load_graph,
)
from cdlp.learning_path.sim_students import (
    generate_independent_students,
    generate_simulated_students,
)
from cdlp.shared.io import EXAMPLES, read_json

RESULTS_DIR = Path("cdlp/learning_path/results")


def simulate_student_answer(
    rng: random.Random,
    true_mastery: float,
    slip: float = 0.10,
    guess: float = 0.15,
) -> bool:
    """Simulate a noisy student answer given their true latent mastery."""
    if is_mastered(true_mastery):
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
    max_questions: int = api.MAX_QUESTIONS_PER_TOPIC,
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


def _item_id(item: dict) -> str:
    return item.get("id", item.get("item_id"))


def run_second_question_diagnosis(
    graph_data: dict,
    quiz_items: list[dict],
    true_states: dict[str, float],
    target: str,
    max_questions: int = api.MAX_QUESTIONS_PER_TOPIC,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], int]:
    """Adaptive diagnosis, plus a second question on a concept after a right answer.

    One lucky guess should not mark a concept as known. The second question is asked only when
    the concept has another unasked item and the question limit allows it; the latest direct
    answer wins (api.update_mastery), so right then wrong ends as not known.
    """
    rng = rng or random.Random(42)
    mastery: dict[str, float] = {}
    asked: list[str] = []

    def ask(item: dict) -> bool:
        nonlocal mastery
        concept = item.get("concept_id", "")
        correct = simulate_student_answer(rng, true_states.get(concept, 0.5))
        mastery = api.update_mastery(graph_data, mastery, concept, correct)
        asked.append(_item_id(item))
        return correct

    while len(asked) < max_questions:
        first = api.next_question(graph_data, quiz_items, {**mastery, "__asked__": asked}, target)
        if not first:
            break
        if not ask(first) or len(asked) >= max_questions:
            continue
        second = next(
            (
                item
                for item in quiz_items
                if item.get("concept_id") == first.get("concept_id") and _item_id(item) not in asked
            ),
            None,
        )
        if second:
            ask(second)

    return mastery, len(asked)


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


def evaluate_accuracy(
    estimated: dict[str, float],
    ground_truth: dict[str, float],
    concepts: list[str] | None = None,
) -> float:
    """Share of concepts whose estimated mastered / not-mastered matches the truth.

    `concepts` fixes the scored set so every strategy is scored on the same concepts
    (evaluate_rq2_and_rq4 passes the target's prerequisite path); a concept a strategy
    never estimated counts at the prior 0.5, i.e. not mastered. Without `concepts`, the
    concepts present in both dicts are scored (the old behaviour).
    """
    if concepts is None:
        concepts = [c for c in ground_truth if c in estimated]
    if not concepts:
        return 1.0
    hits = sum(
        is_mastered(estimated.get(c, 0.5)) == is_mastered(ground_truth.get(c, 0.5))
        for c in concepts
    )
    return hits / len(concepts)


def closure_violations(graph_data: dict, students: list[dict], concepts: list[str]) -> float:
    """Share of students who master some concept without mastering all its prerequisites."""
    G = load_graph(graph_data)

    def violates(m: dict) -> bool:
        return any(
            is_mastered(m.get(c, 0.5)) and not is_mastered(m.get(a, 0.5))
            for c in concepts
            for a in ancestors(G, c)
        )

    return sum(violates(s.get("mastery", {})) for s in students) / max(len(students), 1)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_rq2_and_rq4(
    graph_data: dict,
    quiz_items: list[dict],
    simulated_students: list[dict],
    target: str = "avl_tree",
    seed: int = 42,
) -> dict[str, Any]:
    """RQ2 (diagnosis) and RQ4 (paths) on one population of simulated students.

    Fairness: every strategy uses the same estimator (api.update_mastery), the same
    answer model (simulate_student_answer) and is scored on the same concepts (the
    target's prerequisite path). Each strategy draws answers from its own random stream
    per student (seeded by seed, student index and strategy), so results do not depend
    on the order in which strategies run.
    """
    G = load_graph(graph_data)
    path = generic_path(G, target)
    stats: dict[str, dict[str, list]] = {
        k: {"q": [], "acc": []} for k in ("adaptive", "ask_all", "random")
    }
    personalized_lengths, gap_coverages, order_mistakes = [], [], []

    for i, student in enumerate(simulated_students):
        truth = student.get("mastery", {})

        def stream(name: str, i: int = i) -> random.Random:
            return random.Random(f"{seed}:{i}:{name}")

        est_ad, q_ad = run_adaptive_diagnosis(
            graph_data, quiz_items, truth, target, rng=stream("adaptive")
        )
        est_all, q_all = run_ask_all_diagnosis(
            graph_data, quiz_items, truth, target, rng=stream("ask_all")
        )
        est_rnd, q_rnd = run_random_diagnosis(
            graph_data, quiz_items, truth, target, budget=q_ad, rng=stream("random")
        )
        for name, est, q in [
            ("adaptive", est_ad, q_ad),
            ("ask_all", est_all, q_all),
            ("random", est_rnd, q_rnd),
        ]:
            stats[name]["q"].append(q)
            stats[name]["acc"].append(evaluate_accuracy(est, truth, path))

        # RQ4: path from the adaptive estimate
        steps = api.personalized_path(graph_data, est_ad, target)
        personalized_lengths.append(len(steps))
        unmastered = {c for c in path if not is_mastered(truth.get(c, 0.5))}
        covered = unmastered & {s["concept_id"] for s in steps}
        gap_coverages.append(len(covered) / len(unmastered) if unmastered else 1.0)
        indices = [path.index(s["concept_id"]) for s in steps]
        order_mistakes.append(sum(a > b for a, b in zip(indices, indices[1:], strict=False)))

    q_all_total = sum(stats["ask_all"]["q"])
    diagnosis = {
        name: {"avg_questions": _mean(v["q"]), "accuracy": round(_mean(v["acc"]), 4)}
        for name, v in stats.items()
    }
    diagnosis["question_reduction_pct"] = (
        round((q_all_total - sum(stats["adaptive"]["q"])) / q_all_total * 100, 2)
        if q_all_total
        else 0.0
    )
    diagnosis["students_violating_closure"] = round(
        closure_violations(graph_data, simulated_students, path), 4
    )
    generic_len = len(path)
    return {
        "num_students": len(simulated_students),
        "target_concept": target,
        "mastery_threshold": MASTERY_THRESHOLD,
        "scored_concepts": path,
        "rq2_diagnosis": diagnosis,
        "rq4_learning_path": {
            "generic_avg_length": float(generic_len),
            "personalized_avg_length": _mean(personalized_lengths),
            "path_length_reduction_pct": (
                round((generic_len - _mean(personalized_lengths)) / generic_len * 100, 2)
                if generic_len
                else 0.0
            ),
            "avg_gap_coverage": round(_mean(gap_coverages), 4),
            "total_order_mistakes": sum(order_mistakes),
        },
    }


CONDITIONS = {
    # main condition: knowledge respects the graph (with slip/guess noise in the truth)
    "graph_consistent": generate_simulated_students,
    # robustness: each concept mastered independently, ignoring the graph
    "graph_independent": generate_independent_students,
}


# Fixed before the strategy was first run. The second question is kept only if all three hold.
SECOND_QUESTION_RULE = [
    "with a second question available, accuracy rises in both student conditions, and the "
    "95% paired bootstrap interval of the rise is above 0 in both",
    "with a second question available, topics wrongly marked as known fall in both conditions",
    "in the graph-consistent condition it still asks fewer questions than asking every concept "
    "once; otherwise the saving that adaptive diagnosis exists for is gone",
]


def with_second_items(quiz_items: list[dict]) -> list[dict]:
    """Add one placeholder second item per concept. Only for the simulation.

    The example quiz has one item per concept, so the strategy has nothing to ask there. The
    simulated answer depends on the concept, not on the question text, so a placeholder is
    enough. It answers "what if a second item existed", on the example graph only.
    """
    return [*quiz_items, *({**item, "id": f"{_item_id(item)}__second"} for item in quiz_items)]


def _student_scores(
    graph_data: dict, estimate: dict, questions: int, truth: dict, target: str, path: list[str]
) -> dict[str, float]:
    known = {c for c in path if is_mastered(truth.get(c, 0.5))}
    gaps = set(path) - known
    believed = {c for c in path if is_mastered(estimate.get(c, 0.5))}
    planned = {s["concept_id"] for s in api.personalized_path(graph_data, estimate, target)}
    return {
        "questions": questions,
        "accuracy": evaluate_accuracy(estimate, truth, path),
        "wrongly_known": len(believed & gaps) / len(gaps) if gaps else 0.0,
        "path_length": len(planned),
        "gap_coverage": len(gaps & planned) / len(gaps) if gaps else 1.0,
    }


def _paired_interval(diffs: list[float], seed: int, rounds: int = 2000) -> list[float]:
    """95% bootstrap interval of the mean paired difference (resampling students)."""
    rng = random.Random(f"{seed}:bootstrap")
    means = sorted(_mean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return [round(means[int(rounds * 0.025)], 4), round(means[int(rounds * 0.975)], 4)]


def compare_second_question(
    graph_data: dict,
    quiz_items: list[dict],
    students: list[dict],
    target: str = "avl_tree",
    seed: int = 42,
) -> dict[str, Any]:
    """Adaptive with and without the second question, on the same students and answer model."""
    path = generic_path(load_graph(graph_data), target)
    runs = {"without": run_adaptive_diagnosis, "with": run_second_question_diagnosis}
    scores: dict[str, list[dict[str, float]]] = {name: [] for name in runs}
    for i, student in enumerate(students):
        truth = student.get("mastery", {})
        for name, run in runs.items():
            # The same stream as the main adaptive run, for both: "without" reproduces the
            # main table, and with one item per concept the two arms match exactly.
            rng = random.Random(f"{seed}:{i}:adaptive")
            estimate, questions = run(graph_data, quiz_items, truth, target, rng=rng)
            scores[name].append(
                _student_scores(graph_data, estimate, questions, truth, target, path)
            )
    summary: dict[str, Any] = {
        name: {
            metric: round(_mean([row[metric] for row in rows]), 4)
            for metric in ("questions", "accuracy", "wrongly_known", "path_length", "gap_coverage")
        }
        for name, rows in scores.items()
    }
    diffs = [
        a["accuracy"] - b["accuracy"]
        for a, b in zip(scores["with"], scores["without"], strict=True)
    ]
    summary["accuracy_change"] = round(_mean(diffs), 4)
    summary["accuracy_change_95"] = _paired_interval(diffs, seed)
    return summary


def second_question_results(graph_data: dict, quiz_items: list[dict], seed: int = 42) -> dict:
    """Both item sets and both student conditions, with the rule's verdict."""
    item_sets = {
        "example_items_as_they_are": quiz_items,
        "with_a_placeholder_second_item": with_second_items(quiz_items),
    }
    results: dict[str, Any] = {}
    ask_all: dict[str, float] = {}
    for item_name, items in item_sets.items():
        results[item_name] = {}
        for condition, make in CONDITIONS.items():
            students = make(graph_data, num_students=500, seed=seed)["students"]
            row = compare_second_question(graph_data, items, students, seed=seed)
            row["other_answer_seeds_accuracy_change"] = {
                str(other): compare_second_question(graph_data, items, students, seed=other)[
                    "accuracy_change"
                ]
                for other in range(seed + 1, seed + 5)
            }
            results[item_name][condition] = row
            diagnosis = evaluate_rq2_and_rq4(graph_data, items, students)["rq2_diagnosis"]
            ask_all[condition] = diagnosis["ask_all"]["avg_questions"]

    tested = results["with_a_placeholder_second_item"]
    checks = [
        all(tested[c]["accuracy_change_95"][0] > 0 for c in CONDITIONS),
        all(
            tested[c]["with"]["wrongly_known"] < tested[c]["without"]["wrongly_known"]
            for c in CONDITIONS
        ),
        tested["graph_consistent"]["with"]["questions"] < ask_all["graph_consistent"],
    ]
    return {
        "config": {
            "graph": "cdlp/shared/examples/validated_graph.json",
            "quiz_items": "cdlp/shared/examples/quiz_items.json",
            "target": "avl_tree",
            "concepts_on_path": 5,
            "num_students": 500,
            "seed": seed,
            "slip": 0.10,
            "guess": 0.15,
            "max_questions": api.MAX_QUESTIONS_PER_TOPIC,
            "uses_llm": False,
        },
        "ask_all_questions": ask_all,
        "rule": SECOND_QUESTION_RULE,
        "rule_checks": checks,
        "keep": all(checks),
        **results,
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    graph_data = read_json(EXAMPLES / "validated_graph.json")
    # Quiz items for the example graph (hand-written ds101 items, one per concept)
    quiz_items = read_json(EXAMPLES / "quiz_items.json")["items"]

    runs = {}
    for name, make in CONDITIONS.items():
        students = make(graph_data, num_students=500, seed=42)["students"]
        runs[name] = evaluate_rq2_and_rq4(graph_data, quiz_items, students, target="avl_tree")

    main_run = runs["graph_consistent"]
    results = {
        **{k: main_run[k] for k in ("num_students", "target_concept", "mastery_threshold")},
        "seed": 42,
        "scored_concepts": main_run["scored_concepts"],
        "rq2_diagnosis": main_run["rq2_diagnosis"],
        "rq4_learning_path": main_run["rq4_learning_path"],
        "rq2_diagnosis_independent": runs["graph_independent"]["rq2_diagnosis"],
        "rq4_learning_path_independent": runs["graph_independent"]["rq4_learning_path"],
        "conditions": {
            "graph_consistent": "generate_simulated_students: knowledge closed under the "
            "graph (frontier sampler) plus slip/guess noise in the true mastery",
            "graph_independent": "generate_independent_students: each concept mastered "
            "independently with p = 0.5, ignoring the graph",
        },
    }
    out_file = RESULTS_DIR / "rq2_rq4_results.json"
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    for name, run in runs.items():
        d = run["rq2_diagnosis"]
        print(f"[{name}] closure violated by {d['students_violating_closure']:.0%} of students")
        for k in ("adaptive", "ask_all", "random"):
            print(
                f"  {k:9s} {d[k]['avg_questions']:.2f} questions, accuracy {d[k]['accuracy']:.3f}"
            )
        print(f"  question reduction vs ask-all: {d['question_reduction_pct']:.1f}%")
    print(f"Results saved to: {out_file}")

    second = second_question_results(graph_data, quiz_items)
    second_file = RESULTS_DIR / "rq2_second_question.json"
    second_file.write_text(json.dumps(second, indent=2) + "\n", encoding="utf-8")
    print(f"Second question, rule checks {second['rule_checks']}, keep: {second['keep']}")
    print(f"Results saved to: {second_file}")


if __name__ == "__main__":
    main()
