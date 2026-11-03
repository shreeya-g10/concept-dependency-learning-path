"""quiz_check_v3's no-LLM checks. These use made-up text, so they test the rules themselves."""

from __future__ import annotations

from collections import Counter

import pytest

from cdlp.learning_path import quiz
from cdlp.learning_path import quiz_check_v3 as v3

CFG = v3.load_config()
STACK = {"id": "stack", "name": "Stack", "aliases": ["SLList", "Add", "Stacks"]}
AVL = {"id": "avl_tree", "name": "AVL Tree", "aliases": ["AVL", "AVL Trees"]}
RED_BLACK = {"id": "red_black_tree", "name": "Red-Black Tree", "aliases": ["RedBlackTree"]}
ROTATION = {"id": "rotation", "name": "Rotation", "aliases": ["Rotations"]}
GENERAL = {"id": "general_tree", "name": "General Tree", "aliases": ["Tree", "general"]}
BINARY = {"id": "binary_tree", "name": "Binary Tree", "aliases": ["binary", "Binary Trees"]}
BST = {"id": "bst", "name": "Binary Search Tree", "aliases": ["BST"]}
VERTEX = {"id": "vertex", "name": "Vertex", "aliases": []}
ALL = [STACK, AVL, RED_BLACK, ROTATION, GENERAL, BINARY, BST, VERTEX]
TERMS = v3.concept_terms(ALL)
BY_ID = {c["id"]: c for c in ALL}


def missing(question, source):
    return v3.missing_subject(question, source, "", TERMS, BY_ID)


def support(answer, quote):
    return v3.answer_support(answer, quote, CFG, quiz.COMMON_WORDS)


# ---- quote match ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quote", "chunk"),
    [
        ("depth of at most O(log n) here", "the depth of at most O(\\log n) here too"),
        ("nodes are labelled with the order", "Nodes are la-\nbelled with the order"),
        ("the first node visited", "the ﬁrst node\n  visited"),
    ],
)
def test_formatting_does_not_break_a_quote_match(quote, chunk):
    assert v3.quote_chunk(quote, [{"chunk_id": "c", "text": chunk}])
    assert not quiz.quote_chunk(quote, [{"chunk_id": "c", "text": chunk}]) or "ﬁ" in chunk


def test_sentences_in_another_order_still_fail():
    text = "A path is a cycle if the last edge exists. A path is simple if vertices are unique."
    quote = "A path is simple if vertices are unique. A path is a cycle if the last edge exists."
    assert v3.quote_chunk(quote, [{"chunk_id": "c", "text": text}]) is None


def test_changed_words_still_fail():
    text = "Search costs O(\\log n) in the worst case."
    assert v3.quote_chunk("Search costs O(n) in the worst case", [{"text": text}]) is None


# ---- subject ----------------------------------------------------------------------------


def test_question_naming_another_structure_is_dropped_with_the_reason():
    why = missing("What does rotation do in a red-black tree?", "Rotation keeps an AVL tree level.")
    assert why and "red_black_tree" in why and "red black tree" in why


def test_names_written_differently_still_match():
    assert not missing("What is a BinarySearchTree?", "A binary search tree stores keys in order.")
    assert not missing("What is a binary search tree?", "BinarySearchTrees store keys in order.")


def test_the_longest_name_wins():
    assert v3.named_concepts("Is a binary search tree a tree?", TERMS) == [
        ("bst", "binary search tree")
    ]


def test_an_ordinary_word_alias_never_names_a_concept():
    assert v3.named_concepts("What does add do to a tree in general?", TERMS) == []


def test_identifier_aliases_count():
    assert v3.named_concepts("What does an SLList do?", TERMS) == [("stack", "SLList")]


def test_noisy_alias_does_not_stand_in_for_the_concept():
    # stack has the noisy alias SLList: a chunk about SLList does not prove a question on a stack
    assert missing("What is a stack?", "An SLList stores nodes in a chain.")
    assert not missing("What does an SLList store?", "An SLList stores nodes in a chain.")


def test_the_concept_name_is_enough_for_an_alias_in_the_question():
    assert not missing("What is a BST?", "A binary search tree stores keys in order.")


def test_an_alias_two_concepts_claim_is_not_used():
    terms = v3.concept_terms(
        [{**STACK, "aliases": ["Shared List"]}, {**AVL, "aliases": ["Shared List"]}]
    )
    assert v3.named_concepts("What is a shared list?", terms) == []


def test_plural_forms_are_recognised():
    assert not missing("How are vertices stored?", "Each vertex is stored in an array.")


def test_the_chunk_counts_as_well_as_the_quote():
    assert not v3.missing_subject(
        "What is an AVL tree?", "It stays balanced.", "AVL trees are balanced.", TERMS, BY_ID
    )


# ---- answer support ---------------------------------------------------------------------


def test_answer_words_in_the_quote_pass_after_stemming():
    assert (
        support("Elements are added and removed", "Each element is added, then removes it") >= 0.5
    )


def test_a_quote_on_another_point_fails():
    assert support("It can become unbalanced", "An example is shown in Figure 6.5.") == 0


@pytest.mark.parametrize(("answer", "quote"), [("3", "degree of three"), ("two", "at most 2 kids")])
def test_number_words_equal_digits(answer, quote):
    assert support(answer, quote) == 1


def test_symbols_stay_whole():
    assert support("O(n + m)", "The algorithm runs in O(n + m) time.") == 1
    assert support("O(n + m)", "The algorithm has n nodes and m edges.") == 0
    assert support("O(n + m)", "The algorithm runs in O(n) time.") == 0


def test_an_answer_with_no_content_words_has_no_support():
    assert support("the", "the tree") == 0


# ---- wiring -----------------------------------------------------------------------------

CHUNK = {"chunk_id": "c1", "text": "Rotation keeps an AVL tree balanced after each insert."}


def draft(**changes):
    return {
        "question": "What does rotation keep balanced?",
        "options": ["An AVL tree balanced", "A list sorted"],
        "correct_answer": "An AVL tree balanced",
        "source_quote": "Rotation keeps an AVL tree balanced after each insert.",
        **changes,
    }


def topic():
    return {
        "concept": ROTATION,
        "evidence": [CHUNK],
        "items": [],
        "failures": [],
        "excerpts": {},
        "numbered": 0,
        "dropped": [],
        "v3": quiz.v3_context(ALL),
    }


def test_code_checks_drop_before_any_model_call_and_record_why():
    t = topic()
    wrong = draft(question="What does rotation do in a red-black tree?")
    skipped = Counter()
    assert quiz._take_drafts([wrong], t, skipped) == []
    assert skipped == {"subject_not_in_source": 1}
    assert t["dropped"][0]["reason"] == "subject_not_in_source"
    assert "red_black_tree" in t["dropped"][0]["detail"]


def test_unsupported_answer_is_dropped_with_the_share():
    t = topic()
    skipped = Counter()
    wrong = draft(options=["A list sorted", "Queues waiting"], correct_answer="Queues waiting")
    assert quiz._take_drafts([wrong], t, skipped) == []
    assert skipped == {"answer_not_supported": 1}
    assert "0.00" in t["dropped"][0]["detail"]


def test_a_sound_draft_passes_the_code_checks():
    assert len(quiz._take_drafts([draft()], topic(), Counter())) == 1


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ({"verdicts": {"A": True, "B": True}, "quote_proves": "B"}, "check_several_true"),
        ({"verdicts": {"A": True, "B": False}, "quote_proves": "A"}, "check_disagrees"),
        ({"verdicts": {"A": False, "B": True}, "quote_proves": "NONE"}, "check_quote_no_proof"),
    ],
)
def test_second_model_can_veto(monkeypatch, reply, reason):
    full = {"same_subject": True, "about_topic": True, **reply}
    monkeypatch.setattr(quiz, "chat_json", lambda *a, **k: full)
    t = topic()
    new = quiz._take_drafts([draft()], t, Counter())
    skipped = Counter()
    quiz._check_drafts(new, t, "{concept_name}{excerpt}{question}{options}{quote}", None, skipped)
    assert skipped == {reason: 1}
    assert t["items"] == []
    assert t["dropped"][0]["second_model"]["quote_proves"] == reply["quote_proves"]


def test_second_model_reply_is_kept_on_the_item(monkeypatch):
    reply = {
        "verdicts": {"A": False, "B": True},  # the correct option sorts second
        "quote_proves": "B",
        "same_subject": True,
        "about_topic": True,
    }
    monkeypatch.setattr(quiz, "chat_json", lambda *a, **k: reply)
    t = topic()
    new = quiz._take_drafts([draft()], t, Counter())
    quiz._check_drafts(new, t, "{concept_name}{excerpt}{question}{options}{quote}", None, Counter())
    assert t["items"][0]["second_model"] == reply


@pytest.mark.parametrize("field", ["same_subject", "about_topic"])
def test_no_existing_drop_was_loosened(monkeypatch, field):
    reply = {
        "verdicts": {"A": False, "B": True},  # the correct option sorts second
        "quote_proves": "B",
        "same_subject": True,
        "about_topic": True,
        field: False,
    }
    monkeypatch.setattr(quiz, "chat_json", lambda *a, **k: reply)
    t = topic()
    new = quiz._take_drafts([draft()], t, Counter())
    quiz._check_drafts(new, t, "{concept_name}{excerpt}{question}{options}{quote}", None, Counter())
    assert t["items"] == []


def test_the_old_check_version_stays_available():
    t = topic()
    del t["v3"]
    wrong = draft(question="What does rotation do in a red-black tree?")
    assert len(quiz._take_drafts([wrong], t, Counter())) == 1  # v2 had no subject check


def test_generation_names_the_check_version_and_the_drops(monkeypatch):
    bad = draft(question="What does rotation do in a red-black tree?")
    monkeypatch.setattr(quiz, "chat_json", lambda *a, **k: {"items": [bad]})
    data = {"schema_version": "1.0", "course_id": "x", "concepts": [ROTATION]}
    out = quiz.generate_quiz_items(data, [CHUNK], all_concepts=ALL)
    assert out["generation"]["check_version"] == "quiz_check_v3"
    assert out["generation"]["check_prompt_version"] == "quiz_check_v2"
    assert {d["reason"] for d in out["generation"]["dropped"]} == {"subject_not_in_source"}
