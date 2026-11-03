"""The both-orders rule (configs/order_rule_v1.json), and that the refactor changed no prompt."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.discovery import candidates, llm_discovery
from cdlp.shared.validate import check_file

EX = "cdlp/shared/examples"
X = {"id": "binary_tree", "name": "Binary Tree", "description": "A tree with at most two children."}
Y = {"id": "avl_tree", "name": "AVL Tree", "description": "A height-balanced search tree."}
EVIDENCE = [
    {"chunk_id": "c1", "text": "An AVL tree is a binary tree."},
    {"chunk_id": "c2", "text": "Trees have nodes."},
]
# Prompts from the code before format_neutral_prompt was split out (commit d3b4e61).
BEFORE_THE_REFACTOR = {
    "discover_v3": "bd9261f4041a65630e114136da4124e0a077990c7554f88f1855937ec0891b35",
    "discover_v3_1": "efffb0032b3136e1beb32789e5c9c0501d4011a9c935bdda3ebae37ceef5bb77",
}


@pytest.mark.parametrize("version", sorted(BEFORE_THE_REFACTOR))
def test_prompts_are_byte_identical_to_before_the_refactor(version):
    built = llm_discovery.build_neutral_prompt(X, Y, EVIDENCE, version)
    assert hashlib.sha256(built.encode()).hexdigest() == BEFORE_THE_REFACTOR[version]
    a, b = llm_discovery.neutral_order(X, Y, version)
    assert llm_discovery.format_neutral_prompt(a, b, EVIDENCE, version) == built


def record(a, b, answer, strength="hard", confidence=0.9, cited=()):
    source, target = (b, a) if answer == "B_BEFORE_A" else (a, b)
    return {
        "source": source,
        "target": target,
        "relationship": "NONE" if answer == "NEITHER" else "DIRECT",
        "strength": "none" if answer == "NEITHER" else strength,
        "confidence": confidence,
        "evidence_chunk_ids": list(cited),
        "answer": answer,
        "on_topic": True,
        "pair_a": a,
        "pair_b": b,
    }


def test_same_direction_is_one_stable_link_from_the_hash_order_ask():
    first = record("x", "y", "A_BEFORE_B", strength="hard", cited=["c1"])
    second = record("y", "x", "B_BEFORE_A", strength="soft", cited=["c2", "c1"])
    agreement, links = llm_discovery.apply_order_rule(first, second)
    assert agreement == "stable"
    assert [(r["source"], r["target"], r["strength"]) for r in links] == [("x", "y", "hard")]
    assert links[0]["evidence_chunk_ids"] == ["c1", "c2"]


@pytest.mark.parametrize("hash_order_links", [True, False])
def test_link_in_one_order_only_is_one_unstable_link(hash_order_links):
    link, neither = record("x", "y", "A_BEFORE_B", strength="soft"), record("y", "x", "NEITHER")
    asks = (link, neither) if hash_order_links else (neither, link)
    agreement, links = llm_discovery.apply_order_rule(*asks)
    assert agreement == "unstable"
    assert [(r["source"], r["target"], r["strength"]) for r in links] == [("x", "y", "soft")]


def test_reversed_direction_proposes_both_and_picks_neither():
    first, second = record("x", "y", "A_BEFORE_B"), record("y", "x", "A_BEFORE_B")
    agreement, links = llm_discovery.apply_order_rule(first, second)
    assert agreement == "reversed"
    assert {(r["source"], r["target"]) for r in links} == {("x", "y"), ("y", "x")}


def test_neither_in_both_is_no_link():
    assert llm_discovery.apply_order_rule(
        record("x", "y", "NEITHER"), record("y", "x", "NEITHER")
    ) == ("neither", [])


def test_the_rule_is_written_in_a_versioned_config():
    rule = llm_discovery.load_order_rule()
    assert rule["version"] == "order_rule_v1"
    assert len(rule["rule"]) == 4


def run_cli(tmp_path, monkeypatch, answer_for, *extra):
    """answer_for(a, b) gives the reply's answer. Returns (the written file, the prompts asked)."""
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())
    asked = []

    def fake(prompt, **kwargs):
        a, b = re.findall(r"^ID: (\S+)$", prompt, re.M)[-2:]
        asked.append((a, b))
        answer = answer_for(a, b)
        strength = "NONE" if answer == "NEITHER" else "HARD"
        return {"a": a, "b": b, "answer": answer, "strength": strength, "confidence": "HIGH"}

    monkeypatch.setattr(llm_discovery, "chat_json", fake)
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(tmp_path), *extra],
        ]
    )
    assert check_file(tmp_path / "relationships.json") == []
    return json.loads((tmp_path / "relationships.json").read_text()), asked


def lower_id_first(a, b):
    return "A_BEFORE_B" if a < b else "B_BEFORE_A"  # the same direction whichever is A


def test_course_runs_ask_both_orders_by_default_and_store_both_answers(tmp_path, monkeypatch):
    out, asked = run_cli(tmp_path, monkeypatch, lower_id_first)
    assert {(b, a) for a, b in asked} == set(asked)  # every pair, swapped
    both = out["discovery"]["both_orders"]
    assert both["rule_version"] == "order_rule_v1"
    assert both["stable"] == both["pairs"] == len(out["relationships"]) == len(asked) // 2
    assert {e["order_agreement"] for e in out["relationships"]} == {"stable"}
    assert all(len(row["asks"]) == 2 for row in out["pair_answers"])


def test_a_reversal_in_the_file_gives_two_edges_marked_reversed(tmp_path, monkeypatch):
    out, _ = run_cli(tmp_path, monkeypatch, lambda a, b: "A_BEFORE_B")
    assert out["discovery"]["both_orders"]["reversed"] == out["discovery"]["both_orders"]["pairs"]
    assert len(out["relationships"]) == 2 * out["discovery"]["both_orders"]["pairs"]
    assert {e["order_agreement"] for e in out["relationships"]} == {"reversed"}


def test_neither_pairs_leave_no_edge_but_keep_their_answers(tmp_path, monkeypatch):
    out, asked = run_cli(tmp_path, monkeypatch, lambda a, b: "NEITHER")
    assert out["relationships"] == []
    assert len(out["pair_answers"]) == len(asked) // 2


def test_one_order_results_can_be_computed_from_a_both_orders_run(tmp_path, monkeypatch):
    def biased(a, b):
        return "B_BEFORE_A" if (a + b).count("e") % 2 else "NEITHER"

    both, _ = run_cli(tmp_path / "both", monkeypatch, biased)
    one, _ = run_cli(tmp_path / "one", monkeypatch, biased, "--one-order")
    from_both = llm_discovery.single_order_relationships(both["pair_answers"])
    assert sorted(
        (r["source"], r["target"]) for r in from_both if r["answer"] != "NEITHER"
    ) == sorted((e["source"], e["target"]) for e in one["relationships"])
    assert both["discovery"]["answers"] == one["discovery"]["answers"]


def test_one_order_writes_none_of_the_new_fields(tmp_path, monkeypatch):
    out, asked = run_cli(tmp_path, monkeypatch, lower_id_first, "--one-order")
    assert "pair_answers" not in out and "both_orders" not in out["discovery"]
    assert not any("order_agreement" in e for e in out["relationships"])
    assert len(asked) == len({frozenset(pair) for pair in asked})


def test_benchmark_runs_never_ask_both_orders(tmp_path, monkeypatch):
    pairs = Path(tmp_path) / "pairs.csv"
    pairs.write_text("source,target\ntrees,binary_tree\n")
    monkeypatch.setattr(
        llm_discovery,
        "chat_json",
        lambda prompt, **k: (
            pytest.fail("mock the directional call only")
            if k["prompt_version"] != "discover_v2"
            else {"relationship": "DIRECT", "strength": "HARD", "confidence": "HIGH"}
        ),
    )
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--pairs", str(pairs)],
            *["--pairs-direction", "given", "--out-dir", str(tmp_path)],
        ]
    )
    out = json.loads((tmp_path / "relationships.json").read_text())
    assert "pair_answers" not in out and "discovery" not in out
    assert not any("order_agreement" in e for e in out["relationships"])
