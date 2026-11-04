"""The quick check, study plan and topic map screens, the answer log and the fallback label.

Nothing here calls an LLM: the root-cause tracer is faked or the LLM is unreachable, and
outputs/ points to tmp_path.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
QUIZ = SITE / "pages" / "3_Quick_check.py"
PLAN = SITE / "pages" / "4_My_study_plan.py"
TOPIC_MAP = SITE / "pages" / "5_Topic_map.py"
sys.path.insert(0, str(SITE))

import common  # noqa: E402
import strings as S  # noqa: E402

from cdlp.root_cause import api as root_cause_api  # noqa: E402
from cdlp.shared import llm  # noqa: E402
from cdlp.shared.validate import check_file  # noqa: E402


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    return tmp_path


def with_examples(outputs: Path) -> Path:
    """A course folder holding copies of the example files, for a test to change."""
    course = outputs / "ds101"
    course.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "validated_graph.json", "quiz_items.json"):
        shutil.copy(common.EXAMPLES / name, course / name)
    return course


@pytest.fixture(autouse=True)
def _fresh_cache():
    """load() is st.cache_data: never let one test's files leak into the next."""
    common.st.cache_data.clear()
    yield
    common.st.cache_data.clear()


def test_log_answer_appends_valid_rows(outputs):
    row = {"student_id": "anon_x", "item_id": "q1", "concept_id": "trees", "answer": "n"}
    common.log_answer("ml101", {**row, "correct": False})
    path = common.log_answer("ml101", {**row, "item_id": "q2", "correct": True})
    assert path == outputs / "ml101" / "student_answers.json"
    assert check_file(path) == []
    doc = json.loads(path.read_text())
    assert doc["course_id"] == "ml101"
    assert [a["item_id"] for a in doc["answers"]] == ["q1", "q2"]
    with pytest.raises(ValueError):
        common.log_answer("ml101", {"student_id": "anon_x"})  # breaks the contract
    assert len(json.loads(path.read_text())["answers"]) == 2  # nothing written


def start_quick_check(topic: str = "avl_tree") -> AppTest:
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    return at.button(key=f"topic_{topic}").click().run()


def current_item(at: AppTest) -> dict:
    quiz = json.loads((common.EXAMPLES / "quiz_items.json").read_text())["items"]
    question = next(m.value for m in at.markdown if m.value.startswith("### "))
    return next(q for q in quiz if q["question"] == question[4:])


def tap_answer(at: AppTest, *, correct: bool) -> AppTest:
    """Tap the big button of a right or a wrong option of the current question."""
    item = current_item(at)
    index = next(i for i, o in enumerate(item["options"]) if (o == item["answer"]) == correct)
    return at.button(key=f"answer_{item['id']}_{index}").click().run()


def answer_wrong(at: AppTest) -> AppTest:
    return tap_answer(at, correct=False)


def test_quick_check_logs_answer_and_labels_offline_root_cause(outputs, monkeypatch):
    calls = []

    def fake_trace(graph, quiz_item, answer, mastery, *, allow_fallback=False):
        calls.append(allow_fallback)
        return {"explanation": "[fallback: offline estimate] Gap is likely in trees."}

    monkeypatch.setattr(root_cause_api, "trace", fake_trace)
    at = answer_wrong(start_quick_check())
    assert not at.exception

    assert calls == [True]  # the page asks for the fallback
    path = outputs / "ds101" / "student_answers.json"
    assert check_file(path) == []
    rows = json.loads(path.read_text())["answers"]
    assert len(rows) == 1 and rows[0]["correct"] is False
    assert rows[0]["student_id"].startswith("anon_")  # random id, nothing identifying

    shown = " ".join(c.value for c in at.caption)
    assert "the AI helper was off" in shown and "not from the AI helper" in shown
    assert "[fallback:" not in shown
    assert "Gap is likely in Trees." in shown  # the topic's name, not its raw id


def test_quick_check_labels_an_unusable_ai_reply(outputs, monkeypatch):
    def fake_trace(graph, quiz_item, answer, mastery, *, allow_fallback=False):
        return {"explanation": "[fallback: nearest prerequisite] Gap is likely in trees."}

    monkeypatch.setattr(root_cause_api, "trace", fake_trace)
    at = answer_wrong(start_quick_check())
    assert not at.exception

    shown = " ".join(c.value for c in at.caption)
    assert "answer could not be used" in shown and "not from the AI helper" in shown
    assert "[fallback:" not in shown


def test_the_real_offline_fallback_reads_in_plain_words(outputs, monkeypatch, tmp_path):
    """Not faked: the LLM is unreachable (as in CI), and its text has raw ids and research words.

    The cache and the address are read when llm.py is imported, so setting the environment here
    is not enough. Its own empty cache: a saved reply on this machine would hide the fallback.
    """
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "empty_llm_cache"))
    monkeypatch.setattr(llm, "BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "empty_llm_cache")
    at = answer_wrong(start_quick_check())
    assert not at.exception
    shown = " ".join(c.value for c in at.caption)
    assert "the AI helper was off" in shown and "It may help to go back to" in shown
    assert not re.search(r"baseline|prerequisite|binary_|avl_tree|\[fallback", shown, re.I)


def test_the_stored_root_cause_keeps_the_raw_fallback_marker(outputs, monkeypatch):
    def fake_trace(graph, quiz_item, answer, mastery, *, allow_fallback=False):
        return {"explanation": "[fallback: offline estimate] x", "traced_concept": "trees"}

    monkeypatch.setattr(root_cause_api, "trace", fake_trace)
    at = answer_wrong(start_quick_check())
    assert at.session_state["quiz_answers"][0]["root_cause"].startswith("[fallback:")
    assert "It may help to go back to Trees." in " ".join(c.value for c in at.caption)


def test_a_student_is_not_sent_back_to_a_topic_they_just_got_right(outputs, monkeypatch):
    monkeypatch.setattr(
        root_cause_api,
        "trace",
        lambda *a, **k: {
            "explanation": "[fallback: offline estimate] x",
            "traced_concept": "trees",
        },
    )
    at = AppTest.from_file(str(QUIZ), default_timeout=60)
    at.session_state["quiz_course"] = "ds101"
    at.session_state["quiz_mastery"] = {"trees": 0.9, "__observed__": {"trees": True}}
    at.session_state["quiz_asked"] = []
    at.session_state["quiz_answers"] = [{"concept_id": "trees", "correct": True}]
    at.session_state["quiz_picking"] = True
    at.session_state["quiz_progress"] = 0.0
    at.session_state["quiz_feedback"] = None
    at.session_state["quiz_just_right"] = False
    at.session_state["quiz_not_saved"] = False
    at.run()
    at = at.button(key="topic_binary_tree").click().run()
    assert not at.exception
    at = tap_answer(at, correct=False)
    shown = " ".join(c.value for c in at.caption)
    assert "It may help to go back to" in shown and "go back to Trees" not in shown


# --- quick check screens ------------------------------------------------------------


@pytest.fixture
def no_ai(monkeypatch):
    monkeypatch.setattr(
        root_cause_api,
        "trace",
        lambda *a, **k: {
            "explanation": "[fallback: offline estimate] x",
            "traced_concept": "trees",
        },
    )


def screen_text(at: AppTest) -> str:
    parts = [
        e.value
        for kind in ("markdown", "caption", "info", "success", "warning")
        for e in getattr(at, kind)
    ]
    return " ".join(parts + [b.label for b in at.button])


def test_quick_check_lists_only_ready_topics_with_the_real_count(outputs):
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    assert not at.exception
    assert at.text_input[0].placeholder == S.QUIZ_SEARCH_HINT
    assert not any(m.value.startswith("### ") for m in at.markdown)
    # 6 topics in the examples; Graphs has no accepted link (only review and rejected ones).
    assert any(m.value == S.QUIZ_READY_COUNT.format(ready=5, total=6) for m in at.markdown)
    listed = {b.key for b in at.button if b.key.startswith("topic_")}
    assert "topic_avl_tree" in listed and "topic_graphs" not in listed and len(listed) == 5


def test_quick_check_search_narrows_and_says_when_a_topic_is_not_ready(outputs):
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    at.text_input[0].set_value("avl").run()
    assert [b.key for b in at.button if b.key.startswith("topic_")] == ["topic_avl_tree"]
    assert not at.info or not any(S.QUIZ_TOPIC_NOT_READY in i.value for i in at.info)
    at.text_input[0].set_value("graphs").run()  # a real topic, but it is not ready
    assert not at.exception
    assert any(S.QUIZ_TOPIC_NOT_READY in i.value for i in at.info)
    assert not [b for b in at.button if b.key.startswith("topic_")]


def test_quick_check_search_finds_another_name_of_a_topic(outputs):
    course = with_examples(outputs)
    concepts = json.loads((course / "concepts.json").read_text())
    for concept in concepts["concepts"]:
        if concept["id"] == "binary_search_tree":
            concept["aliases"] = ["BST"]
    (course / "concepts.json").write_text(json.dumps(concepts))
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    at.text_input[0].set_value("bst").run()
    assert [b.key for b in at.button if b.key.startswith("topic_")] == ["topic_binary_search_tree"]


def test_a_long_list_of_ready_topics_says_there_are_more(outputs):
    course = with_examples(outputs)
    concepts = json.loads((course / "concepts.json").read_text())
    graph = json.loads((course / "validated_graph.json").read_text())
    quiz = json.loads((course / "quiz_items.json").read_text())
    edge = next(e for e in graph["edges"] if e["decision"] == "ACCEPT")
    for n in range(20):
        topic = {"id": f"t{n}", "name": f"Topic {n}", "aliases": [], "sources": []}
        concepts["concepts"].append(topic)
        graph["edges"].append({**edge, "id": f"x{n}", "source": "avl_tree", "target": f"t{n}"})
        quiz["items"].append({**quiz["items"][0], "id": f"q{n}", "concept_id": f"t{n}"})
    (course / "concepts.json").write_text(json.dumps(concepts))
    (course / "validated_graph.json").write_text(json.dumps(graph))
    (course / "quiz_items.json").write_text(json.dumps(quiz))
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    assert not at.exception
    assert len([b for b in at.button if b.key.startswith("topic_")]) == 15
    assert any(S.QUIZ_TYPE_MORE in c.value for c in at.caption)


def test_one_question_a_screen_with_big_buttons_and_no_total_or_timer(outputs, no_ai):
    at = start_quick_check()
    assert not at.exception
    assert not at.radio
    item = current_item(at)
    labels = [b.label for b in at.button]
    assert all(option in labels for option in item["options"])
    assert any(m.value == "**Question 1**" for m in at.markdown)
    assert len(at.get("progress")) == 1
    text = screen_text(at).lower()
    assert not re.search(r"\d+\s*(of|/)\s*\d+", text)
    assert "timer" not in text and "seconds" not in text


def test_a_wrong_answer_is_met_kindly_and_never_with_a_score(outputs, no_ai):
    at = answer_wrong(start_quick_check())
    item_answer = at.session_state["quiz_feedback"]["answer"]
    assert any(S.QUIZ_KIND in i.value for i in at.info)
    assert any(item_answer in m.value for m in at.markdown)
    text = screen_text(at).lower()
    for unkind in ("wrong", "incorrect", "not right", "score", "❌"):
        assert unkind not in text
    assert not re.search(r"\d+\s*(of|/)\s*\d+", text.replace("3 of the 6", ""))


def test_questions_are_counted_up_after_the_kind_message(outputs, no_ai):
    at = answer_wrong(start_quick_check())
    at = at.button(key="quiz_continue").click().run()
    assert not at.exception
    assert any(m.value == "**Question 2**" for m in at.markdown)
    rows = json.loads((outputs / "ds101" / "student_answers.json").read_text())["answers"]
    assert len(rows) == 1  # tapping on never logs the same answer twice


def test_the_progress_bar_only_moves_forward(outputs, no_ai):
    at = start_quick_check()
    seen = [at.get("progress")[0].proto.value]
    for _ in range(2):
        at = answer_wrong(at).button(key="quiz_continue").click().run()
        assert not at.exception
        seen.append(at.get("progress")[0].proto.value)
    assert seen == sorted(seen) and seen[-1] > seen[0]


def whole_site() -> AppTest:
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    return at.button(key="home_quiz").click().run()


def test_finishing_opens_the_plan_by_itself(outputs, no_ai):
    at = whole_site()
    at = at.button(key="topic_avl_tree").click().run()
    for _ in range(10):
        assert not at.exception and not at.error
        if at.title[0].value != S.QUIZ_TITLE:
            break
        at = tap_answer(at, correct=True)
    assert at.title[0].value == S.PLAN_TITLE
    # Every answer given on the way there is in the log.
    path = outputs / "ds101" / "student_answers.json"
    assert check_file(path) == []
    rows = json.loads(path.read_text())["answers"]
    assert [r["item_id"] for r in rows] == at.session_state["quiz_asked"]
    assert rows and all(r["correct"] is True for r in rows)


def test_a_wrong_last_answer_is_read_before_the_plan_opens(outputs, no_ai):
    at = whole_site()
    at = at.button(key="topic_trees").click().run()  # the only question on this topic
    at = tap_answer(at, correct=False)
    assert at.title[0].value == S.QUIZ_TITLE and any(S.QUIZ_KIND in i.value for i in at.info)
    at = at.button(key="quiz_continue").click().run()
    assert not at.exception and not at.error
    assert at.title[0].value == S.PLAN_TITLE


def test_coming_back_after_finishing_offers_a_new_topic_not_a_loop(outputs, no_ai):
    at = whole_site()
    at = at.button(key="topic_trees").click().run()
    at = tap_answer(at, correct=True)
    assert at.title[0].value == S.PLAN_TITLE
    at = at.button(key="plan_other_topic").click().run()
    assert not at.exception and not at.error
    assert at.title[0].value == S.QUIZ_TITLE and at.text_input


def test_no_ready_topics_says_so_and_points_to_the_teacher(outputs):
    course = with_examples(outputs)
    quiz = json.loads((course / "quiz_items.json").read_text())
    quiz["items"] = []
    (course / "quiz_items.json").write_text(json.dumps(quiz))
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    assert not at.exception
    assert any(S.QUIZ_NONE_READY in i.value for i in at.info)
    assert not at.text_input


def test_a_topic_with_links_but_no_questions_is_not_in_the_quick_check(outputs):
    course = with_examples(outputs)
    quiz = json.loads((course / "quiz_items.json").read_text())
    quiz["items"] = [q for q in quiz["items"] if q["concept_id"] != "recursion"]
    (course / "quiz_items.json").write_text(json.dumps(quiz))
    at = AppTest.from_file(str(QUIZ), default_timeout=60).run()
    assert not [b for b in at.button if b.key == "topic_recursion"]
    assert any(m.value == S.QUIZ_READY_COUNT.format(ready=4, total=6) for m in at.markdown)
    # The map needs no questions, so the topic is still there.
    at = map_page()
    assert any(m.value == S.MAP_READY_COUNT.format(ready=5, total=6) for m in at.markdown)


def test_no_concept_data_is_changed_and_teachers_see_what_is_not_ready(outputs):
    course = with_examples(outputs)
    before = (course / "concepts.json").read_bytes()
    assert len(json.loads(before)["concepts"]) == 6
    AppTest.from_file(str(QUIZ), default_timeout=60).run()
    map_page()
    teacher_page = SITE / "pages" / "teacher_AI_checks_and_review.py"
    at = AppTest.from_file(str(teacher_page), default_timeout=60).run()
    assert not at.exception
    assert (course / "concepts.json").read_bytes() == before
    text = " ".join(m.value for m in at.markdown)
    assert "Quick check: **5 of 6** topics. Topic map: **5 of 6** topics." in text
    assert "- Graphs: No accepted link yet" in text
    assert any("not ready for students yet (1)" in e.label for e in at.expander)


# --- study plan ---------------------------------------------------------------------


def plan_page(**state) -> AppTest:
    at = AppTest.from_file(str(PLAN), default_timeout=60)
    at.session_state["quiz_answers"] = [{"concept_id": "trees", "correct": False}]
    at.session_state["quiz_mastery"] = {"trees": 0.1}
    at.session_state["quiz_course"] = "ds101"
    at.session_state["study_target"] = "avl_tree"
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def test_plan_opens_with_what_to_study_and_where_to_read(outputs):
    at = plan_page()
    assert not at.exception
    assert at.markdown[0].value == S.PLAN_NEXT_TITLE.format(topic="Recursion")
    # The first topic has no link into it: its page comes from the topic's own source.
    assert at.markdown[1].value == "**Read:** 📄 ds_lec5.pdf, page 3"


def test_plan_steps_show_done_next_later_with_a_reason_and_no_raw_ids(outputs):
    at = plan_page()
    steps = [m.value for m in at.markdown if m.value.startswith("**Topic ")]
    assert steps[0].startswith("**Topic 1: Recursion**") and S.PLAN_STATUS_NEXT in steps[0]
    assert all(S.PLAN_STATUS_LATER in s for s in steps[1:])
    text = screen_text(at)
    assert "You need this before Binary Trees." in text
    assert "avl_tree" not in text and "binary_tree" not in text
    assert "Essential foundation" not in text  # the backwards text from the path
    assert "%" not in text  # no estimate shown as if it were measured


def test_mark_as_done_moves_on_and_stays_for_the_session(outputs):
    at = plan_page()
    at = at.button(key="done_recursion").click().run()
    assert not at.exception
    assert at.markdown[0].value == S.PLAN_NEXT_TITLE.format(topic="Trees")
    steps = [m.value for m in at.markdown if m.value.startswith("**Topic ")]
    assert S.PLAN_STATUS_DONE in steps[0] and S.PLAN_STATUS_NEXT in steps[1]
    assert at.session_state["plan_done"]["ds101"] == ["recursion"]
    assert at.session_state["quiz_mastery"]["trees"] == 0.1  # it says nothing about what they know
    assert not (outputs / "ds101" / "student_answers.json").exists()


def test_plan_says_so_when_everything_is_done(outputs):
    order = ["recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"]
    at = plan_page(plan_done={"ds101": order})
    assert not at.exception
    assert any("every step as done for AVL Trees" in s.value for s in at.success)
    assert at.button(key="plan_other_topic")


def test_plan_says_so_when_everything_is_known_and_offers_another_topic(outputs):
    known = {
        c: 0.9 for c in ("recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree")
    }
    at = plan_page(quiz_mastery=known)
    assert not at.exception
    assert any("already know what you need for AVL Trees" in s.value for s in at.success)
    assert at.button(key="plan_other_topic")
    assert not any(m.value.startswith("### 📖") for m in at.markdown)


def test_plan_handles_a_topic_outside_the_graph(outputs):
    course = with_examples(outputs)
    concepts = json.loads((course / "concepts.json").read_text())
    concepts["concepts"].append({"id": "lonely", "name": "Lonely", "aliases": [], "sources": []})
    (course / "concepts.json").write_text(json.dumps(concepts))
    at = plan_page(study_target="lonely")
    assert not at.exception
    assert any(S.PLAN_EMPTY in i.value for i in at.info)


# --- topic map ----------------------------------------------------------------------


def map_page(focus: str | None = None) -> AppTest:
    at = AppTest.from_file(str(TOPIC_MAP), default_timeout=60)
    if focus:
        at.session_state["map_focus"] = focus
    return at.run()


def test_map_shows_before_this_next_without_the_heavy_picture(outputs):
    at = map_page("binary_tree")
    assert not at.exception
    assert not at.get("iframe")
    assert at.button(key="before_trees").label == "Trees"
    assert at.button(key="after_binary_search_tree").label == "Binary Search Trees"
    assert any(m.value == S.MAP_THIS_TOPIC.format(topic="Binary Trees") for m in at.markdown)
    assert at.button(key="map_full_button").label == S.MAP_SEE_FULL


def test_tapping_a_card_moves_the_focus(outputs):
    at = map_page("binary_tree")
    at = at.button(key="after_binary_search_tree").click().run()
    assert not at.exception
    assert any(m.value == S.MAP_THIS_TOPIC.format(topic="Binary Search Trees") for m in at.markdown)


def test_searching_the_map_moves_the_focus_and_clears_the_box(outputs):
    at = map_page("binary_tree")
    at.text_input[0].set_value("avl").run()
    assert not at.exception
    at = at.button(key="found_avl_tree").click().run()
    assert any(m.value == S.MAP_THIS_TOPIC.format(topic="AVL Trees") for m in at.markdown)
    assert at.text_input[0].value == ""


def test_map_search_says_when_a_topic_is_not_ready(outputs):
    at = map_page("binary_tree")
    at.text_input[0].set_value("graphs").run()  # no accepted link
    assert any(S.MAP_TOPIC_NOT_READY in i.value for i in at.info)


def test_map_lists_only_ready_topics_with_the_real_count(outputs):
    at = map_page()
    assert any(m.value == S.MAP_READY_COUNT.format(ready=5, total=6) for m in at.markdown)
    listed = {b.key for b in at.button if b.key.startswith("all_")}
    assert "all_trees" in listed and "all_graphs" not in listed
    at = at.button(key="all_trees").click().run()
    assert any(m.value == S.MAP_THIS_TOPIC.format(topic="Trees") for m in at.markdown)


def example_edges() -> list[dict]:
    return json.loads((common.EXAMPLES / "validated_graph.json").read_text())["edges"]


def test_map_cards_use_accepted_links_only(outputs):
    other = [e for e in example_edges() if e["decision"] != "ACCEPT"]
    assert other
    for edge in other:
        at = map_page(edge["source"])
        assert not at.exception
        assert not [b for b in at.button if b.key == f"after_{edge['target']}"]
        at = map_page(edge["target"])
        assert not [b for b in at.button if b.key == f"before_{edge['source']}"]


def test_full_map_picture_uses_accepted_links_only_and_waits_for_the_button(outputs):
    pytest.importorskip("pyvis")  # not installed in CI: see the next test for that case
    at = map_page("binary_tree")
    assert not at.get("iframe")  # off until the button is pressed
    at = at.button(key="map_full_button").click().run()
    assert not at.exception
    html = at.get("iframe")[0].proto.srcdoc
    for edge in example_edges():
        drawn = re.search(rf'"from": "{edge["source"]}"[^}}]*"to": "{edge["target"]}"', html)
        assert bool(drawn) == (edge["decision"] == "ACCEPT")
    at = at.button(key="map_full_button").click().run()
    assert not at.get("iframe")


def test_full_map_without_the_drawing_library_lists_accepted_links_only(outputs, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvis.network", None)  # importing it now fails
    names = common.concept_names()
    at = map_page("binary_tree")
    assert not any("comes before" in m.value for m in at.markdown)  # off until the button
    at = at.button(key="map_full_button").click().run()
    assert not at.exception
    assert not at.get("iframe")
    listed = " ".join(m.value for m in at.markdown)
    for edge in example_edges():
        line = f"**{names[edge['source']]}** comes before **{names[edge['target']]}**"
        assert (line in listed) == (edge["decision"] == "ACCEPT")


def test_a_stale_focus_on_a_topic_that_is_not_ready_moves_to_a_ready_one(outputs):
    at = map_page("graphs")
    assert not at.exception
    assert not any(m.value == S.MAP_THIS_TOPIC.format(topic="Graphs") for m in at.markdown)


def test_one_sided_topic_never_implies_nothing_comes_first(outputs):
    at = map_page("trees")
    assert any(S.MAP_NOTHING_BEFORE == c.value for c in at.caption)
    assert "may not be complete" in S.MAP_NOTHING_BEFORE


def test_machine_reason_is_not_shown_to_students(outputs):
    at = map_page("binary_tree")
    assert "defined as a restricted kind" not in screen_text(at)


def test_pages_import_only_the_public_apis():
    for page in (QUIZ, PLAN, TOPIC_MAP):
        for line in page.read_text().splitlines():
            if re.match(r"\s*(from|import) cdlp", line):
                assert "learning_path import api" in line or "root_cause import api" in line, line


# --- answers are shown shuffled ------------------------------------------------------------


def shown_answer_keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button if b.key and b.key.startswith("answer_")]


def expected_keys(item: dict) -> list[str]:
    pairs = common.stable_order(list(enumerate(item["options"])), item["id"])
    return [f"answer_{item['id']}_{index}" for index, _ in pairs]


def test_shuffle_is_stable_and_keeps_every_item():
    items = list(range(6))
    first = common.stable_order(items, "q_loops_1")
    assert first == common.stable_order(items, "q_loops_1")
    assert sorted(first) == items and items == list(range(6))  # the list passed in is untouched


def test_shuffle_is_the_same_in_a_new_process():
    """A restarted server must show the same order, whatever PYTHONHASHSEED it gets."""
    code = (
        "import random; r = random.Random('q_loops_1'); x = list(range(6)); r.shuffle(x); print(x)"
    )
    orders = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2")
    }
    assert orders == {str(common.stable_order(list(range(6)), "q_loops_1"))}


def test_the_right_answer_is_not_always_first():
    places = {
        common.stable_order(["right", "b", "c", "d"], f"q_{n}").index("right") for n in range(40)
    }
    assert places == {0, 1, 2, 3}


def test_answers_show_shuffled_and_keep_their_order_on_a_rerun(outputs):
    at = start_quick_check()
    item = current_item(at)
    first = shown_answer_keys(at)
    assert first == expected_keys(item)
    assert shown_answer_keys(at.run()) == first
    assert sorted(first) == sorted(f"answer_{item['id']}_{i}" for i in range(len(item["options"])))


def test_shuffling_changes_no_question_or_option_text(outputs):
    at = start_quick_check()
    item = current_item(at)  # found by its exact text
    labels = {b.label.replace("\\", "") for b in at.button if b.key in shown_answer_keys(at)}
    assert labels == {o.replace("\\", "") for o in item["options"]}


def test_answers_are_checked_by_text_not_by_place(outputs):
    """The right answer is still marked right wherever it lands, and a wrong one wrong."""
    for correct in (True, False):
        answers = outputs / "ds101" / "student_answers.json"
        answers.unlink(missing_ok=True)
        at = start_quick_check()
        item = current_item(at)
        tap_answer(at, correct=correct)
        row = json.loads(answers.read_text())["answers"][0]
        assert row["correct"] is correct
        assert (row["answer"] == item["answer"]) is correct


def test_a_right_answer_shown_away_from_its_original_place_is_right(outputs, monkeypatch):
    """Force the case: the right answer (first in the file) is drawn last."""
    monkeypatch.setattr(common, "stable_order", lambda items, seed: list(reversed(items)))
    at = start_quick_check()
    item = current_item(at)
    right = item["options"].index(item["answer"])
    assert shown_answer_keys(at)[len(item["options"]) - 1 - right].endswith(f"_{right}")
    at.button(key=f"answer_{item['id']}_{right}").click().run()
    row = json.loads((outputs / "ds101" / "student_answers.json").read_text())["answers"][0]
    assert row["correct"] is True and row["answer"] == item["answer"]
