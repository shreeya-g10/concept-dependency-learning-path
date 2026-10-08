from cdlp.discovery.sim_students import (
    generate_simulated_students,
)


def test_generate_simulated_students():
    concepts = [
        {"id": "trees"},
        {"id": "binary_tree"},
        {"id": "binary_search_tree"},
        {"id": "avl_tree"},
        {"id": "graphs"},
    ]

    relationships = [
        {
            "source": "trees",
            "target": "binary_tree",
            "type": "PREREQUISITE",
            "strength": "hard",
        },
        {
            "source": "binary_tree",
            "target": "binary_search_tree",
            "type": "PREREQUISITE",
            "strength": "hard",
        },
        {
            "source": "binary_search_tree",
            "target": "avl_tree",
            "type": "PREREQUISITE",
            "strength": "hard",
        },
    ]

    students = generate_simulated_students(
        concepts,
        relationships,
        count=500,
        seed=42,
    )

    assert len(students) == 500

    for student in students:
        assert student["student_id"]
        assert set(student["mastery"]) == {
            "trees",
            "binary_tree",
            "binary_search_tree",
            "avl_tree",
            "graphs",
        }

        assert 0 <= student["slip"] <= 1
        assert 0 <= student["guess"] <= 1

        for mastery in student["mastery"].values():
            assert 0 <= mastery <= 1

        assert (
            student["mastery"]["binary_tree"]
            <= student["mastery"]["trees"]
        )

        assert (
            student["mastery"]["binary_search_tree"]
            <= student["mastery"]["binary_tree"]
        )

        assert (
            student["mastery"]["avl_tree"]
            <= student["mastery"]["binary_search_tree"]
        )


def test_soft_relationship_does_not_constrain_mastery():
    concepts = [
        {"id": "recursion"},
        {"id": "trees"},
        {"id": "binary_tree"},
    ]

    relationships = [
        {
            "source": "trees",
            "target": "binary_tree",
            "type": "PREREQUISITE",
            "strength": "hard",
        },
        {
            "source": "recursion",
            "target": "binary_tree",
            "type": "PREREQUISITE",
            "strength": "soft",
        },
    ]

    students = generate_simulated_students(
        concepts,
        relationships,
        count=100,
        seed=42,
    )

    for student in students:
        assert (
            student["mastery"]["binary_tree"]
            <= student["mastery"]["trees"]
        )