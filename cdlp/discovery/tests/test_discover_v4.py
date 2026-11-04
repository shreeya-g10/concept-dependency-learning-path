"""discover_v4: one YES/NO call per direction, and the rule that maps answers to links."""

from __future__ import annotations

import json
import re

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.discovery import candidates, llm_discovery
from cdlp.shared.validate import check_file

EX = "cdlp/shared/examples"
X = {"id": "binary_tree", "name": "Binary Tree", "aliases": ["BT"], "description": "Two children."}
Y = {"id": "avl_tree", "name": "AVL Tree", "description": "A height-balanced search tree."}
NAMED = {"needed": "Binary Tree", "topic": "AVL Tree"}


def ask(needed, topic, answer, strength="hard"):
    yes = answer == "YES"
    return {
        "source": needed,
        "target": topic,
        "relationship": "DIRECT" if yes else "NONE",
        "strength": strength if yes else "none",
        "answer": answer,
    }


@pytest.mark.parametrize(
    ("first", "second", "agreement", "links"),
    [
        ("YES", "NO", "one_way", [("x", "y")]),
        ("NO", "YES", "one_way", [("y", "x")]),
        ("YES", "YES", "both_yes", [("x", "y"), ("y", "x")]),
        ("NO", "NO", "none", []),
    ],
)
def test_two_answers_map_to_links(first, second, agreement, links):
    got, proposed = llm_discovery.apply_direction_rule(ask("x", "y", first), ask("y", "x", second))
    assert got == agreement
    assert [(r["source"], r["target"]) for r in proposed] == links


def test_the_prompt_has_no_a_or_b_labels_and_is_a_new_file():
    prompt = llm_discovery.format_direction_prompt(X, Y, [], "discover_v4")
    assert 'need to understand "Binary Tree" in order to understand "AVL Tree"' in prompt
    assert not re.search(r"\b(A_BEFORE_B|B_BEFORE_A|NEITHER)\b", prompt)
    assert not re.search(r"\b[AB]\b(?! [a-z])", prompt)  # "A bechamel" is English, not a label
    assert "{" not in prompt


@pytest.mark.parametrize(
    ("reply", "answer", "valid"),
    [
        ({**NAMED, "answer": "YES", "strength": "HARD"}, "YES", True),
        ({"needed": "bt", "topic": "avl_tree", "answer": "no", "strength": "NONE"}, "NO", True),
        ({**NAMED, "answer": "YES", "strength": "NONE"}, "NO", False),
        ({"needed": "AVL Tree", "topic": "BT", "answer": "YES", "strength": "HARD"}, "NO", False),
        ({**NAMED, "answer": "MAYBE"}, "NO", False),
        ({}, "NO", False),
        ("not a dict", "NO", False),
    ],
)
def test_only_a_clean_yes_makes_a_link_and_the_raw_answer_is_kept(reply, answer, valid):
    record = llm_discovery._normalise_direction_result(reply, X, Y, set())
    assert (record["answer"], record["valid"]) == (answer, valid)
    assert (record["relationship"] == "DIRECT") == (answer == "YES")
    assert record["raw_answer"] == (reply.get("answer", "") if isinstance(reply, dict) else "")


def run_cli(tmp_path, monkeypatch, answer_for, *extra):
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())
    asked = []

    def fake(prompt, **kwargs):
        assert kwargs["prompt_version"] == "discover_v4"
        needed, topic = re.findall(
            r'understand "([^"]+)" in order to understand "([^"]+)"', prompt
        )[-1]
        asked.append((needed, topic))
        answer = answer_for(needed, topic)
        return {
            "needed": needed,
            "topic": topic,
            "answer": answer,
            "strength": "HARD" if answer == "YES" else "NONE",
            "evidence_chunk_ids": [],
        }

    monkeypatch.setattr(llm_discovery, "chat_json", fake)
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(tmp_path), "--prompt-version", "discover_v4", *extra],
        ]
    )
    assert check_file(tmp_path / "relationships.json") == []
    return json.loads((tmp_path / "relationships.json").read_text()), asked


def test_two_calls_per_pair_and_both_raw_answers_per_direction(tmp_path, monkeypatch):
    out, asked = run_cli(
        tmp_path, monkeypatch, lambda needed, topic: "YES" if needed < topic else "NO"
    )
    assert {(b, a) for a, b in asked} == set(asked)
    directions = out["discovery"]["directions"]
    assert directions["rule_version"] == "direction_rule_v1"
    assert directions["pairs"] == directions["one_way"] == len(asked) // 2
    assert (
        out["discovery"]["answers"]["YES"] == out["discovery"]["answers"]["NO"] == len(asked) // 2
    )
    assert "pair_answers" not in out and "both_orders" not in out["discovery"]
    for row in out["direction_answers"]:
        first, second = row["asks"]
        assert (first["needed"], first["topic"]) == (second["topic"], second["needed"])
        assert {first["raw_answer"], second["raw_answer"]} == {"YES", "NO"}
    assert {e["direction_agreement"] for e in out["relationships"]} == {"one_way"}
    assert all(e["method"] == "llm_discover_v4" for e in out["relationships"])
    assert not any("pair_order" in e for e in out["relationships"])


def test_yes_both_ways_proposes_both_links_and_the_validator_sends_them_to_review(
    tmp_path, monkeypatch
):
    from cdlp.validation.graph_checks import graph_labels

    out, _ = run_cli(tmp_path, monkeypatch, lambda needed, topic: "YES")
    links = out["relationships"]
    assert {e["direction_agreement"] for e in links} == {"both_yes"}
    assert len(links) == 2 * out["discovery"]["directions"]["both_yes"]
    assert set(graph_labels(links)) == {"contradiction"}


def test_no_both_ways_keeps_both_answers_but_no_link(tmp_path, monkeypatch):
    out, asked = run_cli(tmp_path, monkeypatch, lambda needed, topic: "NO")
    assert out["relationships"] == []
    assert len(out["direction_answers"]) == len(asked) // 2


@pytest.mark.parametrize("flags", [["--one-order"], ["--pairs", "pairs.csv"]])
def test_benchmarks_and_one_order_refuse_the_prompt(tmp_path, flags):
    with pytest.raises(SystemExit):
        cli.main(
            [
                *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
                *["--out-dir", str(tmp_path), "--prompt-version", "discover_v4", *flags],
            ]
        )
    assert not (tmp_path / "relationships.json").exists()


def test_the_default_prompts_do_not_change():
    assert llm_discovery.PROMPT_VERSION not in llm_discovery.DIRECTION_PROMPT_VERSIONS
    assert llm_discovery.DIRECTIONAL_PROMPT_VERSION not in llm_discovery.DIRECTION_PROMPT_VERSIONS
