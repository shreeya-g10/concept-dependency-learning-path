"""Page 5 logs every answer anonymously and labels a non-LLM root cause.

Nothing here calls an LLM: the root-cause tracer is faked, and outputs/ points to tmp_path.
"""

import json
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
PAGE5 = SITE / "pages" / "5_My_Learning_Path.py"
sys.path.insert(0, str(SITE))

import common  # noqa: E402

from cdlp.root_cause import api as root_cause_api  # noqa: E402
from cdlp.shared.validate import check_file  # noqa: E402


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    return tmp_path


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


def answer_wrong(at: AppTest) -> AppTest:
    """Pick a wrong option for the current question and submit."""
    quiz = json.loads((common.EXAMPLES / "quiz_items.json").read_text())["items"]
    question = at.markdown[[m.value.startswith("### ") for m in at.markdown].index(True)].value
    item = next(q for q in quiz if q["question"] == question[4:])
    at.radio[0].set_value(next(o for o in item["options"] if o != item["answer"]))
    return at.button[-1].click().run()


def test_page5_logs_answer_and_labels_offline_root_cause(outputs, monkeypatch):
    calls = []

    def fake_trace(graph, quiz_item, answer, mastery, *, allow_fallback=False):
        calls.append(allow_fallback)
        return {"explanation": "[fallback: offline estimate] Gap is likely in trees."}

    monkeypatch.setattr(root_cause_api, "trace", fake_trace)
    at = answer_wrong(AppTest.from_file(str(PAGE5), default_timeout=60).run())
    assert not at.exception

    assert calls == [True]  # the page asks for the fallback
    path = outputs / "ds101" / "student_answers.json"
    assert check_file(path) == []
    rows = json.loads(path.read_text())["answers"]
    assert len(rows) == 1 and rows[0]["correct"] is False
    assert rows[0]["student_id"].startswith("anon_")  # random id, nothing identifying

    shown = " ".join(c.value for c in at.caption)
    assert "offline estimate" in shown and "[fallback:" not in shown
    assert "Gap is likely in trees." in shown
