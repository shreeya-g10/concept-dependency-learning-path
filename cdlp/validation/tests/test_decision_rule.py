"""The decision rule on its own: structural rules, score thresholds, vetoes."""

import pytest

from cdlp.validation import __main__ as cli
from cdlp.validation import graph_checks as g

CFG = cli.load_decision_config()


def decide(label=g.OK, evidence="strong", semantic="strong", necessity="strong", **kw):
    return cli.decide(
        label, {"evidence": evidence, "semantic": semantic, "necessity": necessity}, CFG, **kw
    )


def test_all_strong_is_accept():
    decision, confidence, _ = decide()
    assert (decision, confidence) == ("ACCEPT", 1.0)


@pytest.mark.parametrize("label, word", [(g.SELF_LOOP, "self-loop"), (g.DUPLICATE, "duplicate")])
def test_self_loop_and_duplicate_are_rejected(label, word):
    decision, confidence, reason = decide(label)
    assert (decision, confidence) == ("REJECT", 1.0) and word in reason


def test_redundant_is_rejected_with_the_path():
    decision, _, reason = decide(g.REDUNDANT, implied_path=["trees", "binary_tree", "bst"])
    assert decision == "REJECT"
    assert reason == "Redundant: implied by trees → binary_tree → bst."


@pytest.mark.parametrize("kw", [{"bidirectional": True}, {"label": g.CONTRADICTION}])
def test_bidirectional_and_contradiction_go_to_review(kw):
    assert decide(**kw)[0] == "HUMAN_REVIEW"


def test_cycle_is_never_accepted():
    assert decide(g.CYCLE)[0] == "HUMAN_REVIEW"
    assert decide(g.CYCLE, evidence="none", semantic="none", necessity="none")[0] == "REJECT"


def test_no_support_from_evidence_and_semantic_is_rejected():
    # necessity alone (unreliable so far) cannot rescue an edge nobody else supports
    decision, _, reason = decide(evidence="none", semantic="weak", necessity="strong")
    assert decision == "REJECT" and "neither the material" in reason


def test_a_none_grade_blocks_accept():
    assert decide(evidence="strong", semantic="strong", necessity="none")[0] == "HUMAN_REVIEW"


def test_middling_score_goes_to_review():
    assert decide(evidence="medium", semantic="weak", necessity="medium")[0] == "HUMAN_REVIEW"


def test_low_score_is_rejected():
    assert decide(evidence="weak", semantic="medium", necessity="none")[0] == "REJECT"


def test_skipped_checks_are_left_out_of_the_score():
    decision, _, reason = decide(necessity=None)
    assert decision == "ACCEPT" and "necessity" not in reason
    assert cli.score({"evidence": "strong", "semantic": None, "necessity": None}, CFG) == 1.0


def test_no_check_at_all_goes_to_review():
    assert decide(evidence=None, semantic=None, necessity=None)[0] == "HUMAN_REVIEW"


@pytest.mark.parametrize(
    "skipped, name",
    [
        (set(), "full_agent"),
        ({"evidence"}, "minus_evidence"),
        ({"graph", "semantic"}, "minus_semantic_graph"),
    ],
)
def test_setting_names(skipped, name):
    assert cli.setting_name(skipped) == name


def test_implied_by_uses_other_acyclic_edges():
    rels = [
        {"id": "r1", "source": "a", "target": "b"},
        {"id": "r2", "source": "b", "target": "c"},
        {"id": "r3", "source": "a", "target": "c"},
    ]
    labels = g.graph_labels_by_id(rels)

    assert labels["r3"] == g.REDUNDANT
    assert cli.implied_by(rels[2], rels, labels) == ["a", "b", "c"]
