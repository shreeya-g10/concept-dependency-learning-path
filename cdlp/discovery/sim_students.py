import random


def _hard_prerequisites(
    relationships: list[dict],
) -> dict[str, list[str]]:
    prerequisites = {}

    for relationship in relationships:
        if (
            relationship.get("type") == "PREREQUISITE"
            and relationship.get("strength") == "hard"
        ):
            source = relationship["source"]
            target = relationship["target"]

            prerequisites.setdefault(
                target,
                [],
            ).append(source)

    return prerequisites


def _topological_order(
    concepts: list[dict],
    prerequisites: dict[str, list[str]],
) -> list[str]:
    concept_ids = [
        concept["id"]
        for concept in concepts
    ]

    remaining = set(concept_ids)
    ordered = []

    while remaining:
        ready = sorted(
            concept_id
            for concept_id in remaining
            if all(
                prerequisite not in remaining
                for prerequisite in prerequisites.get(
                    concept_id,
                    [],
                )
            )
        )

        if not ready:
            raise ValueError(
                "Hard prerequisite graph contains a cycle."
            )

        ordered.extend(ready)
        remaining.difference_update(ready)

    return ordered


def _sample_mastery(
    prerequisite_values: list[float],
    rng: random.Random,
) -> float:
    if not prerequisite_values:
        return rng.betavariate(2.0, 2.0)

    upper_bound = min(prerequisite_values)

    return rng.uniform(
        0.0,
        upper_bound,
    )


def generate_simulated_students(
    concepts: list[dict],
    relationships: list[dict],
    count: int = 500,
    seed: int = 42,
) -> list[dict]:
    if count <= 0:
        raise ValueError(
            "count must be greater than zero."
        )

    prerequisites = _hard_prerequisites(
        relationships
    )

    concept_ids = [
        concept["id"]
        for concept in concepts
    ]

    ordered_concepts = _topological_order(
        concepts,
        prerequisites,
    )

    rng = random.Random(seed)

    students = []

    for index in range(1, count + 1):
        mastery = {}

        for concept_id in ordered_concepts:
            prerequisite_values = [
                mastery[prerequisite]
                for prerequisite in prerequisites.get(
                    concept_id,
                    [],
                )
            ]

            mastery[concept_id] = round(
                _sample_mastery(
                    prerequisite_values,
                    rng,
                ),
                4,
            )

        mastery = {
            concept_id: mastery[concept_id]
            for concept_id in concept_ids
        }

        students.append(
            {
                "student_id": f"student_{index:03d}",
                "mastery": mastery,
                "slip": round(
                    rng.uniform(0.05, 0.15),
                    4,
                ),
                "guess": round(
                    rng.uniform(0.15, 0.25),
                    4,
                ),
            }
        )

    return students