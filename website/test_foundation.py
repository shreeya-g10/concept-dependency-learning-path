"""The student-site rules: menu, plain words, honesty notices, course picker. No LLM."""

import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402
import strings as S  # noqa: E402
import ui  # noqa: E402

STUDENT = [SITE / ui.PAGES[k].path for k in ui.STUDENT_PAGES]
# Team names, research terms, tools and raw ids a student must never see.
BANNED = re.compile(
    r"\b(vaidehi|shreeya|sneha|shrestha|prerequisites?|llm|dag|edges?|pipeline|rq\d|ollama"
    r"|ds101|ml101|outputs/|data/raw|chunk\w*|validat\w+|diagnos\w+|baseline|concepts?)\b",
    re.IGNORECASE,
)


def course_content() -> set[str]:
    """Words from the course itself, which may use any term (a tree does have edges)."""
    concepts = json.loads((common.EXAMPLES / "concepts.json").read_text())["concepts"]
    chunks = (common.EXAMPLES / "chunks.jsonl").read_text().splitlines()
    return {c.get("description", "") for c in concepts} | {json.loads(c)["text"] for c in chunks}


def visible_text(at: AppTest) -> str:
    """Everything a student can read on the page (widget labels and option names included)."""
    parts = []
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning"):
        parts += [e.value for e in getattr(at, kind)]
    parts += [e.value for e in at.error] + [e.value for e in at.success]
    parts += [b.label for b in at.button] + [w.label for w in at.text_input]
    for box in at.selectbox:
        parts += [box.label, *box.options]
    for radio in at.radio:
        parts += [radio.label]
    return "\n".join(str(p) for p in parts if p not in course_content())


@pytest.fixture(autouse=True)
def _fresh_cache():
    import streamlit as st

    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def demo_outputs(tmp_path, monkeypatch):
    course = tmp_path / "ds101"
    course.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "relationships.json", "quiz_items.json"):
        shutil.copy(common.EXAMPLES / name, course / name)
    shutil.copy(
        common.EXAMPLES / "demo_subset_validated_graph.json", course / "validated_graph.json"
    )
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    return tmp_path


# --- menu ------------------------------------------------------------------------------


def test_every_menu_entry_has_a_file_and_every_file_a_menu_entry():
    listed = {(SITE / p.path).name for p in ui.PAGES.values()}
    assert listed == {p.name for p in (SITE / "pages").glob("*.py")}


def test_menu_names_and_order():
    assert [ui.PAGES[k].title for k in ui.STUDENT_PAGES] == [
        "Home",
        "1 Add your notes",
        "2 See your topics",
        "3 Quick check",
        "4 My study plan",
        "Topic map",
    ]
    assert S.NAV_GROUP_TEACHERS == "For teachers"
    assert S.NAV_AI_CHECKS == "AI checks and review"


def test_entry_point_opens_home_and_buttons_change_page():
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    assert not at.exception
    assert not at.error  # the entry point turns a page crash into a friendly error
    assert at.title[0].value == S.HOME_TITLE
    at.button(key="home_quiz").click().run()
    assert not at.exception and not at.error
    assert at.title[0].value == S.QUIZ_TITLE


def test_an_answer_in_the_quick_check_reaches_the_study_plan(demo_outputs):
    quiz = json.loads((common.EXAMPLES / "quiz_items.json").read_text())["items"]
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    at.button(key="home_quiz").click().run()
    at.selectbox[0].set_value("avl_tree").run()
    at.button(key="quiz_start").click().run()
    shown = next(m.value for m in at.markdown if m.value.startswith("### "))
    item = next(q for q in quiz if q["question"] == shown[4:])
    at.button(key=f"answer_{item['id']}_{item['options'].index(item['answer'])}").click().run()
    assert not at.exception and not at.error
    next(b for b in at.button if b.label == S.QUIZ_TO_PLAN).click().run()
    assert not at.exception and not at.error
    assert at.title[0].value == S.PLAN_TITLE
    assert not any(S.PLAN_EMPTY in i.value for i in at.info)
    assert any(S.PLAN_FOR.split("{")[0] in m.value for m in at.markdown)


def test_a_page_crash_shows_a_friendly_error(monkeypatch):
    monkeypatch.setattr(common, "course_options", lambda: 1 / 0)
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    assert not at.exception
    assert S.ERROR_PAGE in at.error[0].value and S.WHAT_TO_DO in at.error[0].value


# --- student pages ---------------------------------------------------------------------


@pytest.mark.parametrize("page", STUDENT, ids=lambda p: p.name)
def test_student_pages_use_plain_words(page, demo_outputs):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception
    found = BANNED.findall(visible_text(at))
    assert not found, found


def test_strings_use_plain_words():
    values = [v for k, v in vars(S).items() if k.isupper()]
    text = "\n".join(str(list(v.values()) if isinstance(v, dict) else v) for v in values)
    found = BANNED.findall(text)
    assert not found, found


@pytest.mark.parametrize(
    "page", [p for p in STUDENT if p.name != "1_Add_your_notes.py"], ids=lambda p: p.name
)
def test_demo_notice_stays_on_every_page_with_results(page, demo_outputs):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert any("This is a demo" in w.value and "3 of the 6" in w.value for w in at.warning)


@pytest.mark.parametrize(
    "page",
    [SITE / ui.PAGES[k].path for k in ui.TEACHER_PAGES],
    ids=lambda p: p.name,
)
def test_teachers_also_see_the_written_rule(page, demo_outputs):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    rule = common.demo_subset_rule("ds101")
    assert rule and any(rule in c.value for c in at.caption)


def test_sample_notice_on_example_data(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)  # no outputs: the page shows examples
    at = AppTest.from_file(str(SITE / ui.PAGES["topics"].path), default_timeout=60).run()
    assert any(S.SAMPLE_NOTICE in i.value for i in at.info)


def test_study_plan_asks_for_the_quick_check_first(demo_outputs):
    at = AppTest.from_file(str(SITE / ui.PAGES["plan"].path), default_timeout=60).run()
    assert not at.exception
    assert any(S.PLAN_EMPTY in i.value for i in at.info)
    assert [b.label for b in at.button] == [S.PLAN_TO_QUIZ]


def test_study_plan_after_an_answer_has_no_raw_ids(demo_outputs):
    at = AppTest.from_file(str(SITE / ui.PAGES["plan"].path), default_timeout=60)
    at.session_state["quiz_answers"] = [{"concept_id": "trees", "correct": False}]
    at.session_state["quiz_mastery"] = {"trees": 0.1}
    at.session_state["quiz_course"] = "ds101"
    at.session_state["study_target"] = "avl_tree"
    at.run()
    assert not at.exception
    text = visible_text(at) + " ".join(e.label for e in at.expander)
    assert "avl_tree" not in text and "binary_tree" not in text
    assert "Topic 1:" in text


def test_study_plan_ignores_answers_from_another_course(demo_outputs):
    at = AppTest.from_file(str(SITE / ui.PAGES["plan"].path), default_timeout=60)
    at.session_state["quiz_answers"] = [{"concept_id": "trees", "correct": False}]
    at.session_state["quiz_mastery"] = {"trees": 0.1}
    at.session_state["quiz_course"] = "other"
    at.session_state["study_target"] = "avl_tree"
    at.run()
    assert any(S.PLAN_EMPTY in i.value for i in at.info)


def test_topic_map_sends_the_heavy_picture_only_on_request(demo_outputs):
    at = AppTest.from_file(str(SITE / ui.PAGES["map"].path), default_timeout=60).run()
    assert not at.exception
    assert not at.get("iframe")
    at.button(key="map_full_button").click().run()
    assert not at.exception


# --- course picker ---------------------------------------------------------------------


def test_picker_hides_raw_ids_and_folders_that_are_not_courses(demo_outputs):
    (demo_outputs / "scratch").mkdir()
    (demo_outputs / ".jobs").mkdir()
    bio = demo_outputs / "biology_notes"
    bio.mkdir()
    for name in common.COURSE_FILES:
        shutil.copy(common.EXAMPLES / name, bio / name)
    at = AppTest.from_file(str(SITE / ui.PAGES["home"].path), default_timeout=60).run()
    assert not at.exception
    assert at.selectbox[0].options == ["Biology notes", "Data Structures & Algorithms"]


def test_picking_a_subject_changes_the_data_shown(demo_outputs):
    """load() must not serve the first course's cached files to the next course."""
    bio = demo_outputs / "biology_notes"
    bio.mkdir()
    shutil.copy(common.EXAMPLES / "validated_graph.json", bio / "validated_graph.json")
    concepts = json.loads((common.EXAMPLES / "concepts.json").read_text())
    concepts["concepts"][0]["name"] = "Cell walls"
    (bio / "concepts.json").write_text(json.dumps(concepts))

    def session(course):
        at = AppTest.from_file(str(SITE / ui.PAGES["topics"].path), default_timeout=60)
        at.session_state["course_id"] = course
        return " ".join(m.value for m in at.run().markdown)

    assert "Cell walls" not in session("ds101")
    assert "Cell walls" in session("biology_notes")


# --- theme -----------------------------------------------------------------------------


def contrast(a: str, b: str) -> float:
    def lum(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted((lum(a), lum(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_theme_has_strong_contrast():
    tomllib = pytest.importorskip("tomllib")
    config = tomllib.loads((SITE.parent / ".streamlit" / "config.toml").read_text())
    theme = config["theme"]
    assert contrast(theme["textColor"], theme["backgroundColor"]) >= 7
    assert contrast(theme["textColor"], theme["secondaryBackgroundColor"]) >= 7
    assert contrast(theme["primaryColor"], "#FFFFFF") >= 7  # white words on the main button
