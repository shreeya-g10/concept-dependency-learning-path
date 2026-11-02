"""The question limit per chosen topic, and how the study plan reads a quiz it stopped. No LLM."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
QUIZ = SITE / "pages" / "3_Quick_check.py"
PLAN = SITE / "pages" / "4_My_study_plan.py"
sys.path.insert(0, str(SITE))

import common  # noqa: E402
import strings as S  # noqa: E402
from test_foundation import visible_text  # noqa: E402

from cdlp.learning_path import api  # noqa: E402

LIMIT = api.MAX_QUESTIONS_PER_TOPIC


def edge(source, target):
    return {
        "id": f"{source}_{target}",
        "source": source,
        "target": target,
        "type": "PREREQUISITE",
        "strength": "hard",
        "decision": "ACCEPT",
        "confidence": 0.9,
        "checks": {
            "evidence": "strong",
            "semantic": "strong",
            "necessity": "skipped",
            "graph": "ok",
        },
        "evidence": [],
        "reason": "because",
    }


def wide_course(outputs: Path) -> None:
    """Two separate topics, each with 14 direct earlier topics; `root` sits under a00."""
    ids = [f"{side}{i:02}" for side in "ab" for i in range(14)] + ["root", "goal_a", "goal_b"]
    edges = [edge(f"a{i:02}", "goal_a") for i in range(14)]
    edges += [edge(f"b{i:02}", "goal_b") for i in range(14)]
    edges += [edge("root", "a00")]
    course = outputs / "ds101"
    course.mkdir()
    shutil.copy(common.EXAMPLES / "chunks.jsonl", course / "chunks.jsonl")
    (course / "concepts.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "course_id": "ds101",
                "concepts": [
                    {"id": c, "name": f"Topic {c}", "aliases": [], "sources": []} for c in ids
                ],
            }
        )
    )
    (course / "validated_graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.5",
                "course_id": "ds101",
                "nodes": [{"id": c, "name": f"Topic {c}"} for c in ids],
                "edges": edges,
            }
        )
    )
    (course / "quiz_items.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "course_id": "ds101",
                "items": [
                    {
                        "id": f"q_{c}",
                        "concept_id": c,
                        "question": f"About {c}?",
                        "options": ["right", "wrong"],
                        "answer": "right",
                    }
                    for c in ids
                ],
            }
        )
    )


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    wide_course(tmp_path)
    common.st.cache_data.clear()
    yield tmp_path
    common.st.cache_data.clear()


def home() -> AppTest:
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    return at.button(key="home_quiz").click().run()


def pick(at: AppTest, topic: str) -> AppTest:
    """More topics than the picker lists at once, so type the name, as a student would."""
    at = at.text_input(key="quiz_search").input(topic).run()
    return at.button(key=f"topic_{topic}").click().run()


def answer_right(at: AppTest) -> AppTest:
    button = next(
        b for b in at.button if b.key and b.key.startswith("answer_") and b.key[-2:] == "_0"
    )
    return button.click().run()


def question_shown(at: AppTest) -> bool:
    return any(b.key and b.key.startswith("answer_") for b in at.button)


def plan_steps(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_the_quiz_stops_at_the_limit_and_opens_the_plan(outputs):
    at = home()
    at = pick(at, "goal_a")
    for number in range(1, LIMIT + 1):
        assert question_shown(at)
        assert any(S.QUIZ_QUESTION.format(number=number) == m.value for m in at.markdown)
        at = answer_right(at)
        assert not at.exception and not at.error
    assert at.title[0].value == S.PLAN_TITLE
    assert at.session_state["quiz_topic_counts"] == {"goal_a": LIMIT}


def test_the_plan_treats_unanswered_topics_as_unknown_after_the_limit(outputs):
    at = pick(home(), "goal_a")
    for _ in range(LIMIT):
        at = answer_right(at)
    observed = at.session_state["quiz_mastery"]["__observed__"]
    assert len(observed) == LIMIT
    text = plan_steps(at)
    for concept in [f"a{i:02}" for i in range(14)] + ["goal_a"]:
        shown = f"Topic {concept}" in text
        assert shown == (concept not in observed), concept
    assert not any("already know" in s.value for s in at.success)
    assert any(S.PLAN_LIMIT_NOTE.format(n=LIMIT) == i.value for i in at.info)
    # no way back into questions the limit stopped
    assert "plan_more" not in [b.key for b in at.button]


def test_a_topic_only_inferred_from_a_right_answer_also_stays_on_the_plan(outputs):
    """Stopped by the limit: root was never asked, whatever a right answer on a00 suggested."""
    at = AppTest.from_file(str(PLAN), default_timeout=60)
    answered = {f"a{i:02}": True for i in range(LIMIT)}
    at.session_state["quiz_answers"] = [{"concept_id": c, "correct": True} for c in answered]
    at.session_state["quiz_asked"] = [f"q_{c}" for c in answered]
    at.session_state["quiz_mastery"] = {
        **dict.fromkeys(answered, 0.9),
        "root": 0.85,
        "__observed__": answered,
    }
    at.session_state["quiz_course"] = "ds101"
    at.session_state["study_target"] = "goal_a"
    at.session_state["quiz_topic_counts"] = {"goal_a": LIMIT}
    at.run()
    assert not at.exception
    assert "Topic root" in plan_steps(at)
    assert "Topic a00" not in plan_steps(at)


def test_below_the_limit_inference_still_prunes_the_plan(outputs):
    at = AppTest.from_file(str(PLAN), default_timeout=60)
    at.session_state["quiz_answers"] = [{"concept_id": "a00", "correct": True}]
    at.session_state["quiz_asked"] = ["q_a00"]
    at.session_state["quiz_mastery"] = {"a00": 0.9, "root": 0.85, "__observed__": {"a00": True}}
    at.session_state["quiz_course"] = "ds101"
    at.session_state["study_target"] = "goal_a"
    at.session_state["quiz_topic_counts"] = {"goal_a": 1}
    at.run()
    assert "Topic root" not in plan_steps(at)
    assert not at.info
    assert at.button(key="plan_more")


def test_exactly_ten_answers_with_nothing_left_is_not_called_a_stop(outputs):
    at = AppTest.from_file(str(PLAN), default_timeout=60)
    ids = [f"a{i:02}" for i in range(14)] + ["root", "goal_a"]
    at.session_state["quiz_answers"] = [{"concept_id": c, "correct": True} for c in ids]
    at.session_state["quiz_asked"] = [f"q_{c}" for c in ids]
    at.session_state["quiz_mastery"] = {
        **dict.fromkeys(ids, 0.9),
        "__observed__": dict.fromkeys(ids, True),
    }
    at.session_state["quiz_course"] = "ds101"
    at.session_state["study_target"] = "goal_a"
    at.session_state["quiz_topic_counts"] = {"goal_a": LIMIT}
    at.run()
    assert any("already know" in s.value for s in at.success)
    assert not any(S.PLAN_LIMIT_NOTE.format(n=LIMIT) == i.value for i in at.info)


def test_the_limit_counts_per_topic_not_per_session(outputs):
    at = pick(home(), "goal_a")
    for _ in range(4):
        at = answer_right(at)
    at = at.button(key="quiz_other_topic").click().run()
    at = pick(at, "goal_b")
    assert any(S.QUIZ_QUESTION.format(number=1) == m.value for m in at.markdown)
    for _ in range(LIMIT):  # the 4 answers on the first topic do not use up this one's limit
        assert question_shown(at)
        at = answer_right(at)
    assert at.title[0].value == S.PLAN_TITLE
    assert at.session_state["quiz_topic_counts"] == {"goal_a": 4, "goal_b": LIMIT}
    assert len(at.session_state["quiz_asked"]) == 4 + LIMIT


def test_going_back_to_a_topic_does_not_start_its_count_again(outputs):
    at = pick(home(), "goal_a")
    for _ in range(LIMIT):
        at = answer_right(at)
    at = at.button(key="plan_other_topic").click().run()
    at = pick(at, "goal_a")
    assert not at.exception
    assert at.title[0].value == S.PLAN_TITLE  # straight to the plan, no eleventh question
    assert len(at.session_state["quiz_asked"]) == LIMIT


def test_the_note_uses_plain_words(outputs):
    at = pick(home(), "goal_a")
    for _ in range(LIMIT):
        at = answer_right(at)
    assert S.PLAN_LIMIT_NOTE.format(n=LIMIT) in visible_text(at)
