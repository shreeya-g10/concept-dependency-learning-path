"""Unit tests for chain, baselines, LLM tracer, CLI and evaluator. The LLM is always mocked."""

import json
from pathlib import Path

import pytest
import requests

from cdlp.root_cause import __main__ as cli
from cdlp.root_cause import api, evaluate, tracer
from cdlp.root_cause.baselines import blame_nearest, blame_target
from cdlp.root_cause.chain import prerequisite_chain
from cdlp.shared import llm
from cdlp.shared.io import EXAMPLES, read_json
from cdlp.shared.validate import check

DEV_SET = Path(__file__).parent / "fixtures" / "dev_set.json"
GRAPH = read_json(EXAMPLES / "validated_graph.json")
ITEMS = {i["id"]: i for i in read_json(EXAMPLES / "quiz_items.json")["items"]}


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", fail)
    monkeypatch.setattr(llm, "chat_json", fail)


def fake_llm(monkeypatch, reply):
    calls = []

    def chat_json(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "chat_json", chat_json)
    return calls


def wrap(result):
    return {
        "schema_version": "1.1",
        "course_id": "ds101",
        "traces": [{"student_id": "s", **result}],
    }


# chain --------------------------------------------------------------------------------


def test_chain_is_accept_only_and_nearest_first():
    chain = prerequisite_chain(GRAPH, "avl_tree")
    ids = [c["concept_id"] for c in chain]
    # graphs -> avl_tree is REJECT and trees -> graphs is HUMAN_REVIEW: graphs is not in it
    assert ids == ["avl_tree", "binary_search_tree", "binary_tree", "recursion", "trees"]
    assert [c["distance"] for c in chain] == [0, 1, 2, 3, 3]
    recursion = next(c for c in chain if c["concept_id"] == "recursion")
    assert recursion["prerequisite_of"] == [{"concept_id": "binary_tree", "strength": "soft"}]


def test_chain_of_unknown_concept_is_just_itself():
    assert [c["concept_id"] for c in prerequisite_chain(GRAPH, "nope")] == ["nope"]


# baselines ----------------------------------------------------------------------------


def test_blame_target_ranks_target_then_chain():
    r = blame_target(GRAPH, ITEMS["q_avl_1"], "10", {})
    assert r["traced_concept"] == "avl_tree"
    assert [c["concept_id"] for c in r["candidates"]][:2] == ["avl_tree", "binary_search_tree"]
    assert check(wrap(r), "root_cause") == []


def test_blame_nearest_picks_lowest_mastery_direct_prerequisite():
    mastery = {"trees": 0.2, "recursion": 0.6}
    r = blame_nearest(GRAPH, ITEMS["q_bt_1"], "3", mastery)
    assert [c["concept_id"] for c in r["candidates"]] == ["trees", "recursion", "binary_tree"]
    scores = [c["score"] for c in r["candidates"]]
    assert scores == sorted(scores, reverse=True) and abs(sum(scores) - 1) < 1e-3
    assert check(wrap(r), "root_cause") == []


def test_blame_nearest_with_no_mastery_breaks_ties_by_distance_then_id():
    # RQ3 setting: no mastery. trees and recursion are both distance 1 from binary_tree
    r = blame_nearest(GRAPH, ITEMS["q_bt_1"], "3", {})
    assert [c["concept_id"] for c in r["candidates"]] == ["recursion", "trees", "binary_tree"]
    # deeper chain: the direct prerequisite first, then target, then by distance, then id
    r = blame_nearest(GRAPH, ITEMS["q_avl_1"], "30", {})
    ids = [c["concept_id"] for c in r["candidates"]]
    assert ids == ["binary_search_tree", "avl_tree", "binary_tree", "recursion", "trees"]


def test_blame_nearest_known_mastery_beats_unknown():
    r = blame_nearest(GRAPH, ITEMS["q_bt_1"], "3", {"trees": 0.4})  # recursion unknown (0.5)
    assert r["traced_concept"] == "trees"


def test_blame_nearest_without_prerequisites_blames_target():
    r = blame_nearest(GRAPH, ITEMS["q_rec_1"], "A loop counter", {"recursion": 0.1})
    assert r["traced_concept"] == "recursion" and len(r["candidates"]) == 1


# LLM tracer ---------------------------------------------------------------------------


def test_prompt_has_question_answers_and_chain_with_mastery():
    item = ITEMS["q_avl_1"]
    chain = prerequisite_chain(GRAPH, "avl_tree")
    prompt = tracer.build_prompt(item, "10", chain, {"binary_search_tree": 0.15})
    assert "Insert 10, 20, 30 into an empty AVL tree" in prompt
    assert "Student's answer: 10" in prompt and "Correct answer: 20" in prompt
    assert '- binary_search_tree "Binary Search Trees" (hard prerequisite of avl_tree)' in prompt
    assert "mastery 0.15" in prompt and "mastery unknown" in prompt
    assert "{" + "chain}" not in prompt and "{" + "target}" not in prompt


def test_few_shot_examples_are_from_another_domain():
    text = tracer.PROMPT_FILE.read_text()
    examples = text.split("Now the real case.")[0]
    for course_word in ("tree", "BST", "AVL", "recursion", "regression", "matrix", "vector"):
        assert course_word.lower() not in examples.lower()


def test_llm_trace_uses_versioned_prompt_and_cleans_output(monkeypatch):
    calls = fake_llm(
        monkeypatch,
        {
            "candidates": [
                {"concept_id": "binary_search_tree", "score": 1.2},  # clamped to 1
                {"concept_id": "graphs", "score": 0.5},  # not in the ACCEPT chain: dropped
                {"concept_id": "avl_tree", "score": 0.6},
                {"concept_id": "binary_search_tree", "score": 0.1},  # duplicate: dropped
                {"concept_id": "trees", "score": "high"},  # not a number: dropped
            ],
            "explanation": "The ordering rule\n is missing.",
        },
    )
    r = api.trace(GRAPH, ITEMS["q_avl_1"], "30", {"binary_search_tree": 0.15})

    assert calls[0]["prompt_version"] == "trace_v1" and calls[0]["temperature"] == 0.0
    ids = [c["concept_id"] for c in r["candidates"]]
    assert ids == ["binary_search_tree", "avl_tree", "binary_tree", "recursion", "trees"]
    assert r["candidates"][0]["score"] == pytest.approx(1 / 1.6, abs=1e-3)
    assert r["confidence"] == r["candidates"][0]["score"]
    assert r["traced_concept"] == "binary_search_tree"
    assert r["explanation"] == "The ordering rule is missing."
    assert check(wrap(r), "root_cause") == []


@pytest.mark.parametrize(
    "reply",
    [
        {"candidates": [{"concept_id": "graphs", "score": 1}]},
        {"candidates": []},
        {"something": "else"},
        ["not", "a", "dict"],
        json.JSONDecodeError("bad", "x", 0),
    ],
)
def test_unusable_llm_output_falls_back_to_nearest(monkeypatch, reply):
    fake_llm(monkeypatch, reply)
    r = api.trace(GRAPH, ITEMS["q_avl_1"], "30", {})
    assert r["explanation"].startswith(tracer.FALLBACK_PREFIX)
    assert r["traced_concept"] == "binary_search_tree"
    assert check(wrap(r), "root_cause") == []


def test_connection_errors_are_not_hidden(monkeypatch):
    fake_llm(monkeypatch, ConnectionError("no LLM"))
    with pytest.raises(ConnectionError):
        api.trace(GRAPH, ITEMS["q_avl_1"], "30", {})


def test_concept_without_prerequisites_makes_no_llm_call(monkeypatch):
    calls = fake_llm(monkeypatch, {})
    r = api.trace(GRAPH, ITEMS["q_rec_1"], "A loop counter", {})
    assert calls == [] and r["traced_concept"] == "recursion" and r["confidence"] == 1.0


# CLI ----------------------------------------------------------------------------------


def test_cli_traces_only_wrong_answers_with_student_mastery(monkeypatch):
    calls = fake_llm(
        monkeypatch,
        {"candidates": [{"concept_id": "binary_tree", "score": 1}], "explanation": "x"},
    )
    answers = read_json(EXAMPLES / "student_answers.json")
    state = cli.mastery_by_student(EXAMPLES / "student_state.json")
    out = cli.run(GRAPH, read_json(EXAMPLES / "quiz_items.json"), answers, state, "llm")

    wrong = [a for a in answers["answers"] if not a["correct"]]
    assert [(t["student_id"], t["item_id"]) for t in out["traces"]] == [
        (a["student_id"], a["item_id"]) for a in wrong
    ]
    # q_rec_1 has no prerequisites, so one call fewer than wrong answers
    assert len(calls) == len(wrong) - 1
    line = '- binary_tree "Binary Trees" (hard prerequisite of binary_search_tree), mastery 0.15'
    assert line in calls[0]["prompt"]  # student_a's binary_tree mastery
    assert check(out, "root_cause") == []


# dev set and evaluator ----------------------------------------------------------------


def test_dev_set_is_valid_and_uses_example_items():
    dev = read_json(DEV_SET)
    assert check(dev, "root_cause_testset") == []
    assert len(dev["answers"]) == 10
    for row in dev["answers"]:
        assert row["item_id"] in ITEMS and not row["correct"]
        assert row["concept_id"] == ITEMS[row["item_id"]]["concept_id"]
        assert row["answer"] in ITEMS[row["item_id"]]["options"]
        assert row["answer"] != ITEMS[row["item_id"]]["answer"]
        chain = [c["concept_id"] for c in prerequisite_chain(GRAPH, row["concept_id"])]
        assert row["expected_concept"] in chain


def test_evaluate_baselines_on_dev_set():
    dev, quiz = read_json(DEV_SET), read_json(EXAMPLES / "quiz_items.json")
    target = evaluate.evaluate(GRAPH, quiz, dev, {}, "target")
    nearest = evaluate.evaluate(GRAPH, quiz, dev, {}, "nearest")
    assert target["n"] == nearest["n"] == 10
    assert target["top1_accuracy"] == 0.5  # 5 of the 10 labels are the item's own concept
    assert 0 <= nearest["top1_accuracy"] <= nearest["top3_accuracy"] <= 1


def test_evaluate_llm_counts_fallbacks(monkeypatch):
    fake_llm(monkeypatch, {"candidates": []})
    dev, quiz = read_json(DEV_SET), read_json(EXAMPLES / "quiz_items.json")
    r = evaluate.evaluate(GRAPH, quiz, dev, {}, "llm")
    assert r["llm_fallbacks"] == 9  # every row except the no-prerequisite one


# allow_fallback -----------------------------------------------------------------------


def test_trace_signature_keeps_existing_parameters():
    import inspect

    params = inspect.signature(api.trace).parameters
    assert list(params)[:4] == ["graph", "quiz_item", "answer", "mastery"]
    assert params["allow_fallback"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["allow_fallback"].default is False


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("refused"),
        requests.Timeout("slow"),
        ConnectionRefusedError("refused"),
    ],
)
def test_unreachable_llm_is_strict_by_default(monkeypatch, error):
    fake_llm(monkeypatch, error)
    with pytest.raises(type(error)):
        api.trace(GRAPH, ITEMS["q_avl_1"], "30", {})


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("refused"),
        requests.Timeout("slow"),
        ConnectionRefusedError("refused"),
    ],
)
def test_unreachable_llm_with_allow_fallback_returns_offline_estimate(monkeypatch, error):
    fake_llm(monkeypatch, error)
    mastery = {"binary_search_tree": 0.15}
    r = api.trace(GRAPH, ITEMS["q_avl_1"], "30", mastery, allow_fallback=True)
    expected = blame_nearest(GRAPH, ITEMS["q_avl_1"], "30", mastery)
    assert r["explanation"] == f"{tracer.OFFLINE_PREFIX} {expected['explanation']}"
    assert r["explanation"].startswith("[fallback: offline estimate]")
    assert r["candidates"] == expected["candidates"]
    assert r["traced_concept"] == "binary_search_tree"
    assert check(wrap(r), "root_cause") == []


def test_allow_fallback_does_not_hide_http_errors(monkeypatch):
    fake_llm(monkeypatch, requests.HTTPError("404 model not found"))
    with pytest.raises(requests.HTTPError):
        api.trace(GRAPH, ITEMS["q_avl_1"], "30", {}, allow_fallback=True)


def test_allow_fallback_still_uses_a_reachable_llm(monkeypatch):
    reply = {"candidates": [{"concept_id": "avl_tree", "score": 1}], "explanation": "No rotation."}
    calls = fake_llm(monkeypatch, reply)
    r = api.trace(GRAPH, ITEMS["q_avl_1"], "10", {}, allow_fallback=True)
    assert len(calls) == 1 and r["traced_concept"] == "avl_tree"
    assert r["explanation"] == "No rotation."


def test_evaluate_without_mastery_ignores_row_mastery():
    dev, quiz = read_json(DEV_SET), read_json(EXAMPLES / "quiz_items.json")
    no_m = evaluate.evaluate(GRAPH, quiz, dev, {}, "nearest", use_mastery=False)
    # dev_08 (q_bt_1): no mastery -> trees and recursion tie -> recursion by id
    row = next(r for r in no_m["rows"] if r["student_id"] == "dev_08")
    assert row["ranked"][0] == "recursion"
    with_m = evaluate.evaluate(GRAPH, quiz, dev, {}, "nearest")
    row = next(r for r in with_m["rows"] if r["student_id"] == "dev_08")
    assert row["ranked"][0] == "recursion"  # recursion mastery 0.1 < trees 0.9
