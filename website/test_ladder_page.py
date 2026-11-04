"""The quick check and study plan with the level ladder. No LLM."""

import json
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

from cdlp.root_cause import api as root_cause_api  # noqa: E402

LADDER_QUIZ = json.loads((common.EXAMPLES / "ladder_quiz_items.json").read_text())["items"]


@pytest.fixture(autouse=True)
def course(tmp_path, monkeypatch):
    folder = tmp_path / "ds101"
    folder.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "validated_graph.json"):
        shutil.copy(common.EXAMPLES / name, folder / name)
    shutil.copy(common.EXAMPLES / "ladder_quiz_items.json", folder / "quiz_items.json")
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    monkeypatch.setattr(
        root_cause_api,
        "trace",
        lambda *a, **k: {
            "explanation": "[fallback: offline estimate] x",
            "traced_concept": "trees",
        },
    )
    common.st.cache_data.clear()
    yield folder
    common.st.cache_data.clear()


def start(target: str = "avl_tree") -> AppTest:
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    at.button(key="home_quiz").click().run()
    return at.button(key=f"topic_{target}").click().run()


def shown(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.success] + [i.value for i in at.info]
    return " ".join(parts + [w.value for w in at.warning])


def heading(at: AppTest) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("### "))


def current(at: AppTest) -> dict:
    return next(q for q in LADDER_QUIZ if q["question"] == heading(at)[4:])


def studied(at: AppTest, concept: str, answer: str) -> AppTest:
    return at.button(key=f"studied_{concept}_{answer}").click().run()


def tap(at: AppTest, correct: bool) -> AppTest:
    item = current(at)
    index = next(i for i, o in enumerate(item["options"]) if (o == item["answer"]) == correct)
    return at.button(key=f"answer_{item['id']}_{index}").click().run()


def know(at: AppTest, concept: str) -> AppTest:
    at = studied(at, concept, "yes")
    return tap(tap(at, True), True)


def test_the_first_screen_asks_if_the_first_topic_was_studied():
    at = start()
    assert not at.exception
    assert heading(at) == "### Have you studied Recursion?"
    labels = [b.label for b in at.button if b.key and b.key.startswith("studied_")]
    assert labels == [S.QUIZ_STUDIED_YES, S.QUIZ_STUDIED_NO, S.QUIZ_STUDIED_NOT_SURE]
    assert "Question 1" not in shown(at)


@pytest.mark.parametrize("answer, level", [("yes", "medium"), ("no", "easy"), ("not_sure", "easy")])
def test_the_answer_picks_the_first_level_and_marks_nothing_known(answer, level):
    at = studied(start(), "recursion", answer)
    assert not at.exception
    assert current(at)["difficulty"] == level and current(at)["concept_id"] == "recursion"
    assert "recursion" not in at.session_state["quiz_mastery"]


def test_the_page_never_shows_the_level_label():
    at = studied(start(), "recursion", "yes")
    text = shown(at).lower()
    assert "medium" not in text and "difficulty" not in text and "suggestion" not in text


def test_answers_stay_shuffled_and_are_logged(course):
    at = studied(start(), "recursion", "yes")
    tap(at, True)
    row = json.loads((course / "student_answers.json").read_text())["answers"][0]
    assert row["concept_id"] == "recursion" and row["correct"] is True


def test_know_it_moves_to_the_next_topic_with_a_new_question():
    at = know(start(), "recursion")
    assert not at.exception
    assert heading(at) == "### Have you studied Trees?"
    assert "That's right" in shown(at)


def test_a_wrong_easy_answer_stops_and_the_plan_explains_it():
    at = know(start(), "recursion")
    at = studied(at, "trees", "no")
    at = tap(at, False)
    assert S.QUIZ_KIND in shown(at)
    at = at.button(key="quiz_continue").click().run()
    assert not at.exception
    assert at.title[0].value == S.PLAN_TITLE
    text = shown(at)
    assert "You already know Recursion, so start with Trees." in text
    assert S.PLAN_RESULTS["start_here"] in text
    assert S.PLAN_RESULTS["not_checked"] in text
    assert S.PLAN_LADDER_STOPPED.format(topic="Trees") in text
    assert S.PLAN_MORE_QUESTIONS not in [b.label for b in at.button]


def test_stopping_at_the_last_topic_does_not_mention_later_topics():
    at = start("trees")
    at = studied(at, "trees", "no")
    at = tap(at, False)
    at = at.button(key="quiz_continue").click().run()
    assert at.title[0].value == S.PLAN_TITLE and not at.exception
    assert S.PLAN_RESULTS["start_here"] in [m.value for m in at.markdown]
    assert "later topics" not in shown(at)


def test_the_plan_shows_each_result_and_starts_at_the_first_not_known():
    at = know(start(), "recursion")
    at = know(at, "trees")
    at = know(at, "binary_tree")
    at = studied(at, "binary_search_tree", "yes")
    at = tap(at, True)  # medium right
    at = tap(at, False)  # hard wrong: quick revision
    at = at.button(key="quiz_continue").click().run()
    at = studied(at, "avl_tree", "no")
    at = tap(at, True)  # easy right
    at = tap(at, False)  # medium wrong: study this
    at = at.button(key="quiz_continue").click().run()
    assert not at.exception and at.title[0].value == S.PLAN_TITLE
    text = shown(at)
    assert (
        "You already know Recursion, Trees and Binary Trees, so start with Binary Search Trees."
    ) in text
    lines = [m.value for m in at.markdown]
    assert S.PLAN_RESULTS["quick_revision"] in lines and S.PLAN_RESULTS["study_this"] in lines
    assert "Study this next: Binary Search Trees" in text
    assert "✅ Know it: Binary Trees" in text


def test_nothing_known_says_only_where_to_start():
    at = start("binary_tree")
    at = studied(at, "recursion", "not_sure")
    at = tap(at, False)
    at = at.button(key="quiz_continue").click().run()
    at = studied(at, "trees", "no")
    at = tap(at, False)
    at = at.button(key="quiz_continue").click().run()
    assert "Start with Recursion." in shown(at) and "You already know" not in shown(at)


def test_a_gap_on_a_soft_link_keeps_asking_and_the_note_says_so():
    at = studied(start(), "recursion", "no")
    at = tap(at, False)
    at = at.button(key="quiz_continue").click().run()
    assert heading(at) == "### Have you studied Trees?"
    at = know(at, "trees")
    assert heading(at) == "### Have you studied Binary Trees?"  # only a soft link from Recursion
    at = know(at, "binary_tree")
    at = know(at, "binary_search_tree")
    at = know(at, "avl_tree")
    assert not at.exception and at.title[0].value == S.PLAN_TITLE
    text = shown(at)
    assert S.PLAN_LADDER_STILL_ASKED.format(topics="Binary Trees", topic="Recursion") in text
    assert "We stopped at" not in text and "We did not ask" not in text
    assert S.PLAN_RESULTS["not_checked"] not in [m.value for m in at.markdown]
    assert "so start with Recursion." in text


def test_a_gap_on_hard_links_says_those_topics_were_not_asked():
    at = know(start(), "recursion")
    at = studied(at, "trees", "no")
    at = tap(at, False)
    at = at.button(key="quiz_continue").click().run()
    text = shown(at)
    assert S.PLAN_LADDER_STOPPED.format(topic="Trees") in text
    assert "We still asked" not in text
    assert [m.value for m in at.markdown].count(S.PLAN_RESULTS["not_checked"]) == 3


def test_no_hard_question_ends_at_quick_revision_without_asking(course):
    quiz = json.loads((course / "quiz_items.json").read_text())
    quiz["items"] = [i for i in quiz["items"] if i["difficulty"] != "hard"]
    (course / "quiz_items.json").write_text(json.dumps(quiz))
    common.st.cache_data.clear()
    at = studied(start("trees"), "trees", "yes")
    at = tap(at, True)  # medium right, and no hard question exists
    assert not at.exception and at.title[0].value == S.PLAN_TITLE
    assert S.PLAN_RESULTS["quick_revision"] in [m.value for m in at.markdown]
    log = json.loads((course / "student_answers.json").read_text())["answers"]
    assert len(log) == 1


def test_the_card_says_start_from_the_basics():
    assert S.PLAN_RESULTS["start_here"] == "🏁 Start from the basics"
    assert "Start here" not in S.PLAN_RESULTS.values()


def test_all_known_says_so():
    at = start()
    for concept in ("recursion", "trees", "binary_tree", "binary_search_tree", "avl_tree"):
        at = know(at, concept)
    assert not at.exception
    # Streamlit shows a leading emoji as the alert's icon, not as part of its text.
    assert S.PLAN_ALL_KNOWN.format(topic="AVL Trees").removeprefix("🎉 ") in shown(at)


def test_seeing_the_plan_early_keeps_the_rest_not_checked_and_lets_you_go_back():
    at = know(start(), "recursion")
    at = studied(at, "trees", "yes")
    next(b for b in at.button if b.label == S.QUIZ_TO_PLAN).click().run()
    assert at.title[0].value == S.PLAN_TITLE
    text = shown(at)
    assert S.PLAN_RESULTS["not_checked"] in text and "start with Trees" in text
    at.button(key="plan_more").click().run()
    assert not at.exception and at.title[0].value == S.QUIZ_TITLE
    assert current(at)["concept_id"] == "trees"


def test_the_limit_note_shows_when_ten_questions_end_the_quiz():
    at = start()
    for concept in ("recursion", "trees", "binary_tree"):
        at = studied(at, concept, "no")
        at = tap(tap(tap(at, True), True), True)
    at = studied(at, "binary_search_tree", "no")
    at = tap(at, True)
    assert not at.exception and at.title[0].value == S.PLAN_TITLE
    text = shown(at)
    assert S.PLAN_LIMIT_NOTE.format(n=10) in text
    assert "start with Binary Search Trees" in text and S.PLAN_RESULTS["not_checked"] in text


# --- a course without levels keeps today's quick check -------------------------------------


def old_quiz(course: Path) -> None:
    shutil.copy(common.EXAMPLES / "quiz_items.json", course / "quiz_items.json")


def test_a_course_without_levels_asks_no_self_report(course):
    old_quiz(course)
    at = start()
    assert not at.exception
    assert "Have you studied" not in shown(at)
    assert "Binary Trees" in shown(at)
    assert not [b for b in at.button if b.key and b.key.startswith("studied_")]
    assert "__ladder__" not in at.session_state["quiz_mastery"]


def test_a_course_without_levels_shows_no_ladder_words_on_the_plan(course):
    old_quiz(course)
    at = start()
    quiz = json.loads((course / "quiz_items.json").read_text())["items"]
    item = next(q for q in quiz if q["question"] == heading(at)[4:])
    at = at.button(key=f"answer_{item['id']}_{item['options'].index(item['answer'])}").click().run()
    next(b for b in at.button if b.label == S.QUIZ_TO_PLAN).click().run()
    assert at.title[0].value == S.PLAN_TITLE and not at.exception
    lines = [m.value for m in at.markdown]
    for words in S.PLAN_RESULTS.values():
        assert words not in lines
    assert "You already know" not in shown(at)
