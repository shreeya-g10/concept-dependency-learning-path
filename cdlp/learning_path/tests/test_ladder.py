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
    assert not summary["limit_reached"]
    assert summary["stops"] == [
        {
            "concept_id": "trees",
            "not_checked": ORDER[2:],
            "stops_everything_later": True,
            "still_asked": [],
        }
    ]
    assert not any("binary" in i or "avl" in i for i in asked)
    assert "binary_tree" not in mastery  # not checked is never a guess


def test_a_gap_on_a_soft_link_skips_nothing():
    """Recursion -soft-> Binary Trees: everything is still asked, and the note can say so."""
    script = {c: ("yes", [True, True]) for c in ORDER}
    script["recursion"] = ("no", [False])
    mastery, asked = play(script)
    got = results(mastery)
    assert got["recursion"] == "start_here"
    assert [got[c] for c in ORDER[1:]] == ["know_it"] * 4
    assert any("avl" in i for i in asked)
    assert api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)["stops"] == [
        {
            "concept_id": "recursion",
            "not_checked": [],
            "stops_everything_later": False,
            "still_asked": ["binary_tree"],
        }
    ]


def test_a_gap_on_hard_links_skips_what_depends_on_it():
    script = {"recursion": ("yes", [True, True]), "trees": ("no", [False])}
    mastery, asked = play(script)
    assert [results(mastery)[c] for c in ORDER[2:]] == ["not_checked"] * 3
    assert not any("binary" in i or "avl" in i for i in asked)
    plan = [s["concept_id"] for s in api.personalized_path(GRAPH, mastery, TARGET)]
    assert plan == ORDER[1:]


def test_two_gaps_each_count_and_a_skipped_topic_is_never_called_still_asked():
    mastery, _ = play({"recursion": ("no", [False]), "trees": ("no", [False])})
    stops = api.ladder_summary(GRAPH, QUIZ, mastery, TARGET, STRATEGY)["stops"]
    assert [s["concept_id"] for s in stops] == ["recursion", "trees"]
    assert stops[0]["still_asked"] == []  # Binary Trees was skipped because of Trees
    assert stops[1]["not_checked"] == ORDER[2:]
    assert api.ladder_next(GRAPH, QUIZ, mastery, TARGET, STRATEGY) is None


def linked_graph(links):
    edge = {"type": "PREREQUISITE", "decision": "ACCEPT"}
    names = sorted({c for a, b, _ in links for c in (a, b)})
    return {
        "nodes": [{"id": c} for c in names],
        "edges": [
            {**edge, "id": f"e{n}", "source": a, "target": b, "strength": strength}
            for n, (a, b, strength) in enumerate(links)
        ],
    }


def test_a_hard_link_after_a_soft_one_does_not_make_a_topic_depend():
    graph = linked_graph([("a", "b", "soft"), ("b", "c", "hard"), ("a", "d", "hard")])
    G = ladder.load_graph(graph)
    assert ladder.hard_dependents(G, "a") == {"d"}
    assert ladder.hard_dependents(G, "b") == {"c"}
    assert ladder.hard_dependents(G, "c") == set()


def test_a_link_with_no_strength_counts_as_hard_like_the_rest_of_the_module():
    graph = linked_graph([("a", "b", "hard")])
    del graph["edges"][0]["strength"]
    assert ladder.hard_dependents(ladder.load_graph(graph), "a") == {"b"}


def test_middle_closes_only_hard_dependents():
    script = {c: ("no", [False]) for c in ORDER}
    mastery, asked = play(script, strategy="ladder_middle")
    assert any("recursion" in i for i in asked)  # still asked, though Binary Trees failed first


def chain_graph(concepts):
    edge = {"type": "PREREQUISITE", "strength": "hard", "decision": "ACCEPT"}
    return {
        "nodes": [{"id": c} for c in concepts],
        "edges": [
            {**edge, "id": f"e{n}", "source": a, "target": b}
            for n, (a, b) in enumerate(zip(concepts, concepts[1:], strict=False))
        ],
    }


@pytest.mark.parametrize("start", ["yes", "no"])
@pytest.mark.parametrize("answers", itertools.product([True, False], repeat=4))
def test_a_straight_chain_ends_at_the_first_gap(start, answers):
    """A straight chain has nothing unrelated: nothing after the first gap is ever asked."""
    concepts = ["a", "b", "c"]
    graph = chain_graph(concepts)
    items = [
        {"id": f"{c}_{v}", "concept_id": c, "question": "q", "options": ["x", "y"], "answer": "x"}
        | {"difficulty": v}
        for c in concepts
        for v in ladder.LEVELS
    ]
    mastery: dict = {}
    remaining = list(answers) * 3
    while (step := api.ladder_next(graph, items, mastery, "c", STRATEGY)) is not None:
        if "self_report" in step:
            mastery = api.ladder_self_report(mastery, step["self_report"], start)
        else:
            correct = remaining.pop(0)
            mastery = api.ladder_record(graph, items, mastery, "c", step, correct, STRATEGY)
    rows = api.ladder_summary(graph, items, mastery, "c", STRATEGY)["rows"]
    got = [r["result"] for r in rows]
    if "start_here" in got:
        gap = got.index("start_here")
        assert got[gap + 1 :] == ["not_checked"] * (len(got) - gap - 1)
        assert all(r["questions"] == 0 for r in rows[gap + 1 :])
    else:
        assert "not_checked" not in got


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


@pytest.mark.parametrize("left_over", ["medium", "easy"])
def test_nothing_stands_in_for_hard_and_no_hard_question_is_recorded(left_over):
    items = levels_only("medium", left_over)
    mastery, asked = play({"recursion": ("yes", [True])}, quiz=items, target="recursion")
    assert asked == ["i0"]  # the left-over question is not asked: it could not change the result
    assert mastery["recursion"] == ladder.RESULT_MASTERY["quick_revision"]
    row = api.ladder_summary(GRAPH, items, mastery, "recursion", STRATEGY)["rows"][0]
    assert row["result"] == "quick_revision" and row["no_hard_question"]
    assert row["stand_ins"] == []


def test_easy_and_medium_stand_ins_stay_as_they_were():
    items = levels_only("hard", "hard", "hard")
    mastery, asked = play({"recursion": ("no", [True, True, True])}, quiz=items, target="recursion")
    row = api.ladder_summary(GRAPH, items, mastery, "recursion", STRATEGY)["rows"][0]
    assert asked == ["i0", "i1", "i2"]
    assert [s["wanted"] for s in row["stand_ins"]] == ["easy", "medium"]
    assert row["result"] == "know_it" and not row["no_hard_question"]


def test_the_only_hard_question_used_up_earlier_leaves_no_hard_question():
    items = levels_only("hard")
    mastery, asked = play({"recursion": ("yes", [True])}, quiz=items, target="recursion")
    row = api.ladder_summary(GRAPH, items, mastery, "recursion", STRATEGY)["rows"][0]
    assert asked == ["i0"] and row["no_hard_question"] and row["result"] == "quick_revision"


def test_a_real_hard_question_still_earns_know_it_after_an_earlier_stand_in():
    items = levels_only("hard", "hard")  # the medium slot is filled by a hard question
    mastery, _ = play({"recursion": ("yes", [True, True])}, quiz=items, target="recursion")
    rows = api.ladder_summary(GRAPH, items, mastery, "recursion", STRATEGY)["rows"]
    assert rows[0]["result"] == "know_it"
    assert rows[0]["stand_ins"] == [{"wanted": "medium", "used": "hard", "item_id": "i0"}]


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
    assert summary["stops"] == []


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
