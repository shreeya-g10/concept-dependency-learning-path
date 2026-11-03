"""The checks built from real ds101 failures, run on those same questions.

quiz_dev_examples.json holds real drafts from the quiz_v2 review run. They were used to DESIGN
these checks, so they are development examples. Passing here says nothing about accuracy, and
any accuracy figure must come from questions not used here.

Two kinds of test, and they prove different things:
- The name and near-duplicate checks use no LLM, so these tests show that they really do
  catch the real questions.
- The second model is mocked. These tests show that the prompt carries what the model needs,
  and that a model that says "several are true" gets the item dropped. They do NOT show that
  llama3.1 gives that answer: only a real run can show that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdlp.learning_path import quiz

DEV = json.loads((Path(__file__).parent / "quiz_dev_examples.json").read_text(encoding="utf-8"))
EXAMPLES = DEV["examples"]
BST = DEV["concepts"]["binary_search_tree"]
ROTATION = DEV["concepts"]["rotation"]
GRAPH = DEV["concepts"]["graph"]


def example(concept_id: str, words: str) -> dict:
    return next(
        e
        for e in EXAMPLES
        if e["concept_id"] == concept_id and words in e["draft"]["question"].casefold()
    )


def clean(example_row: dict, item_id: str = "q") -> dict:
    """An example as the item the checker receives."""
    draft = example_row["draft"]
    item = quiz.clean_item(
        {**draft, "evidence_chunk_ids": [example_row["chunk_id"]]},
        example_row["concept_id"],
        item_id,
        [example_row["chunk_id"]],
    )
    item["source_quote"] = " ".join(draft["source_quote"].split())
    return item


def evidence_of(example_row: dict) -> list[dict]:
    return [{"chunk_id": example_row["chunk_id"], "text": example_row["excerpt"]}]


def run_check(monkeypatch, example_row: dict, concept: dict, reply: dict) -> tuple[str | None, str]:
    prompts = []

    def chat_json(prompt, **kwargs):
        assert kwargs["prompt_version"] == "quiz_check_v2"
        prompts.append(prompt)
        return reply

    monkeypatch.setattr(quiz, "chat_json", chat_json)
    template = quiz.load_prompt("quiz_check_v2")
    result = quiz.check_item(clean(example_row), concept, example_row["excerpt"], template, None)
    return result, prompts[0]


def letters_of(prompt: str) -> dict[str, str]:
    """Option text -> letter, as the prompt showed them."""
    block = prompt.split("OPTIONS:\n", 1)[1].split("\n\nQUOTE OFFERED", 1)[0]
    return {line.split(". ", 1)[1]: line[0] for line in block.splitlines()}


def test_the_quiz_check_v1_prompt_is_kept_for_the_record():
    assert "only_one_correct" in quiz.load_prompt("quiz_check_v1")
    assert quiz.CHECK_PROMPT_VERSION == "quiz_check_v2"


def test_the_examples_really_passed_the_old_check():
    """Why v2 is needed: the old check said yes to these."""
    graph = example("graph", "what is a graph")["quiz_check_v1_reply"]
    assert graph["only_one_correct"] is True and graph["about_topic"] is True
    assert (
        example("rotation", "what does rotation do")["quiz_check_v1_reply"]["about_topic"] is True
    )


# ---- a. the name check -------------------------------------------------------------


@pytest.mark.parametrize(
    "words",
    ["what can happen", "potential problem", "an example of"],
)
def test_real_bst_drafts_written_as_one_word_now_name_the_topic(words):
    row = example("binary_search_tree", words)
    assert quiz.v2_problem(row["draft"], BST, evidence_of(row)) is None
    # the old pattern is what dropped them
    asked = f"{row['draft']['question']} {row['draft']['correct_answer']}"
    assert not any(p.search(asked) for p in quiz._name_patterns(BST))


@pytest.mark.parametrize(
    "text",
    [
        "What is a Binary Search Tree?",
        "what is a binary search tree",
        "BINARY SEARCH TREES",
        "a BinarySearchTree",
        "BinarySearchTrees",
        "binarysearchtree",
        "a binary-search tree",
        "a binary_search_tree",
        "a binary–search tree",
        "a binary search tree's root",
        "the BST",
    ],
)
def test_name_check_ignores_spaces_hyphens_and_case_and_handles_plurals(text):
    assert quiz.names_topic(text, BST)


@pytest.mark.parametrize(
    "name,text",
    [
        ("Queue", "two queues"),
        ("Queues", "a queue"),
        ("Stack", "the stacks"),
        ("Matrix", "two matrices"),
        ("Matrices", "a matrix"),
        ("Dependency", "their dependencies"),
        ("Dependencies", "one dependency"),
        ("Hash", "two hashes"),
        ("Hypothesis", "two hypotheses"),
        ("Heap Sort", "heapsort"),
        ("Heapsort", "heap-sort"),
        ("C++", "written in c++ today"),
    ],
)
def test_name_check_plural_and_singular_forms(name, text):
    assert quiz.names_topic(text, {"name": name})


@pytest.mark.parametrize(
    "name,text",
    [
        ("Queue", "an efficient ArrayQueue"),  # a real rejected draft: a different thing
        ("Graph", "a paragraph"),
        ("Tree", "a treetop"),
        ("Binary Search Tree", "a binary tree"),
        ("Binary Search Tree", "binary search"),
        ("AVL Tree", "a red-black tree"),
        ("Stack", "a stacked plot"),
        ("C++", "the letter c"),
        ("", "anything"),
    ],
)
def test_name_check_does_not_accept_other_words(name, text):
    assert not quiz.names_topic(text, {"name": name})


# ---- b. each option judged on its own ----------------------------------------------


def test_what_is_a_graph_is_dropped_when_several_options_are_judged_true(monkeypatch):
    row = example("graph", "what is a graph")
    _, prompt = run_check(monkeypatch, row, GRAPH, {})
    letters = letters_of(prompt)
    answer = letters[row["draft"]["correct_answer"]]
    too_broad = letters["A set of vertices and edges"]
    reply = {
        "verdicts": {letter: letter in (answer, too_broad) for letter in letters.values()},
        "quote_proves": answer,
        "same_subject": True,
        "about_topic": True,
    }
    assert run_check(monkeypatch, row, GRAPH, reply)[0] == "check_several_true"


def test_the_prompt_asks_about_each_option_and_shows_all_of_them(monkeypatch):
    row = example("graph", "what is a graph")
    _, prompt = run_check(monkeypatch, row, GRAPH, {})
    assert set(letters_of(prompt)) == set(row["draft"]["options"])
    assert "judge every option on its own" in prompt
    assert '"verdicts"' in prompt
    assert row["excerpt"] in prompt


# ---- c. does the quote prove it, and is it about the same thing ----------------------


@pytest.mark.parametrize(
    "words", ["what does rotation do", "when might a rotation", "what is the purpose of rotation"]
)
def test_rotation_questions_are_dropped_when_the_quote_is_on_another_subject(monkeypatch, words):
    row = example("rotation", words)
    _, prompt = run_check(monkeypatch, row, ROTATION, {})
    # the mismatch the model must spot is in front of it
    assert "red-black tree" in prompt.split("QUESTION:\n", 1)[1].split("\n", 1)[0]
    quote = prompt.split("QUOTE OFFERED AS PROOF:\n", 1)[1].split("\n", 1)[0]
    assert quote == " ".join(row["draft"]["source_quote"].split())

    answer = letters_of(prompt)[row["draft"]["correct_answer"]]
    reply = {
        "verdicts": {letter: letter == answer for letter in letters_of(prompt).values()},
        "quote_proves": answer,
        "same_subject": False,
        "about_topic": True,
    }
    assert run_check(monkeypatch, row, ROTATION, reply)[0] == "check_quote_other_subject"


def test_rotation_height_question_is_dropped_when_the_quote_proves_nothing(monkeypatch):
    row = example("rotation", "affect the height")
    _, prompt = run_check(monkeypatch, row, ROTATION, {})
    answer = letters_of(prompt)[row["draft"]["correct_answer"]]
    reply = {
        "verdicts": {letter: letter == answer for letter in letters_of(prompt).values()},
        "quote_proves": "NONE",
        "same_subject": True,
        "about_topic": True,
    }
    assert run_check(monkeypatch, row, ROTATION, reply)[0] == "check_quote_no_proof"


def test_a_real_item_passes_when_the_model_says_it_is_sound(monkeypatch):
    """The other side of the vetoes: a clean verdict keeps the item."""
    row = example("binary_search_tree", "binary search tree property")
    _, prompt = run_check(monkeypatch, row, BST, {})
    answer = letters_of(prompt)[row["draft"]["correct_answer"]]
    reply = {
        "verdicts": {letter: letter == answer for letter in letters_of(prompt).values()},
        "quote_proves": answer,
        "same_subject": True,
        "about_topic": True,
    }
    assert run_check(monkeypatch, row, BST, reply)[0] is None


# ---- near-duplicate questions ---------------------------------------------------------


def test_real_rotation_questions_with_the_same_quote_are_duplicates():
    first = clean(example("rotation", "what does rotation do"))
    assert quiz.near_duplicate(clean(example("rotation", "purpose of rotation")), [first])


def test_real_bst_questions_with_the_same_long_answer_are_duplicates():
    first = clean(example("binary_search_tree", "what can happen"))
    assert quiz.near_duplicate(clean(example("binary_search_tree", "potential problem")), [first])


def test_nearly_the_same_wording_is_a_duplicate():
    def row(question):
        return {"question": question, "answer": "x", "source_quote": question}

    one = row("What is the height of an AVL tree?")
    assert quiz.near_duplicate(row("What is the height of AVL trees?"), [one])


def test_different_real_questions_on_a_topic_are_not_duplicates():
    rows = [clean(e) for e in EXAMPLES if e["concept_id"] == "rotation"]
    when, height = rows[1], rows[3]
    assert not quiz.near_duplicate(when, [rows[0]])
    assert not quiz.near_duplicate(height, [rows[0], when])


def test_the_same_short_answer_to_different_questions_is_not_a_duplicate():
    """Real AVL drafts: depth and update time are different facts, both O(log n)."""
    depth = {
        "question": "What is the maximum depth of an AVL tree with n nodes?",
        "answer": "O(log n)",
        "source_quote": "it has a depth of at most O(log n).",
    }
    updates = {
        "question": "What is the time complexity of insert and delete operations in an AVL tree?",
        "answer": "O(log n)",
        "source_quote": "updates will also cost O(log n), even in the worst case.",
    }
    assert not quiz.near_duplicate(updates, [depth])
