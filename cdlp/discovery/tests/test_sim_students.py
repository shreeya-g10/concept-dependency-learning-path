"""Tests for simulated student generation with level-independent frontier sampler.

Owner: Vaidehi.
"""

from __future__ import annotations

from cdlp.discovery.sim_students import generate_simulated_students
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check


def test_sim_students_schema_conformance():
    graph_data = read_json(EXAMPLES / "validated_graph.json")
    sim = generate_simulated_students(graph_data, num_students=20, seed=42)

    assert sim["schema_version"] == "1.0"
    assert sim["course_id"] == "ds101"
    assert len(sim["students"]) == 20

    # Schema validation
    errors = check(sim, "sim_students")
    assert errors == []


def test_level_independent_frontier_sampler_does_not_decay():
    graph_data = read_json(EXAMPLES / "validated_graph.json")
    # Generate large sample to inspect deep concept distributions
    sim = generate_simulated_students(graph_data, num_students=100, seed=42)

    deep_concept = "avl_tree"
    masteries = [
        s["mastery"][deep_concept] for s in sim["students"] if deep_concept in s["mastery"]
    ]

    # Under uniform(0, min(parents)), 5 levels deep would average < 0.05
    # Under the frontier sampler, students who reach the frontier have mastery > 0.80
    high_mastery_count = sum(1 for m in masteries if m >= 0.80)
    assert high_mastery_count > 10, (
        "Frontier sampler must allow deep concepts to reach high mastery"
    )
