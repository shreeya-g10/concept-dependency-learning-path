"""Evaluation and experimental benchmarking for RQ2 and RQ4.

Owner: Vaidehi (inherited from Shrestha).
Measures:
- RQ2: Adaptive diagnosis vs Ask-Every-Concept vs Random-Order on 500 simulated students.
- RQ4: Personalized paths vs Generic baseline paths (length, gap coverage, order mistakes).

Usage:
    python -m cdlp.learning_path.evaluate
    python -m cdlp.learning_path.evaluate --ladder   # level ladder, its own results file
"""

from __future__ import annotations

import json
import random
import sys
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
LADDER_CONFIG = Path(__file__).parent / "configs" / "ladder_eval.json"
LADDER_STRATEGIES = ("ladder_linear", "ladder_middle")


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


# ---- level ladder: a separate comparison, written to ladder_comparison.json -----------------

LADDER_ASSUMPTIONS = [
    "Simulated difficulty is not real difficulty: the chance of a right answer per level is chosen "
    "in configs/ladder_eval.json, not measured from students. The medium row equals the old answer "
    "model (slip 0.10, guess 0.15). Nothing here shows that AI-labelled hard questions are harder.",
    "Self-report is chosen too: yes_if_known and yes_if_not_known in the config, and a student who "
    "does not say yes picks No or Not sure at random. Both start at easy.",
    "A student's knowledge of a topic is two states, known or not known, from true mastery above "
    "0.8. Real knowledge has degrees, so Quick revision and Study this cannot be scored as such: "
    "both count as not known.",
    "Answers are independent given the topic and level, so a right answer on a topic does not make "
    "the next one likelier. A real student's answers are linked, so the benefit of asking a second "
    "or third question is probably an upper limit.",
    "Placeholder quiz items: one easy, medium and hard item per topic, with no real text. Real "
    "courses will have missing levels; no_hard_items shows the worst case.",
    "The example graph: 5 topics on the target's path. Rerun on real course graphs before citing.",
    "Mastery values per result (0.9, 0.7, 0.4, 0.1) only place Know it above the 0.8 threshold. "
    "They are a design choice, not calibrated probabilities.",
    "adaptive_levelled uses the same answer model and items as the ladders, and asks items in file "
    "order, so easy first. adaptive is the existing strategy on the existing quiz and answer "
    "model.",
    "A question is one quiz question. Self-report taps are counted apart.",
]


def placeholder_ladder_items(graph_data: dict, target: str, drop_levels=()) -> list[dict]:
    """One item per level per topic on the target's path. No real text: placeholders only."""
    return [
        {
            "id": f"placeholder_{concept}_{level}",
            "concept_id": concept,
            "question": f"(placeholder {level} question on {concept})",
            "options": ["right", "wrong"],
            "answer": "right",
            "difficulty": level,
        }
        for concept in generic_path(load_graph(graph_data), target)
        for level in ("easy", "medium", "hard")
        if level not in drop_levels
    ]


def simulate_level_answer(rng: random.Random, true_mastery: float, level: str, model: dict) -> bool:
    """A right answer's chance depends on whether the topic is known and on the item's level."""
    return rng.random() < model["known" if is_mastered(true_mastery) else "not_known"][level]


def simulate_self_report(rng: random.Random, true_mastery: float, model: dict) -> str:
    key = "yes_if_known" if is_mastered(true_mastery) else "yes_if_not_known"
    return "yes" if rng.random() < model[key] else rng.choice(["no", "not_sure"])


def run_ladder_diagnosis(
    graph_data: dict,
    items: list[dict],
    truth: dict[str, float],
    target: str,
    strategy: str,
    rng: random.Random,
    cfg: dict,
) -> tuple[dict, int, int]:
    """(mastery, quiz questions, self-report taps) for one simulated student."""
    mastery: dict = {}
    questions = reports = 0
    while True:
        step = api.ladder_next(graph_data, items, mastery, target, strategy)
        if step is None:
            return mastery, questions, reports
        if "self_report" in step:
            concept = step["self_report"]
            answer = simulate_self_report(rng, truth.get(concept, 0.5), cfg["self_report"])
            mastery = api.ladder_self_report(mastery, concept, answer)
            reports += 1
            continue
        level = step.get("difficulty", "easy")
        correct = simulate_level_answer(
            rng, truth.get(step["concept_id"], 0.5), level, cfg["answer_model"]
        )
        mastery = api.ladder_record(graph_data, items, mastery, target, step, correct, strategy)
        questions += 1


def run_adaptive_levelled(
    graph_data: dict,
    items: list[dict],
    truth: dict[str, float],
    target: str,
    rng: random.Random,
    cfg: dict,
) -> tuple[dict, int]:
    """The current adaptive selection, on the ladders' items and answer model."""
    mastery: dict = {}
    asked: list = []
    while len(asked) < api.MAX_QUESTIONS_PER_TOPIC:
        item = api.next_question(graph_data, items, {**mastery, "__asked__": asked}, target)
        if not item:
            break
        correct = simulate_level_answer(
            rng, truth.get(item["concept_id"], 0.5), item["difficulty"], cfg["answer_model"]
        )
        mastery = api.update_mastery(graph_data, mastery, item["concept_id"], correct)
        asked.append(item["id"])
    return mastery, len(asked)


def _plan_scores(
    graph_data: dict, estimate: dict, truth: dict, path: list[str], target: str
) -> dict:
    """The same scores for every strategy. Every number is about the target's path."""
    steps = {s["concept_id"] for s in api.personalized_path(graph_data, estimate, target)}
    gaps = {c for c in path if not is_mastered(truth.get(c, 0.5))}
    known = set(path) - gaps
    return {
        "accuracy": evaluate_accuracy(estimate, truth, path),
        # The share of this student's gaps we call known. No gaps counts as none wrong.
        "wrongly_known": (
            sum(is_mastered(estimate.get(c, 0.5)) for c in gaps) / len(gaps) if gaps else 0.0
        ),
        "gap_coverage": len(gaps & steps) / len(gaps) if gaps else 1.0,
        "path_length": len(steps),
        "known_topics_on_plan": len(known & steps),
    }


def _ladder_extras(graph_data: dict, items: list[dict], mastery: dict, target: str, name: str):
    summary = api.ladder_summary(graph_data, items, mastery, target, name)
    rows = summary["rows"]
    return {
        "not_checked": sum(r["result"] == "not_checked" for r in rows),
        "stopped_early": 1.0 if any(s["not_checked"] for s in summary["stops"]) else 0.0,
        "skipped_by_a_gap": sum(len(s["not_checked"]) for s in summary["stops"]),
        "stand_ins": sum(len(r["stand_ins"]) for r in rows),
        "stand_ins_for_hard": sum(s["wanted"] == "hard" for r in rows for s in r["stand_ins"]),
        "no_hard_question": sum(r["no_hard_question"] for r in rows),
    }


def _bootstrap_mean_interval(diffs: list[float], resamples: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(resamples))
    return [round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples)], 4)]


def evaluate_ladders(
    graph_data: dict,
    quiz_items: list[dict],
    students: list[dict],
    cfg: dict,
    answer_seed: int | None = None,
) -> dict[str, Any]:
    """Questions, accuracy, wrongly known, gap coverage and path length per strategy.

    Same rules as evaluate_rq2_and_rq4: the same scored concepts, and each strategy draws from
    its own random stream per student. `adaptive` is that function's own run, so it must equal
    rq2_rq4_results.json on the same seed.
    """
    target = cfg["target"]
    seed = cfg["seed"] if answer_seed is None else answer_seed
    path = generic_path(load_graph(graph_data), target)
    items = placeholder_ladder_items(graph_data, target, cfg.get("drop_levels", ()))
    per_student: dict[str, list[dict]] = {
        name: [] for name in ("adaptive", "adaptive_levelled", *LADDER_STRATEGIES)
    }
    for i, student in enumerate(students):
        truth = student.get("mastery", {})

        def stream(name: str, i: int = i) -> random.Random:
            return random.Random(f"{seed}:{i}:{name}")

        est, q = run_adaptive_diagnosis(
            graph_data, quiz_items, truth, target, rng=stream("adaptive")
        )
        per_student["adaptive"].append(
            {
                "questions": q,
                "self_reports": 0,
                **_plan_scores(graph_data, est, truth, path, target),
            }
        )
        est, q = run_adaptive_levelled(
            graph_data, items, truth, target, stream("adaptive_levelled"), cfg
        )
        per_student["adaptive_levelled"].append(
            {
                "questions": q,
                "self_reports": 0,
                **_plan_scores(graph_data, est, truth, path, target),
            }
        )
        for name in LADDER_STRATEGIES:
            est, q, reports = run_ladder_diagnosis(
                graph_data, items, truth, target, name, stream(name), cfg
            )
            per_student[name].append(
                {
                    "questions": q,
                    "self_reports": reports,
                    **_plan_scores(graph_data, est, truth, path, target),
                    **_ladder_extras(graph_data, items, est, target, name),
                }
            )
    strategies = {
        name: {key: round(_mean([r[key] for r in rows]), 4) for key in rows[0]}
        for name, rows in per_student.items()
    }
    against_adaptive = {}
    for name in LADDER_STRATEGIES:
        against_adaptive[name] = {}
        for key in ("questions", "accuracy", "wrongly_known", "path_length"):
            diffs = [
                r[key] - base[key]
                for r, base in zip(per_student[name], per_student["adaptive_levelled"], strict=True)
            ]
            against_adaptive[name][key] = {
                "mean_difference": round(_mean(diffs), 4),
                "interval_95": _bootstrap_mean_interval(diffs, cfg["bootstrap_resamples"], seed),
            }
    return {"strategies": strategies, "against_adaptive_levelled": against_adaptive}


def ladder_comparison(graph_data: dict, quiz_items: list[dict], cfg: dict) -> dict[str, Any]:
    """The results file: both student conditions, other answer seeds and the sensitivity runs."""
    populations = {
        name: make(graph_data, num_students=cfg["num_students"], seed=cfg["seed"])["students"]
        for name, make in CONDITIONS.items()
    }
    main_runs = {
        name: evaluate_ladders(graph_data, quiz_items, students, cfg)
        for name, students in populations.items()
    }
    other_seeds: dict = {name: {s: {} for s in LADDER_STRATEGIES} for name in populations}
    for name, students in populations.items():
        for seed in cfg["answer_seeds"]:
            run = evaluate_ladders(graph_data, quiz_items, students, cfg, answer_seed=seed)
            for strategy in LADDER_STRATEGIES:
                other_seeds[name][strategy][str(seed)] = run["strategies"][strategy]["accuracy"]
    sensitivity = {}
    for scenario, change in cfg["sensitivity"].items():
        changed = {**cfg, **{k: v for k, v in change.items() if k != "about"}}
        sensitivity[scenario] = {
            "about": change["about"],
            **{
                name: evaluate_ladders(graph_data, quiz_items, students, changed)["strategies"]
                for name, students in populations.items()
            },
        }
    return {
        "placeholder_items": True,
        "simulated_students": True,
        "no_llm": True,
        "assumptions": LADDER_ASSUMPTIONS,
        "config": cfg,
        "target_concept": cfg["target"],
        "mastery_threshold": MASTERY_THRESHOLD,
        "scored_concepts": generic_path(load_graph(graph_data), cfg["target"]),
        "conditions": main_runs,
        "accuracy_by_answer_seed": other_seeds,
        "sensitivity": sensitivity,
    }


def ladder_main() -> None:
    cfg = json.loads(LADDER_CONFIG.read_text(encoding="utf-8"))
    graph_data = read_json(EXAMPLES / "validated_graph.json")
    quiz_items = read_json(EXAMPLES / "quiz_items.json")["items"]
    results = ladder_comparison(graph_data, quiz_items, cfg)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / "ladder_comparison.json"
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for name, run in results["conditions"].items():
        print(f"[{name}]")
        for strategy, row in run["strategies"].items():
            print(
                f"  {strategy:18s} {row['questions']:5.2f} questions"
                f"  accuracy {row['accuracy']:.3f}"
                f"  wrongly known {row['wrongly_known']:.3f}  gaps {row['gap_coverage']:.3f}"
                f"  path {row['path_length']:.2f}"
            )
    print(f"Results saved to: {out_file}")


if __name__ == "__main__":
    if "--ladder" in sys.argv[1:]:
        ladder_main()
    else:
        main()
