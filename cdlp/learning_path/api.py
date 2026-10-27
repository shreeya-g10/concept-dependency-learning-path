"""Adaptive prerequisite graph and quiz API (owner: Shrestha)."""
import math
import networkx as nx


def build_graph(graph: dict, include_review: bool = False, include_soft: bool = True) -> nx.DiGraph:
    g = nx.DiGraph()
    for node in graph['nodes']:
        g.add_node(node['id'], **{k: v for k, v in node.items() if k != 'id'})
    for edge in graph['edges']:
        if edge['decision'] != 'ACCEPT' and not (include_review and edge['decision'] == 'HUMAN_REVIEW'):
            continue
        if not include_soft and edge.get('strength') == 'soft':
            continue
        g.add_edge(edge['source'], edge['target'], **edge)
    if not nx.is_directed_acyclic_graph(g):
        raise ValueError('Validated prerequisite graph contains a directed cycle')
    return g


def prerequisite_order(graph: dict, target: str, include_soft: bool = True) -> list[str]:
    g = build_graph(graph, include_soft=include_soft)
    if target not in g:
        raise ValueError(f'Unknown target: {target}')
    return list(nx.topological_sort(g.subgraph(nx.ancestors(g, target) | {target})))


def graph_summary(graph: dict) -> dict:
    g = build_graph(graph)
    reduced = nx.transitive_reduction(g)
    return {'nodes': g.number_of_nodes(), 'edges': g.number_of_edges(),
            'reduced_edges': list(reduced.edges()),
            'depth': {n: nx.dag_longest_path_length(g.subgraph(nx.ancestors(g, n) | {n})) for n in g}}


def _entropy(p):
    p = max(1e-9, min(1 - 1e-9, p))
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def next_question(graph: dict, quiz: dict, mastery: dict[str, float], target: str) -> dict | None:
    """Choose the unasked item with highest uncertainty and prerequisite reach.

    Pass previously asked item ids in mastery['__asked__'] (optional, non-contract
    session-only metadata); otherwise confident concepts are not repeated.
    """
    g = build_graph(graph)
    required = set(prerequisite_order(graph, target))
    asked = set(mastery.get('__asked__', []))
    candidates = []
    for item in quiz['items']:
        c = item['concept_id']
        if c not in required or item['id'] in asked:
            continue
        prob = float(mastery.get(c, 0.5))
        if prob <= 0.15 or prob >= 0.85:
            continue
        reach = len(nx.descendants(g, c) & required)
        candidates.append((_entropy(prob) * (1 + 0.12 * reach), item['id'], item))
    return sorted(candidates, key=lambda x: (-x[0], x[1]))[0][2] if candidates else None


def update_mastery(graph: dict, mastery: dict[str, float], concept_id: str, correct: bool) -> dict[str, float]:
    g = build_graph(graph)
    if concept_id not in g:
        raise ValueError(f'Unknown concept: {concept_id}')
    updated = dict(mastery)
    prior = float(updated.get(concept_id, 0.5))
    # Bayesian observation model: P(correct|knows)=0.9; P(correct|not)=0.2.
    likelihood_known, likelihood_unknown = (0.9, 0.2) if correct else (0.1, 0.8)
    posterior = prior * likelihood_known / (prior * likelihood_known + (1-prior) * likelihood_unknown)
    updated[concept_id] = round(max(0.01, min(0.99, posterior)), 4)
    for ancestor in nx.ancestors(g, concept_id):
        old = float(updated.get(ancestor, 0.5))
        if correct:
            updated[ancestor] = round(old + 0.25 * (1-old), 4)
        else:
            updated[ancestor] = round(old + 0.10 * (0.5-old), 4)
    return updated


def personalized_path(graph: dict, mastery: dict[str, float], target: str) -> list[dict]:
    g = build_graph(graph)
    order = prerequisite_order(graph, target)
    steps = []
    for concept in order:
        if float(mastery.get(concept, 0.5)) >= 0.8:
            continue
        incoming = [(source, g.edges[source, concept]) for source in g.predecessors(concept)]
        hard = [(source, e) for source, e in incoming if e.get('strength') != 'soft']
        relevant = hard or incoming
        evidence = []
        for _, edge in relevant:
            for ev in edge.get('evidence', []):
                if ev.get('doc') and isinstance(ev.get('page'), int) and ev['page'] >= 1:
                    record = {k: ev[k] for k in ('doc', 'page', 'chunk_id') if k in ev}
                    if record not in evidence:
                        evidence.append(record)
        if concept == target:
            why = 'Your learning goal; build the required foundations first.'
        elif relevant:
            why = f"Prerequisite for {', '.join(g.nodes[s].get('name', s) for s in g.successors(concept) if s in order) or 'your goal'}; current mastery {float(mastery.get(concept, .5)):.0%}."
        else:
            why = f'Foundation concept; estimated mastery {float(mastery.get(concept, .5)):.0%}.'
        steps.append({'concept_id': concept, 'why': why, 'evidence': evidence})
    return steps
