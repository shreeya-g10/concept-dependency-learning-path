"""Teacher review: Accept / Reject buttons, ordering, and the applied graph.

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

PAGE = SITE / "pages" / "teacher_AI_checks_and_review.py"
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
    message = next(e.value for e in at.error if "blocking link" in e.value)
    assert "in a circle" in message and "Reject it" in message  # why, and what to do next


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
    assert any("Your Accept was refused" in w.value for w in at.warning)


def test_example_data_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)  # no outputs: the page shows examples
    at = open_page()
    assert not at.exception
    assert all(b.disabled for b in at.button if b.key and b.key.startswith(("accept_", "reject_")))
    assert any("example data" in i.value for i in at.info)
    assert list(tmp_path.iterdir()) == []


# --- plain labels first, technical terms in smaller text ---------------------------------


def test_plain_decision_labels_with_the_technical_terms_in_small_text(outputs):
    at = open_page()
    assert [m.label for m in at.metric][:3] == ["Accepted", "Rejected", "Needs your review"]
    assert "Needs your review" in [s.value for s in at.subheader]
    assert any("HUMAN_REVIEW" in c.value for c in at.caption)
    # never a raw decision name or check name as a label
    assert not any(m.label in ("ACCEPT", "REJECT", "HUMAN_REVIEW") for m in at.metric)
    assert any("evidence check" in c.value and "confidence" in c.value for c in at.caption)


def test_links_that_need_the_teacher_come_before_the_full_list(outputs):
    at = open_page()
    headings = [s.value for s in at.subheader]
    assert headings.index("Decisions") < headings.index("Needs your review")
    assert headings.index("Needs your review") < headings.index("All links")


def test_the_list_shows_one_decision_at_a_time(outputs):
    at = open_page()
    assert at.radio[0].format_func("REJECT").startswith("Rejected (")
    at.radio[0].set_value("HUMAN_REVIEW").run()
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any("AVL" in text and "Trees" in text for text in labels)  # the added r7


def test_the_last_build_details_are_on_the_teacher_page(outputs, tmp_path, monkeypatch):
    import jobs

    folder = tmp_path / "jobs" / "ds101"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"state": "failed", "returncode": 1}))
    (folder / "pipeline.log").write_text("==> cdlp.extraction\nValueError: bad pdf\n")
    monkeypatch.setattr(jobs, "JOBS", tmp_path / "jobs")
    at = open_page()
    assert not at.exception
    assert "Last time the notes were read" in [s.value for s in at.subheader]
    assert any("ValueError: bad pdf" in c.value for c in at.code)


def test_ai_suggestions_page_uses_plain_labels():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(SITE / "pages" / "teacher_AI_suggestions.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert at.multiselect[0].format_func("hard") == "Must learn first"
    assert any("candidate prerequisite edge" in c.value for c in at.caption)


# --- validator reasons on the review cards ---------------------------------------------


def with_reason(course, edge_id, reason, **checks):
    path = course / "validated_graph.json"
    graph = json.loads(path.read_text())
    edge = next(e for e in graph["edges"] if e["id"] == edge_id)
    edge["reason"] = reason
    edge["checks"].update(checks)
    path.write_text(json.dumps(graph))


def test_a_review_card_shows_the_reason_in_plain_words_with_the_raw_text_small(outputs):
    raw = (
        "evidence strong, semantic none (score 0.50). Semantic: A binary tree is more general. "
        "(skipped: necessity)"
    )
    with_reason(outputs, "r5", raw, evidence="strong", semantic="none", graph="ok")
    at = open_page()
    assert not at.exception
    said = " ".join(m.value for m in at.markdown)
    assert "The notes clearly support this link." in said
    assert "The AI says this teaching order does not make sense." in said
    assert "The AI's words: A binary tree is more general." in said
    assert "evidence strong, semantic none" not in said and "(skipped" not in said
    small = " ".join(c.value for c in at.caption)
    assert "evidence strong, semantic none (score 0.50). (skipped: necessity)" in small
    assert "A binary tree is more general" not in small  # said once, in the plain text


def test_a_circle_is_explained_in_plain_words(outputs):
    raw = "evidence weak, semantic strong (score 0.67; lies on a cycle, so never accepted)."
    with_reason(outputs, "r5", raw, evidence="weak", semantic="strong", graph="cycle")
    at = open_page()
    said = " ".join(m.value for m in at.markdown)
    assert "part of a circle of links" in said
    assert "lies on a cycle" not in said


def test_a_reason_that_is_already_plain_is_left_alone(outputs):
    at = open_page()
    assert "validator unsure" in " ".join(m.value for m in at.markdown)
    assert not any(
        "Technical details" in c.value and "validator unsure" in c.value for c in at.caption
    )
