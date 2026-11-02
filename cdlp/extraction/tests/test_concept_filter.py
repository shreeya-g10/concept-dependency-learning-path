"""Evidence filter: each rule, stable concepts, and independence from the gold data."""

import ast
import copy
import json
from pathlib import Path

import pytest

from cdlp.extraction import concept_filter as cf
from cdlp.shared.validate import check, schema_for

CONFIG = cf.load_config()
FILLER = "Plain sentence with nothing relevant in it."


def chunk(n, text=FILLER, heading="Section", doc="a.pdf"):
    return {"chunk_id": f"c{n}", "doc": doc, "page": 1, "heading": heading, "text": text}


def concept(name, sources=("c0",), aliases=(), slug=None):
    return {
        "id": slug or name.lower().replace(" ", "_"),
        "name": name,
        "aliases": list(aliases),
        "description": f"About {name}.",
        "sources": [{"doc": "a.pdf", "page": 1, "chunk_id": s} for s in sources],
    }


def run(concepts, chunks, **settings):
    # Padding chunks keep the course above min_chunks_to_apply; min_concepts_after is off
    # so that one concept can be tested alone.
    pad = [chunk(1000 + n) for n in range(CONFIG["min_chunks_to_apply"])]
    config = {**CONFIG, "min_concepts_after": 0, **settings}
    data = {"schema_version": "1.7", "course_id": "t", "concepts": concepts}
    filtered, report = cf.filter_concepts(data, chunks + pad, config)
    return filtered, {r["id"]: r for r in report["concepts"]}, report


def reason(name, chunks, **kwargs):
    c = concept(name, **kwargs)
    return run([c], chunks)[1][c["id"]]["reason"]


def test_a_heading_keeps_a_concept_with_little_text_evidence():
    assert reason("Binary Heap", [chunk(0, heading="BinaryHeap: An Implicit Tree")]) == "heading"


def test_an_exercise_heading_is_not_evidence():
    chunks = [chunk(0, "A treque is a queue.", heading="Discussion and Exercises")]
    assert reason("Treque", chunks) == "exercise_only"


def test_mentions_in_exercises_do_not_count():
    chunks = [
        chunk(n, "A splay tree here.", heading="Discussion and Exercises") for n in range(5)
    ] + [chunk(5, "A splay tree here.")]
    assert reason("Splay Tree", chunks, sources=("c5",)) == "weak_evidence"


def test_mentions_in_enough_chunks_keep_a_concept():
    chunks = [chunk(n, "The backing array grows.") for n in range(CONFIG["min_mention_chunks"])]
    assert reason("Backing Array", chunks) == "many_mentions"


def test_mentions_across_documents_keep_a_concept():
    chunks = [chunk(0, "A forest here.", doc="a.pdf"), chunk(1, "A forest here.", doc="b.pdf")]
    assert reason("Forest", chunks) == "several_documents"


def test_two_mentions_in_one_document_are_not_enough():
    chunks = [chunk(0, "A forest here."), chunk(1, "A forest here.")]
    assert reason("Forest", chunks) == "weak_evidence"


def test_several_source_chunks_with_a_mention_keep_a_concept():
    chunks = [chunk(0, "A meld here."), chunk(1)]
    assert reason("Meld", chunks, sources=("c0", "c1")) == "sources_and_mentions"


def test_many_source_chunks_keep_a_concept_used_as_a_call():
    ids = [f"c{n}" for n in range(CONFIG["strong_source_chunks"])]
    chunks = [chunk(n, "Call resize(x) now.") for n in range(len(ids))]
    assert reason("Resize", chunks, sources=ids) == "many_source_chunks"


@pytest.mark.parametrize("name", ["gather(u)", "add(i, x)", "get(i) and set(i,x)"])
def test_a_name_written_as_a_call_is_code(name):
    assert cf.is_code_name({"name": name}, [], CONFIG)


def test_a_name_with_its_call_as_an_alias_is_code():
    assert cf.is_code_name({"name": "Find X", "aliases": ["find(x)"]}, [], CONFIG)


def test_a_name_the_text_uses_only_as_a_call_is_code():
    text = "then push black(u) and push black(v)"
    assert cf.is_code_name({"name": "Push Black"}, [text], CONFIG)


def test_the_method_suffix_is_ignored_when_looking_for_calls():
    assert cf.is_code_name({"name": "Grow Method"}, ["call grow() and grow()"], CONFIG)


def test_a_concept_also_used_in_prose_is_not_code():
    text = "an edge joins nodes; each edge counts; add edge(i) once"
    assert not cf.is_code_name({"name": "Edge"}, [text], CONFIG)


def test_one_call_is_not_enough_to_call_a_name_code():
    assert not cf.is_code_name({"name": "Meld"}, ["meld(a)"], CONFIG)


@pytest.mark.parametrize("name", ["Lemma", "Theorems", "Analysis", "Correctness"])
def test_generic_words_are_removed_even_with_much_evidence(name):
    chunks = [chunk(n, f"{name} here.", heading=name) for n in range(5)]
    assert reason(name, chunks) == "generic_word"


def test_ordinary_or_shared_aliases_are_not_evidence():
    chunks = [chunk(n, "Add a tree to the list, then a Double-Ended Queue.") for n in range(4)]
    weak = concept("Foo Bar", aliases=["Add", "Tree"])
    shared = concept("Baz Qux", aliases=["Double-Ended Queue"])
    other = concept("Deque", aliases=["Double-Ended Queue"])
    rows = run([weak, shared, other], chunks)[1]
    assert rows["foo_bar"]["mention_chunks"] == 0
    assert rows["baz_qux"]["mention_chunks"] == 0


def test_specific_aliases_are_evidence():
    chunks = [chunk(n, "The BST here, and a Sorted Tree.") for n in range(3)]
    rows = run([concept("Abc Def", aliases=["BST"])], chunks)[1]
    assert rows["abc_def"]["mention_chunks"] == 3


def test_text_matching_handles_plurals_hyphens_line_breaks_ligatures_and_class_names():
    pattern = cf.term_pattern("Doubly-Linked List")
    for text in ["doubly linked lists", "doubly-\nlinked list", "DoublyLinkedList"]:
        assert pattern.search(cf.normalize(text))
    assert cf.term_pattern("Space-Efficient List").search(cf.normalize("Space-Eﬃcient List"))
    assert not cf.term_pattern("Directed Graph").search(cf.normalize("an undirected graph"))


def test_a_call_written_alias_needs_a_word_boundary():
    chunks = [chunk(n, "foo(1) is called") for n in range(3)]
    rows = run([concept("Abc Def", aliases=["O(1) time"])], chunks)[1]
    assert rows["abc_def"]["mention_chunks"] == 0
    chunks = [chunk(n, "It takes O( 1 ) time") for n in range(3)]
    rows = run([concept("Abc Def", aliases=["O(1) time"])], chunks)[1]
    assert rows["abc_def"]["mention_chunks"] == 3


def test_kept_concepts_are_unchanged_and_the_input_is_not_modified():
    keep = concept("Binary Heap", aliases=["BinaryHeap", "Priority Queue"], slug="heap")
    drop = concept("Treque")
    data = {"schema_version": "1.7", "course_id": "t", "dedup_method": "embedding"}
    data["concepts"] = [keep, drop]
    before = copy.deepcopy(data)
    chunks = [chunk(n, heading="Binary Heap") for n in range(CONFIG["min_chunks_to_apply"])]
    filtered, report = cf.filter_concepts(data, chunks, {**CONFIG, "min_concepts_after": 1})
    assert filtered["concepts"] == [before["concepts"][0]]
    assert filtered["dedup_method"] == "embedding"
    assert data == before
    assert check(filtered, schema_for(Path("concepts.json"))) == []
    assert (report["concepts_before"], report["concepts_after"]) == (2, 1)


def test_a_small_course_keeps_every_concept_and_says_so():
    data = {"schema_version": "1.7", "course_id": "t", "concepts": [concept("Treque")]}
    filtered, report = cf.filter_concepts(data, [chunk(0)], CONFIG)
    assert filtered["concepts"] == data["concepts"]
    assert not report["applied"] and "too few" in report["note"]


def test_settings_that_would_leave_almost_nothing_keep_every_concept():
    data = {"schema_version": "1.7", "course_id": "t", "concepts": [concept("Treque")]}
    chunks = [chunk(n) for n in range(CONFIG["min_chunks_to_apply"])]
    filtered, report = cf.filter_concepts(data, chunks, CONFIG)
    assert filtered["concepts"] == data["concepts"]
    assert not report["applied"] and "would remain" in report["note"]


def test_settings_come_from_the_config():
    chunks = [chunk(0, "A forest here.")]
    assert run([concept("Forest")], chunks, min_mention_chunks=1)[1]["forest"]["decision"] == "keep"


def test_the_filter_does_not_use_gold_data():
    tree = ast.parse(Path(cf.__file__).read_text(encoding="utf-8"))
    code = tree.body[1:]  # the module docstring may say that gold is not used
    strings = [n.value for node in code for n in ast.walk(node) if isinstance(n, ast.Constant)]
    assert not any("gold" in s.lower() for s in strings if isinstance(s, str))
    assert "gold" not in json.dumps(CONFIG).lower()
