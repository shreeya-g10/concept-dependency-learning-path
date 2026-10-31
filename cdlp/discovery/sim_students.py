"""Synthetic student generation for adaptive diagnosis evaluation (RQ2).

Owner: Vaidehi.
Generates simulated students with known ground-truth mastery respecting prerequisite DAGs.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from cdlp.learning_path.graph import load_graph, topological_sort
from cdlp.shared.io import write_json


def generate_simulated_students(
    graph_data: dict,
    num_students: int = 50,
    seed: int = 42,
    course_id: str = "ds101",
) -> dict[str, Any]:
    """Generate synthetic students with ground truth mastery states respecting the DAG.

    If a student has mastered concept B, they must have high mastery of its hard prerequisites,
    subject to occasional slip (10%) and guess (15%) noise.
    """
    rng = random.Random(seed)
    G = load_graph(graph_data)
    nodes = list(G.nodes)
    topo_order = topological_sort(G) if nodes else []

    students = []
    for i in range(1, num_students + 1):
        s_id = f"sim_s_{i:03d}"
        mastery = {}

        # Cutoff depth or random proficiency level
        proficiency = rng.random()

        for concept in topo_order:
            parents = list(G.predecessors(concept))
            if not parents:
                # Root concepts
                prob = 0.85 if rng.random() < (proficiency + 0.2) else 0.15
            else:
                # If prerequisites mastered, high chance of mastering this concept
                parents_mastered = all(mastery.get(p, 0.5) > 0.6 for p in parents)
                if parents_mastered:
                    prob = 0.85 if rng.random() < 0.85 else 0.15
                else:
                    prob = 0.15 if rng.random() < 0.90 else 0.85  # rare slip/lucky guess

            mastery[concept] = round(prob, 2)

        target = "avl_tree" if "avl_tree" in nodes else (nodes[-1] if nodes else "concept")

        students.append(
            {
                "id": s_id,
                "target": target,
                "mastery": mastery,
            }
        )

    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "students": students,
    }


def save_simulated_students(
    path: Path | str,
    graph_data: dict,
    num_students: int = 50,
    course_id: str = "ds101",
) -> None:
    """Save synthetic students to disk conforming to sim_students.schema.json."""
    data = generate_simulated_students(
        graph_data=graph_data,
        num_students=num_students,
        course_id=course_id,
    )
    write_json(path, data)
