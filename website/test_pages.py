"""Every website page must render without an exception (on example data)."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
PAGES = sorted((SITE / "pages").glob("*.py"))
# `streamlit run website/Home.py` puts website/ on sys.path (for common.py, jobs.py);
# a single page run by AppTest does not, so add it here.
AI_CHECKS = SITE / "pages" / "teacher_AI_checks_and_review.py"
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_renders(page):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception


def test_demo_subset_banner_on_every_page(tmp_path, monkeypatch):
    import json

    import common

    course = tmp_path / "demo101"
    course.mkdir()
    examples = Path(common.EXAMPLES)
    for name in ("concepts.json", "chunks.jsonl", "relationships.json", "quiz_items.json"):
        (course / name).write_text((examples / name).read_text())
    (course / "validated_graph.json").write_text(
        (examples / "demo_subset_validated_graph.json").read_text()
    )
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    common.st.cache_data.clear()

    assert "only 3 of the 6 links" in common.demo_subset_note("demo101")
    assert common.demo_subset_rule("demo101")
    graph = json.loads((course / "validated_graph.json").read_text())
    assert graph["subset"]["kind"] == "demo"


def test_banner_renders_in_the_page_header(tmp_path, monkeypatch):
    import common

    course = tmp_path / "demo101"
    course.mkdir()
    (course / "validated_graph.json").write_text(
        (Path(common.EXAMPLES) / "demo_subset_validated_graph.json").read_text()
    )
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    monkeypatch.setattr(common, "get_active_course", lambda: "demo101")
    common.st.cache_data.clear()
    shown = []
    monkeypatch.setattr(common.st, "warning", lambda text, **k: shown.append(text))
    monkeypatch.setattr(common.st, "title", lambda *a, **k: None)
    monkeypatch.setattr(common.st, "caption", lambda *a, **k: None)
    import ui

    ui.page_header("Topic map", source_file="validated_graph.json")

    assert shown and shown[0].startswith("**This is a demo.**")


def _live_course(tmp_path, graph):
    import json

    import common

    course = tmp_path / "ds101"
    course.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "relationships.json", "quiz_items.json"):
        (course / name).write_text((Path(common.EXAMPLES) / name).read_text())
    (course / "validated_graph.json").write_text(json.dumps(graph))
    return common


def test_page3_hides_example_necessity_runs_on_a_live_graph_without_necessity(
    tmp_path, monkeypatch
):
    import json

    import common
    import streamlit as st

    st.cache_data.clear()  # load() is cached: an earlier test cached the example graph
    graph = json.loads((Path(common.EXAMPLES) / "validated_graph.json").read_text())
    for e in graph["edges"]:
        e["checks"]["necessity"] = "skipped"  # the demo run skipped necessity
        e["necessity_gap"] = None
    _live_course(tmp_path, graph)
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)

    at = AppTest.from_file(str(AI_CHECKS), default_timeout=60).run()

    assert not at.exception
    assert not any("Trial check" in s.value for s in at.subheader)


def test_page3_still_shows_necessity_runs_on_the_examples():
    at = AppTest.from_file(str(AI_CHECKS), default_timeout=60).run()
    assert not at.exception


@pytest.fixture(autouse=True)
def _fresh_cache():
    """load() is st.cache_data: never let one test's files leak into the next."""
    import streamlit as st

    st.cache_data.clear()
    yield
    st.cache_data.clear()
