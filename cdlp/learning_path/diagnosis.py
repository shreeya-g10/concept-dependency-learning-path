"""Simple interpretable adaptive diagnosis policy (owner: Shrestha)."""

from cdlp.learning_path.graph import generic_path, load_graph, prerequisites

MAX_QUESTIONS = 10


def initial_mastery(graph: dict, target: str) -> dict[str, float]:
    return dict.fromkeys(generic_path(load_graph(graph), target), 0.5)


def update(graph: dict, mastery: dict[str, float], concept: str, correct: bool) -> dict[str, float]:
    network = load_graph(graph)
    if concept not in network:
        raise ValueError(f"Unknown concept: {concept}")
    state = dict(mastery)
    state[concept] = 0.9 if correct else 0.1
    for parent in prerequisites(network, concept):
        old = float(state.get(parent, 0.5))
        if correct:
            state[parent] = max(old, 0.8)
        elif old == 0.5:
            state[parent] = 0.5  # Not knowing a child does not prove its parents are unknown.
    return state


def choose_question(graph: dict, quiz: dict, mastery: dict[str, float], target: str,
                    asked: set[str] | None = None) -> dict | None:
    """Choose the middle uncertain prerequisite; never repeat an item."""
    path = generic_path(load_graph(graph), target)
    asked = asked or set()
    items = {item["concept_id"]: item for item in quiz["items"] if item["id"] not in asked}
    uncertain = [concept for concept in path if 0.2 <= float(mastery.get(concept, 0.5)) <= 0.8
                 and concept in items]
    if not uncertain:
        return None
    return items[uncertain[len(uncertain) // 2]]
