"""The level ladder: its rules, its state in the mastery dict, and old quiz files. No LLM."""

import inspect
import itertools
import json

import pytest

from cdlp.learning_path import api, ladder
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check_file

GRAPH = read_json(EXAMPLES / "validated_graph.json")
OLD_QUIZ = read_json(EXAMPLES / "quiz_items.json")
QUIZ = read_json(EXAMPLES / "ladder_quiz_items.json")
ORDER = ["recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"]
TARGET = "avl_tree"
STRATEGY = "ladder_linear"


def play(script, *, quiz=QUIZ, target=TARGET, strategy=STRATEGY):
    """script: {concept: (self-report, [right or wrong, ...])}. Returns (mastery, items asked)."""
    mastery: dict = {}
    asked = []
    positions = {c: 0 for c in script}
    while True:
        step = api.ladder_next(GRAPH, quiz, mastery, target, strategy)
        if step is None:
            return mastery, asked
        if "self_report" in step:
            concept = step["self_report"]
            mastery = api.ladder_self_report(mastery, concept, script[concept][0])
            continue
        concept = step["concept_id"]
        correct = script[concept][1][positions[concept]]
        positions[concept] += 1
        mastery = api.ladder_record(GRAPH, quiz, mastery, target, step, correct, strategy)
        asked.append(step["id"])


def results(mastery, quiz=QUIZ, target=TARGET, strategy=STRATEGY):
    rows = api.ladder_summary(GRAPH, quiz, mastery, target, strategy)["rows"]
    return {r["concept_id"]: r["result"] for r in rows}


KNOWS_ALL = {c: ("yes", [True, True]) for c in ORDER}


# --- rule 1: the self-report only sets the starting level ---------------------------------


def test_topics_come_in_graph_order_and_each_starts_with_the_question():
    assert api.prerequisite_order(GRAPH, TARGET) == ORDER
    assert api.ladder_next(GRAPH, QUIZ, {}, TARGET, STRATEGY) == {"self_report": "recursion"}


@pytest.mark.parametrize("answer, level", [("yes", "medium"), ("no", "easy"), ("not_sure", "easy")])
def test_the_answer_sets_only_the_starting_level(answer, level):
    mastery = api.ladder_self_report({}, "recursion", answer)
    step = api.ladder_next(GRAPH, QUIZ, mastery, TARGET, STRATEGY)
    assert step["concept_id"] == "recursion" and step["difficulty"] == level
    assert "recursion" not in mastery  # no mastery value: nothing is marked known
    assert api.personalized_path(GRAPH, mastery, TARGET)[0]["concept_id"] == "recursion"


def test_a_bad_self_report_is_refused():
    with pytest.raises(ValueError):
        api.ladder_self_report({}, "recursion", "maybe")


# --- rules 2 and 3: every route through a topic --------------------------------------------


@pytest.mark.parametrize(
    "start, answers, asked_levels, result",
    [
        ("yes", [True, True], ["medium", "hard"], "know_it"),
        ("yes", [True, False], ["medium", "hard"], "quick_revision"),
        ("yes", [False, True], ["medium", "easy"], "study_this"),
        ("yes", [False, False], ["medium", "easy"], "start_here"),
        ("no", [True, True, True], ["easy", "medium", "hard"], "know_it"),
        ("no", [True, True, False], ["easy", "medium", "hard"], "quick_revision"),
        ("no", [True, False], ["easy", "medium"], "study_this"),
        ("no", [False], ["easy"], "start_here"),
        ("not_sure", [True, False], ["easy", "medium"], "study_this"),
        ("not_sure", [False], ["easy"], "start_here"),
    ],
)
def test_every_route_through_a_topic(start, answers, asked_levels, result):
    script = {c: ("yes", [True, True]) for c in ORDER}
    script["recursion"] = (start, answers)
    mastery, asked = play(script)
    assert results(mastery)["recursion"] == result
    levels = {i["id"]: i["difficulty"] for i in QUIZ["items"]}
    assert [levels[i] for i in asked if "recursion" in i] == asked_levels


def test_know_it_is_the_only_result_above_the_mastery_threshold():
    assert [r for r, m in ladder.RESULT_MASTERY.items() if m > api.MASTERY_THRESHOLD] == ["know_it"]


def test_easy_wrong_stops_the_quiz_and_later_topics_are_not_checked():
    script = {"recursion": ("yes", [True, True]), "trees": ("no", [False])}
    mastery, asked = play(script)
    assert api.ladder_next(GRAPH, QUIZ, mastery, TARGET, STRATEGY) is None
    got = results(mastery)
    assert got["recursion"] == "know_it" and got["trees"] == "start_here"
    assert [got[c] for c in ORDER[2:]] == ["not_checked"] * 3
    summary = api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)
    assert summary["stopped_at"] == "trees" and not summary["limit_reached"]
    assert summary["not_checked_after_stop"] == ORDER[2:]
    assert not any("binary" in i or "avl" in i for i in asked)
    assert "binary_tree" not in mastery  # not checked is never a guess


def test_study_this_and_quick_revision_keep_going():
    script = {c: ("yes", [True, True]) for c in ORDER}
    script["recursion"] = ("no", [True, False])
    script["trees"] = ("yes", [True, False])
    mastery, _ = play(script)
    assert [results(mastery)[c] for c in ORDER] == [
        "study_this",
        "quick_revision",
        "know_it",
        "know_it",
        "know_it",
    ]


def test_a_later_right_answer_never_lifts_an_earlier_result():
    """update_mastery's propagation would mark recursion known here."""
    script = {c: ("yes", [True, True]) for c in ORDER}
    script["recursion"] = ("no", [True, False])
    mastery, _ = play(script)
    assert mastery["recursion"] == ladder.RESULT_MASTERY["study_this"]
    plan = [s["concept_id"] for s in api.personalized_path(GRAPH, mastery, TARGET)]
    assert plan == ["recursion"]


# --- rule 4: no repeats, nearest level, the limit ------------------------------------------


@pytest.mark.parametrize("answers", itertools.product([True, False], repeat=3))
@pytest.mark.parametrize("start", ["yes", "no"])
def test_no_question_is_asked_twice(start, answers):
    mastery, asked = play({c: (start, list(answers)) for c in ORDER})
    assert len(asked) == len(set(asked))
    assert len(asked) <= api.MAX_QUESTIONS_PER_TOPIC
    assert mastery["__asked__"] == asked


def levels_only(*levels, concept="recursion"):
    return [
        {
            "id": f"i{n}",
            "concept_id": concept,
            "question": "q",
            "options": ["a", "b"],
            "answer": "a",
        }
        | ({"difficulty": level} if level else {})
        for n, level in enumerate(levels)
    ]


def test_nearest_level_stands_in_and_it_is_recorded():
    items = levels_only("medium", "medium")
    mastery = api.ladder_self_report({}, "recursion", "no")
    first = api.ladder_next(GRAPH, items, mastery, "recursion", STRATEGY)
    assert first["id"] == "i0"
    mastery = api.ladder_record(GRAPH, items, mastery, "recursion", first, True, STRATEGY)
    topic = mastery["__ladder__"]["topics"]["recursion"]
    assert topic["stand_ins"] == [{"wanted": "easy", "used": "medium", "item_id": "i0"}]
    rows = api.ladder_summary(GRAPH, items, mastery, "recursion", STRATEGY)["rows"]
    assert rows[0]["stand_ins"] == topic["stand_ins"]


def test_a_tie_between_levels_takes_the_easier_one():
    items = levels_only("hard", "easy")
    assert ladder.pick_item(items, {}, "recursion", "medium")["difficulty"] == "easy"


def test_unlabelled_items_count_as_easy_and_can_stand_in():
    items = levels_only(None, "hard")
    assert ladder.level_of(items[0]) == "easy"
    assert ladder.pick_item(items, {}, "recursion", "easy")["id"] == "i0"
    assert ladder.pick_item(items, {"__asked__": ["i1"]}, "recursion", "medium")["id"] == "i0"


@pytest.mark.parametrize(
    "start, levels, answers, result",
    [
        ("no", ["easy"], [True], "study_this"),  # no medium left to try
        ("no", ["easy", "medium"], [True, True], "quick_revision"),  # no hard left to try
        ("yes", ["medium"], [False], "study_this"),  # no easy left to try
        ("yes", ["medium"], [True], "quick_revision"),
    ],
)
def test_no_question_left_never_claims_more_than_the_answers(start, levels, answers, result):
    items = levels_only(*levels)
    mastery, _ = play({"recursion": (start, answers)}, quiz=items, target="recursion")
    assert results(mastery, items, "recursion")["recursion"] == result


def test_a_topic_with_no_questions_is_not_checked_and_is_skipped():
    items = [i for i in QUIZ["items"] if i["concept_id"] != "recursion"]
    assert api.ladder_next(GRAPH, items, {}, TARGET, STRATEGY) == {"self_report": "trees"}
    mastery, asked = play({c: ("yes", [True, True]) for c in ORDER[1:]}, quiz=items)
    got = results(mastery, items)
    assert got["recursion"] == "not_checked" and got["trees"] == "know_it"
    assert asked


def test_the_limit_stops_at_ten_and_unasked_topics_are_not_checked(monkeypatch):
    monkeypatch.setattr(api, "MAX_QUESTIONS_PER_TOPIC", 5)
    mastery, asked = play({c: ("no", [True, True, True]) for c in ORDER})
    assert len(asked) == 5
    got = results(mastery)
    assert got["recursion"] == "know_it"
    assert got["trees"] == "not_checked"  # its answers so far prove no result: still on the plan
    assert got["avl_tree"] == "not_checked"
    assert api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)["limit_reached"]
    assert api.MAX_QUESTIONS_PER_TOPIC == 5


def test_the_real_limit_value_is_unchanged():
    assert api.MAX_QUESTIONS_PER_TOPIC == 10


def test_results_carry_to_another_target_and_its_count_is_separate():
    mastery, _ = play({"recursion": ("yes", [True, True])}, target="recursion")
    step = api.ladder_next(GRAPH, QUIZ, mastery, TARGET, STRATEGY)
    assert step == {"self_report": "trees"}
    assert mastery["__ladder__"]["asked_for_target"] == {"recursion": 2}


# --- rule 5: what the plan reads -----------------------------------------------------------


def test_the_plan_starts_at_the_first_topic_that_is_not_know_it():
    script = {c: ("yes", [True, True]) for c in ORDER}
    script["binary_search_tree"] = ("yes", [True, False])
    script["avl_tree"] = ("no", [False])
    mastery, _ = play(script)
    summary = api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)
    assert summary["known"] == ORDER[:3]
    assert summary["first_to_study"] == "binary_search_tree"
    plan = api.personalized_path(GRAPH, mastery, TARGET)
    assert [s["concept_id"] for s in plan] == ["binary_search_tree", "avl_tree"]


def test_everything_known_leaves_nothing_to_study():
    mastery, _ = play(KNOWS_ALL)
    assert api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)["first_to_study"] is None
    assert api.personalized_path(GRAPH, mastery, TARGET) == []


# --- ladder_middle -------------------------------------------------------------------------


def test_middle_starts_in_the_middle_and_know_it_infers_ancestors():
    assert api.ladder_next(GRAPH, QUIZ, {}, TARGET, "ladder_middle") == {
        "self_report": "binary_tree"
    }
    mastery, asked = play(
        {
            "binary_tree": ("yes", [True, True]),
            "binary_search_tree": ("yes", [True, True]),
            "avl_tree": ("yes", [True, True]),
        },
        strategy="ladder_middle",
    )
    rows = api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, "ladder_middle")["rows"]
    by_id = {r["concept_id"]: r for r in rows}
    assert by_id["trees"]["result"] == "know_it" and by_id["trees"]["inferred"]
    assert by_id["recursion"]["inferred"] and not by_id["binary_tree"]["inferred"]
    assert not any("recursion" in i or "q_trees" in i for i in asked)


def test_middle_moves_earlier_after_a_gap_and_never_asks_past_it():
    script = {c: ("yes", [False, True]) for c in ORDER}
    script["binary_tree"] = ("no", [False])
    mastery, asked = play(script, strategy="ladder_middle")
    got = results(mastery, strategy="ladder_middle")
    assert got["binary_tree"] == "start_here"
    assert got["binary_search_tree"] == got["avl_tree"] == "not_checked"
    assert any("recursion" in i or "q_trees" in i for i in asked)
    summary = api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, "ladder_middle")
    assert summary["stopped_at"] is None


# --- rule 6: old quiz files, rule 8: stable api, rule 10: one config value -----------------


def test_old_quiz_files_keep_the_old_selection_and_stay_valid():
    assert not api.uses_ladder(OLD_QUIZ)
    assert not api.uses_ladder(OLD_QUIZ["items"])
    assert check_file(EXAMPLES / "quiz_items.json") == []
    assert api.next_question(GRAPH, OLD_QUIZ, {}, TARGET)["concept_id"] == "binary_tree"


def test_a_course_with_levels_uses_the_ladder_and_the_file_is_valid():
    assert api.uses_ladder(QUIZ)
    assert check_file(EXAMPLES / "ladder_quiz_items.json") == []
    assert {i["difficulty"] for i in QUIZ["items"]} == set(ladder.LEVELS)


def test_the_public_signatures_are_stable():
    assert list(inspect.signature(api.next_question).parameters) == [
        "graph",
        "quiz",
        "mastery",
        "target",
    ]
    assert list(inspect.signature(api.update_mastery).parameters) == [
        "graph",
        "mastery",
        "concept_id",
        "correct",
    ]
    assert list(inspect.signature(api.personalized_path).parameters) == [
        "graph",
        "mastery",
        "target",
    ]


def test_ladder_state_sits_in_the_mastery_dict_and_the_old_api_still_reads_it():
    mastery, _ = play(KNOWS_ALL)
    assert "__ladder__" in mastery and "__asked__" in mastery
    json.dumps(mastery)  # session state and any later saving need plain data
    assert api.update_mastery(GRAPH, mastery, "trees", False)["trees"] == 0.1
    assert api.next_question(GRAPH, QUIZ, mastery, TARGET) is None


def test_inputs_are_never_changed():
    before = api.ladder_self_report({}, "recursion", "yes")
    snapshot = json.dumps(before, sort_keys=True)
    step = api.ladder_next(GRAPH, QUIZ, before, TARGET, STRATEGY)
    api.ladder_record(GRAPH, QUIZ, before, TARGET, step, True, STRATEGY)
    assert json.dumps(before, sort_keys=True) == snapshot


def test_quick_check_shows_ladder_linear_from_one_config_value(tmp_path, monkeypatch):
    assert ladder.configured_strategy() == "ladder_linear"
    config = tmp_path / "quick_check.json"
    monkeypatch.setattr(ladder, "CONFIG", config)
    config.write_text('{"strategy": "ladder_middle"}')
    assert api.ladder_next(GRAPH, QUIZ, {}, TARGET) == {"self_report": "binary_tree"}
    config.write_text('{"strategy": "adaptive"}')
    assert not api.uses_ladder(QUIZ)
    config.write_text('{"strategy": "nonsense"}')
    with pytest.raises(ValueError):
        api.uses_ladder(QUIZ)
