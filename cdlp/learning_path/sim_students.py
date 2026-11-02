"""Synthetic student generation for adaptive diagnosis evaluation (RQ2).

Initial code: Vaidehi (moved from cdlp/discovery/).
Generates simulated students with known ground-truth mastery respecting prerequisite DAGs
using a level-independent frontier sampler from ACCEPT edges in validated_graph.json.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from cdlp.learning_path.graph import ancestors, load_graph, topological_sort
from cdlp.shared.io import write_json


def generate_simulated_students(
    graph_data: dict,
    num_students: int = 50,
    seed: int = 42,
    course_id: str | None = None,
) -> dict[str, Any]:
    """Generate synthetic students with ground truth mastery states respecting the DAG.

    Uses a level-independent frontier sampler from ACCEPT edges (both hard and soft):
    1. For each student, pick a learning 'frontier' concept in topological order.
    2. All concepts before the frontier and all upstream ancestors (prerequisites)
       are in the student's 'known' zone: expected mastery ~ 0.90 (with occasional slip).
    3. Concepts strictly beyond the frontier are in the 'unlearned' zone:
       expected mastery ~ 0.10 (with occasional lucky guess).
    This avoids depth-dependent decay where deep concepts otherwise trend toward 0.
    """
    rng = random.Random(seed)
    G = load_graph(graph_data)
    nodes = list(G.nodes)
    topo_order = topological_sort(G) if nodes else []

    resolved_course_id = course_id or graph_data.get("course_id") or "ds101"

    students = []
    for i in range(1, num_students + 1):
        s_id = f"sim_s_{i:03d}"
        slip = round(rng.uniform(0.05, 0.12), 2)
        guess = round(rng.uniform(0.10, 0.20), 2)

        # Level-independent frontier selection:
        # Pick progress point k in [0, len(topo_order)]
        k = rng.randint(0, len(topo_order))
        if k > 0:
            frontier_concept = topo_order[k - 1]
            mastered_zone = ancestors(G, frontier_concept) | {frontier_concept}
            for c in topo_order[:k]:
                if ancestors(G, c).issubset(mastered_zone):
                    mastered_zone.add(c)
        else:
            mastered_zone = set()

        mastery: dict[str, float] = {}
        for concept in nodes:
            if concept in mastered_zone:
                # Level-independent high mastery (~0.90)
                if rng.random() < slip:
                    m = rng.uniform(0.15, 0.35)
                else:
                    m = rng.uniform(0.85, 0.98)
            else:
                # Unlearned zone: low mastery (~0.10)
                if rng.random() < guess:
                    m = rng.uniform(0.65, 0.85)
                else:
                    m = rng.uniform(0.02, 0.18)

            mastery[concept] = round(m, 2)

        target = "avl_tree" if "avl_tree" in nodes else (nodes[-1] if nodes else "concept")

        students.append(
            {
                "student_id": s_id,
                "target": target,
                "mastery": mastery,
                "slip": slip,
                "guess": guess,
            }
        )

    return {
        "schema_version": "1.0",
        "course_id": resolved_course_id,
        "students": students,
    }


def save_simulated_students(
    path: Path | str,
    graph_data: dict,
    num_students: int = 50,
    course_id: str | None = None,
) -> None:
    """Save synthetic students to disk conforming to sim_students.schema.json."""
    data = generate_simulated_students(
        graph_data=graph_data,
        num_students=num_students,
        course_id=course_id,
    )
    write_json(path, data)
