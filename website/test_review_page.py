"""Page 3 teacher review: Accept / Reject buttons, ordering, and the applied graph.

Runs on a copy of the example files in a temporary outputs/ folder. Each click runs the
real `python -m cdlp.validation.apply_review` CLI (no LLM).
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402

PAGE = SITE / "pages" / "3_Validation_Agent.py"
EXAMPLES = common.EXAMPLES


def human_review_edge(eid, source, target):
    return {
        "id": eid,
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "decision": "HUMAN_REVIEW",
        "confidence": 0.4,
        "checks": {"evidence": "weak", "semantic": "weak", "necessity": "weak", "graph": "ok"},
        "evidence": [],
        "reason": "validator unsure",
    }


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    course = tmp_path / "ds101"
    course.mkdir()
    for name in ["validated_graph.json", "concepts.json", "chunks.jsonl", "sim_students.json"]:
        shutil.copy(EXAMPLES / name, course / name)
    graph = json.loads((course / "validated_graph.json").read_text())
    # avl_tree -> trees closes a cycle with the ACCEPT path trees -> ... -> avl_tree
    graph["edges"].append(human_review_edge("r7", "avl_tree", "trees"))
    (course / "validated_graph.json").write_text(json.dumps(graph))
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    return course


def open_page():
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    st.cache_data.clear()  # load() caches by file name: drop other tests' graphs
    return AppTest.from_file(str(PAGE), default_timeout=120).run()


def edges_of(course):
    graph = json.loads((course / "validated_graph.json").read_text())
    return {e["id"]: e for e in graph["edges"]}


def test_blocking_edges_come_first_and_cannot_be_accepted(outputs):
    at = open_page()
    assert not at.exception
    accept = [b for b in at.button if b.key and b.key.startswith("accept_")]
    assert [b.key for b in accept] == ["accept_r7", "accept_r5"]  # blocking r7 first
    assert accept[0].disabled and not accept[1].disabled
    assert any("blocking edge" in e.value for e in at.error)


def test_accept_saves_the_decision_and_updates_the_graph(outputs):
    at = open_page()
    at.text_input(key="comment_r5").input("taught after trees")
    at.button(key="accept_r5").click().run()
    assert not at.exception
    decisions = json.loads((outputs / "review_decisions.json").read_text())["decisions"]
    assert [(d["edge_id"], d["decision"], d["comment"]) for d in decisions] == [
        ("r5", "ACCEPT", "taught after trees")
    ]
    r5 = edges_of(outputs)["r5"]
    assert r5["decision"] == "ACCEPT" and r5["review"]["decided_by"] == "teacher"
    # the page re-ran: r5 no longer waits, and the queue was rebuilt without it
    assert "accept_r5" not in [b.key for b in at.button]
    queue = json.loads((outputs / "review_queue.json").read_text())["queue"]
    assert [q["edge_id"] for q in queue] == ["r7"]


def test_reject_and_change_of_mind(outputs):
    at = open_page()
    at.button(key="reject_r7").click().run()
    assert edges_of(outputs)["r7"]["decision"] == "REJECT"
    at.button(key="change_r7").click().run()  # "Change to ACCEPT": refused, closes a cycle
    assert not at.exception
    r7 = edges_of(outputs)["r7"]
    assert r7["decision"] == "HUMAN_REVIEW" and r7["review"]["status"] == "refused_cycle"


def test_example_data_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)  # no outputs: the page shows examples
    at = open_page()
    assert not at.exception
    assert all(b.disabled for b in at.button if b.key and b.key.startswith(("accept_", "reject_")))
    assert any("example data" in i.value for i in at.info)
    assert list(tmp_path.iterdir()) == []
