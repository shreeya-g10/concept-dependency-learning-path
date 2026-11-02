"""The written demo-subset rule: which edges it keeps, and that it never invents one."""

import json
from pathlib import Path

from cdlp.validation import __main__ as cli
from cdlp.validation import demo_rule

CONFIG = Path("cdlp/validation/configs/demo_subset_ds101.json")
RULE = demo_rule.load_rule(CONFIG)


def proposed(*pairs, confidence=0.9):
    return {
        "schema_version": "1.2",
        "course_id": "ds101",
        "relationships": [
            {
                "id": f"r{i}",
                "source": a,
                "target": b,
                "type": "PREREQUISITE",
                "strength": "hard",
                "confidence": confidence,
                "evidence": [],
            }
            for i, (a, b) in enumerate(pairs, start=1)
        ],
    }


CHAIN = [
    ("general_tree", "binary_tree"),
    ("binary_tree", "binary_search_tree"),
    ("binary_search_tree", "avl_tree"),
]
BACKWARDS = ("binary_tree", "general_tree")
SHORTCUT = ("binary_tree", "avl_tree")
UNLIKELY = ("stack", "heap")
FAMILY = ("binary_search_tree", "red_black_tree")
OTHER = ("graph", "adjacency_list")


def tiers(record):
    return {(e["source"], e["target"]): e["tier"] for e in record["selected"]}


def test_every_edge_gets_the_tier_the_rule_says():
    rels = proposed(OTHER, FAMILY, UNLIKELY, SHORTCUT, BACKWARDS, *CHAIN)
    _, _, record = demo_rule.select(rels, 28, RULE)
    got = tiers(record)
    assert all(got[link] == "chain" for link in CHAIN)
    assert got[BACKWARDS] == got[SHORTCUT] == got[UNLIKELY] == "likely_wrong"
    assert got[FAMILY] == "tree_family"
    assert got[OTHER] == "other"
    assert record["missing_chain_links"] == []


def test_never_adds_an_edge_the_llm_did_not_propose():
    rels = proposed(*CHAIN[:1], FAMILY)  # two chain links are missing
    kept, subset, record = demo_rule.select(rels, 28, RULE)
    assert {(r["source"], r["target"]) for r in kept["relationships"]} == {CHAIN[0], FAMILY}
    assert subset["n"] == 2 and subset["of"] == 2
    assert record["missing_chain_links"] == [
        {"source": "binary_tree", "target": "binary_search_tree"},
        {"source": "binary_search_tree", "target": "avl_tree"},
    ]


def test_slots_for_rejections_survive_many_tree_edges():
    tree = RULE["families"]["tree"][5:]
    many = [(a, b) for a in tree for b in tree if a != b]
    wrong = [("stack", c) for c in tree] + [("queue", c) for c in tree]
    _, subset, record = demo_rule.select(proposed(*many, *wrong), 28, RULE)
    counts = [e["tier"] for e in record["selected"]]
    assert subset["n"] == 28
    assert counts.count("likely_wrong") == RULE["likely_wrong_slots"]
    assert counts.count("tree_family") == 28 - RULE["likely_wrong_slots"]


def test_unused_rejection_slots_go_to_the_next_tier():
    tree = RULE["families"]["tree"][5:]
    many = [(a, b) for a in tree for b in tree if a != b]
    _, subset, record = demo_rule.select(proposed(*many, UNLIKELY), 28, RULE)
    counts = [e["tier"] for e in record["selected"]]
    assert subset["n"] == 28 and counts.count("likely_wrong") == 1


def test_likely_wrong_order_and_determinism():
    rels = proposed(UNLIKELY, SHORTCUT, BACKWARDS)
    one_slot = {**RULE, "likely_wrong_slots": 1}
    _, _, record = demo_rule.select(rels, 1, one_slot)
    assert list(tiers(record)) == [BACKWARDS]
    assert demo_rule.select(rels, 28, RULE)[2] == demo_rule.select(rels, 28, RULE)[2]


def test_kept_edges_keep_their_original_records_and_order():
    rels = proposed(OTHER, *CHAIN)
    kept, _, _ = demo_rule.select(rels, 3, RULE)
    assert kept["relationships"] == rels["relationships"][1:]


def test_config_covers_each_concept_once():
    members = [c for family in RULE["families"].values() for c in family]
    assert len(members) == len(set(members))
    assert set(RULE["chain"]) <= set(RULE["families"]["tree"])
    assert "not a performance measure" in RULE["selection"]


def test_cli_writes_rule_and_edges_and_labels_the_graph(tmp_path, monkeypatch, capsys):
    rels = proposed(*CHAIN[:2], UNLIKELY, FAMILY)
    path = tmp_path / "relationships.json"
    path.write_text(json.dumps(rels))
    seen = {}

    def fake_validate(relationships, concepts, chunks, **kwargs):
        seen["ids"] = [r["id"] for r in relationships["relationships"]]
        return {"course_id": "ds101", "edges": []}

    monkeypatch.setattr(cli, "validate", fake_validate)
    monkeypatch.setattr(cli, "write_graph", lambda out, graph: seen.update(graph=graph))
    monkeypatch.setattr(cli, "read_jsonl", lambda p: [])
    monkeypatch.setattr(cli, "read_json", lambda p: rels if Path(p) == path else {"concepts": []})
    out = tmp_path / "validated_graph.json"
    cli.main(
        [
            *["--relationships", str(path), "--concepts", "c.json", "--chunks", "c.jsonl"],
            *["--out", str(out), "--demo-subset", "3", "--demo-rule", str(CONFIG)],
            *["--stats", str(tmp_path / "s.json")],
        ]
    )
    record = json.loads((tmp_path / "validated_graph.demo_subset.json").read_text())
    assert record["rule_id"] == "demo_subset_ds101_v1"
    assert record["rule"]["chain"] == RULE["chain"]
    assert [e["id"] for e in record["selected"]] == seen["ids"]
    assert seen["graph"]["subset"]["selection"] == RULE["selection"]
    assert "WARNING: chain link binary_search_tree -> avl_tree" in capsys.readouterr().err
