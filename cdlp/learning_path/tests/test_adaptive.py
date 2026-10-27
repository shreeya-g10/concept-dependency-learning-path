import pytest
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.learning_path.api import build_graph, prerequisite_order, next_question, update_mastery, personalized_path
from cdlp.learning_path.evaluate import evaluate

GRAPH = read_json(EXAMPLES / 'validated_graph.json')
QUIZ = read_json(EXAMPLES / 'quiz_items.json')
STUDENTS = read_json(EXAMPLES / 'sim_students.json')


def test_only_accepted_edges():
    g = build_graph(GRAPH)
    assert g.has_edge('trees', 'binary_tree')
    assert not g.has_edge('trees', 'graphs')
    assert not g.has_edge('graphs', 'avl_tree')


def test_prerequisite_order():
    order = prerequisite_order(GRAPH, 'avl_tree')
    assert order.index('trees') < order.index('binary_tree') < order.index('binary_search_tree') < order.index('avl_tree')


def test_adaptive_updates():
    initial = {'binary_tree': .5, 'trees': .5}
    result = update_mastery(GRAPH, initial, 'binary_tree', True)
    assert result['binary_tree'] > .5 and result['trees'] > .5
    wrong = update_mastery(GRAPH, initial, 'binary_tree', False)
    assert wrong['binary_tree'] < .5


def test_no_repeat():
    item = next_question(GRAPH, QUIZ, {}, 'avl_tree')
    assert item
    remaining = next_question(GRAPH, QUIZ, {'__asked__': [item['id']]}, 'avl_tree')
    assert remaining and remaining['id'] != item['id']


def test_path_respects_mastery_and_order():
    steps = personalized_path(GRAPH, {'trees': .95}, 'avl_tree')
    ids = [s['concept_id'] for s in steps]
    assert 'trees' not in ids and ids[-1] == 'avl_tree'
    assert ids.index('binary_tree') < ids.index('binary_search_tree')


def test_cycle_rejected():
    modified = {**GRAPH, 'edges': GRAPH['edges'] + [{**GRAPH['edges'][0], 'source': 'avl_tree', 'target': 'trees'}]}
    with pytest.raises(ValueError):
        build_graph(modified)


def test_evaluation_reproducible():
    assert evaluate(GRAPH, QUIZ, STUDENTS, 'avl_tree', repeats=2) == evaluate(GRAPH, QUIZ, STUDENTS, 'avl_tree', repeats=2)
