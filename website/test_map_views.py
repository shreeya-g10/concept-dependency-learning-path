"""The topic map's two views, its 30-link rule and the study plan's button. No LLM.

A stand-in for the drawing library records what would be drawn, so these also run in CI, where
pyvis is not installed. One test at the end uses the real library when it is there.
"""

import json
import logging
import shutil
import sys
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402
import jobs  # noqa: E402
import strings as S  # noqa: E402
import ui  # noqa: E402

from cdlp.learning_path.ladder import RESULT_MASTERY  # noqa: E402
from cdlp.root_cause import api as root_cause_api  # noqa: E402

MAP = str(SITE / ui.PAGES["map"].path)
PLAN = str(SITE / ui.PAGES["plan"].path)
COURSE = "ds101"
RESULT_WORDS = [*S.PLAN_RESULTS.values(), S.PLAN_RESULT_THINK_KNOWN]


@pytest.fixture(autouse=True)
def course(tmp_path, monkeypatch):
    folder = tmp_path / COURSE
    folder.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "validated_graph.json", "quiz_items.json"):
        shutil.copy(common.EXAMPLES / name, folder / name)
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    monkeypatch.setattr(
        root_cause_api,
        "trace",
        lambda *a, **k: {"explanation": "[fallback: offline estimate] x", "traced_concept": "x"},
    )
    common.st.cache_data.clear()
    yield folder
    common.st.cache_data.clear()


@pytest.fixture
def drawn(monkeypatch):
    """Stands in for pyvis: {"nodes": {id: arguments}, "edges": [(source, target, title)]}."""
    record = {"nodes": {}, "edges": [], "bgcolor": None}

    class Network:
        def __init__(self, **kwargs):
            record["bgcolor"] = kwargs.get("bgcolor")

        def add_node(self, node_id, **kwargs):
            record["nodes"][node_id] = kwargs

        def add_edge(self, source, target, **kwargs):
            record["edges"].append((source, target, kwargs.get("title")))

        def set_options(self, options):
            record["options"] = options

        def generate_html(self):
            return "<html><head></head><body>picture</body></html>"

    module = types.ModuleType("pyvis.network")
    module.Network = Network
    monkeypatch.setitem(sys.modules, "pyvis", types.ModuleType("pyvis"))
    monkeypatch.setitem(sys.modules, "pyvis.network", module)
    return record


def write_chain(course: Path, links: int) -> str:
    """A course that is one line of topics with this many links. Returns the last topic."""
    ids = [f"t{i}" for i in range(links + 1)]
    edge = next(
        e
        for e in json.loads((common.EXAMPLES / "validated_graph.json").read_text())["edges"]
        if e["decision"] == "ACCEPT"
    )
    (course / "validated_graph.json").write_text(
        json.dumps(
            {
                "course_id": COURSE,
                "nodes": [{"id": i, "name": i} for i in ids],
                "edges": [
                    {**edge, "id": f"e{n}", "source": a, "target": b, "strength": "hard"}
                    for n, (a, b) in enumerate(zip(ids, ids[1:], strict=False))
                ],
            }
        )
    )
    (course / "concepts.json").write_text(
        json.dumps({"concepts": [{"id": i, "name": i, "aliases": [], "sources": []} for i in ids]})
    )
    common.st.cache_data.clear()
    return ids[-1]


def answered_state(target: str, mastery: dict | None = None) -> dict:
    return {
        "quiz_answers": [{"concept_id": target, "correct": False}],
        "quiz_mastery": mastery if mastery is not None else {target: 0.1},
        "quiz_course": COURSE,
        "study_target": target,
    }


def open_page(path: str, **state) -> AppTest:
    at = AppTest.from_file(path, default_timeout=60)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def shown(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [i.value for i in at.info] + [w.value for w in at.warning]
    return " ".join(parts + [b.label for b in at.button])


def label(record: dict, concept_id: str) -> str:
    return record["nodes"][concept_id]["label"].replace("\n", " ")


# --- the 30-link rule, on both views ---------------------------------------------------


@pytest.mark.parametrize("view", [S.MAP_VIEW_PATH, S.MAP_VIEW_ALL])
def test_a_map_of_exactly_30_links_shows_by_itself_with_no_button(course, drawn, view):
    target = write_chain(course, 30)
    at = open_page(MAP, **answered_state(target), map_view_mode=view)
    assert not at.exception
    assert len(at.get("iframe")) == 1
    assert len(drawn["edges"]) == 30
    assert "map_full_button" not in [b.key for b in at.button]


@pytest.mark.parametrize(
    "view, see, hide",
    [
        (S.MAP_VIEW_PATH, S.MAP_SEE_PATH, S.MAP_HIDE_PATH),
        (S.MAP_VIEW_ALL, S.MAP_SEE_FULL, S.MAP_HIDE_FULL),
    ],
)
def test_a_map_of_31_links_sends_nothing_until_the_button(course, drawn, view, see, hide):
    target = write_chain(course, 31)
    at = open_page(MAP, **answered_state(target), map_view_mode=view)
    assert not at.exception
    assert not at.get("iframe")
    assert not drawn["nodes"]  # the library was not even used
    assert at.button(key="map_full_button").label == see
    at = at.button(key="map_full_button").click().run()
    assert len(at.get("iframe")) == 1
    assert len(drawn["edges"]) == 31
    assert at.button(key="map_full_button").label == hide
    at = at.button(key="map_full_button").click().run()
    assert not at.get("iframe")


def test_the_limit_counts_the_links_of_the_view_on_screen(course, drawn):
    """A short path shows at once. Its tap must not also send a large All Topics map."""
    write_chain(course, 31)
    at = open_page(MAP, **answered_state("t3"))
    assert not at.exception
    assert len(at.get("iframe")) == 1
    assert len(drawn["edges"]) == 3
    at.radio(key="map_view_mode").set_value(S.MAP_VIEW_ALL).run()
    assert not at.get("iframe")
    assert at.button(key="map_full_button").label == S.MAP_SEE_FULL


def test_opening_a_large_path_does_not_open_a_large_all_topics_map(course, drawn):
    target = write_chain(course, 31)
    at = open_page(MAP, **answered_state(target))
    at = at.button(key="map_full_button").click().run()
    assert len(at.get("iframe")) == 1
    at.radio(key="map_view_mode").set_value(S.MAP_VIEW_ALL).run()
    assert not at.get("iframe")


# --- when each view is offered ----------------------------------------------------------


def test_with_no_answers_there_is_no_path_view(drawn):
    at = open_page(MAP, study_target="avl_tree")
    assert not at.exception
    assert not at.radio
    assert len(at.get("iframe")) == 1
    assert not any(w in label(drawn, "trees") for w in RESULT_WORDS)


def test_answers_from_another_course_give_no_path_view(drawn):
    at = open_page(MAP, **{**answered_state("avl_tree"), "quiz_course": "ml101"})
    assert not at.exception
    assert not at.radio


# --- My Study Path uses the plan's words ------------------------------------------------


def test_a_course_with_no_levels_uses_the_plan_wording(drawn):
    mastery = {"trees": 0.9, "binary_tree": 0.3}
    at = open_page(MAP, **answered_state("avl_tree", mastery))
    assert not at.exception
    assert at.radio(key="map_view_mode").value == S.MAP_VIEW_PATH
    assert S.PLAN_STATUS_NEXT in label(drawn, "recursion")
    assert S.PLAN_STATUS_LATER in label(drawn, "binary_tree")
    assert S.PLAN_RESULT_THINK_KNOWN in label(drawn, "trees")
    assert S.MAP_GOAL in label(drawn, "avl_tree")
    assert any(m.value == S.PLAN_JUST_START.format(topic="Recursion") for m in at.markdown)
    for concept_id in drawn["nodes"]:
        assert "Known" not in label(drawn, concept_id)
        assert S.PLAN_RESULTS["know_it"] not in label(drawn, concept_id)


def ladder_course(course: Path) -> None:
    shutil.copy(common.EXAMPLES / "ladder_quiz_items.json", course / "quiz_items.json")
    common.st.cache_data.clear()


LADDER_RESULTS = {
    "recursion": "know_it",
    "trees": "know_it",
    "binary_tree": "quick_revision",
    "binary_search_tree": "study_this",
    "avl_tree": "start_here",
}


def ladder_state(results: dict, inferred: tuple = ()) -> dict:
    """Session state as the quick check leaves it, for these results."""
    mastery = {c: RESULT_MASTERY[r] for c, r in results.items()}
    mastery["__ladder__"] = {
        "topics": {
            c: {"result": r, "answers": [], "inferred": c in inferred} for c, r in results.items()
        },
        "asked_for_target": {"avl_tree": 3},
    }
    return answered_state("avl_tree", mastery)


def test_mixed_ladder_results_read_the_same_on_the_map_and_the_plan(course, drawn):
    ladder_course(course)
    state = ladder_state(LADDER_RESULTS)
    at = open_page(MAP, **state)
    assert not at.exception
    words = {c: label(drawn, c) for c in LADDER_RESULTS}
    assert S.PLAN_RESULTS["know_it"] == "✅ Know it"
    assert S.PLAN_RESULTS["know_it"] in words["recursion"]
    assert S.PLAN_RESULTS["know_it"] in words["trees"]
    assert S.PLAN_RESULTS["quick_revision"] in words["binary_tree"]
    assert S.PLAN_RESULTS["study_this"] in words["binary_search_tree"]
    assert S.PLAN_RESULTS["start_here"] in words["avl_tree"]
    for concept_id, text in words.items():
        assert "Known" not in text
        if LADDER_RESULTS[concept_id] != "know_it":
            assert S.PLAN_RESULTS["know_it"] not in text

    plan = open_page(PLAN, **state)
    assert not plan.exception
    lines = [m.value for m in plan.markdown]
    for result in ("quick_revision", "study_this", "start_here"):
        assert S.PLAN_RESULTS[result] in lines


def test_the_start_is_the_first_topic_on_the_plan(course, drawn):
    ladder_course(course)
    state = ladder_state(LADDER_RESULTS)
    at = open_page(MAP, **state)
    assert not at.exception
    assert S.PLAN_STATUS_NEXT in label(drawn, "binary_tree")
    others = [c for c in LADDER_RESULTS if c != "binary_tree"]
    assert not any(S.PLAN_STATUS_NEXT in label(drawn, c) for c in others)
    assert any(m.value == S.PLAN_JUST_START.format(topic="Binary Trees") for m in at.markdown)
    plan = open_page(PLAN, **state)
    assert plan.markdown[0].value == S.PLAN_NEXT_TITLE.format(topic="Binary Trees")


def test_marking_the_first_topic_done_moves_the_start_on_both_pages(course, drawn):
    ladder_course(course)
    state = {**ladder_state(LADDER_RESULTS), "plan_done": {COURSE: ["binary_tree"]}}
    open_page(MAP, **state)
    assert S.PLAN_STATUS_DONE in label(drawn, "binary_tree")
    assert S.PLAN_RESULTS["quick_revision"] in label(drawn, "binary_tree")
    assert S.PLAN_STATUS_NEXT in label(drawn, "binary_search_tree")
    plan = open_page(PLAN, **state)
    assert plan.markdown[0].value == S.PLAN_NEXT_TITLE.format(topic="Binary Search Trees")


def test_an_inferred_topic_says_we_think_not_know_it(course, drawn):
    ladder_course(course)
    open_page(MAP, **ladder_state(LADDER_RESULTS, inferred=("trees",)))
    assert S.PLAN_RESULT_THINK_KNOWN in label(drawn, "trees")
    assert S.PLAN_RESULTS["know_it"] not in label(drawn, "trees")


def test_a_topic_not_reached_reads_not_checked_yet(course, drawn):
    ladder_course(course)
    results = {"recursion": "know_it", "trees": "start_here"}
    open_page(MAP, **ladder_state(results))
    assert S.PLAN_RESULTS["not_checked"] == "❓ Not checked yet"
    assert S.PLAN_RESULTS["not_checked"] in label(drawn, "avl_tree")
    assert S.PLAN_RESULTS["start_here"] in label(drawn, "trees")


def test_without_the_drawing_library_the_path_still_says_each_state(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvis.network", None)
    at = open_page(MAP, **answered_state("avl_tree", {"trees": 0.9}))
    assert not at.exception
    assert not at.get("iframe")
    text = shown(at)
    assert S.MAP_PATH_LINE.format(topic="Recursion", words=S.PLAN_STATUS_NEXT) in text
    assert "**Trees** comes before **Binary Trees**" in text


# --- All Topics -------------------------------------------------------------------------


@pytest.mark.parametrize("view", [S.MAP_VIEW_PATH, S.MAP_VIEW_ALL])
def test_both_views_draw_accepted_links_only(drawn, view):
    edges = json.loads((common.EXAMPLES / "validated_graph.json").read_text())["edges"]
    at = open_page(MAP, **answered_state("avl_tree"), map_view_mode=view)
    assert not at.exception
    pairs = {(source, target) for source, target, _ in drawn["edges"]}
    assert pairs == {(e["source"], e["target"]) for e in edges if e["decision"] == "ACCEPT"}
    assert "graphs" not in drawn["nodes"]


def test_all_topics_shows_no_student_results(drawn):
    open_page(MAP, **answered_state("avl_tree"), map_view_mode=S.MAP_VIEW_ALL)
    for concept_id in drawn["nodes"]:
        assert not any(w in label(drawn, concept_id) for w in RESULT_WORDS)
        assert S.MAP_GOAL not in label(drawn, concept_id)


def build_preview(tmp_path: Path, monkeypatch) -> str:
    name = "my_notes"
    monkeypatch.setattr(jobs, "RAW", tmp_path / "raw")
    monkeypatch.setattr(jobs, "JOBS", tmp_path / ".jobs")
    monkeypatch.setattr(jobs, "OUTPUTS", tmp_path)
    raw = jobs.RAW / name
    raw.mkdir(parents=True)
    (raw / "notes.md").write_text(
        "# Variables\n\nA variable stores a value in memory.\n\n"
        "# Loops\n\nA loop repeats statements while a condition holds.\n\n"
        "# Functions\n\nA function groups statements under a name.\n",
        encoding="utf-8",
    )
    state = jobs.job_dir(name)
    state.mkdir(parents=True)
    assert jobs.fast_demo_run(name, state) == 0
    common.st.cache_data.clear()
    return name


def test_a_preview_keeps_its_label_and_helps_wording_on_the_map(tmp_path, monkeypatch, drawn):
    name = build_preview(tmp_path, monkeypatch)
    at = open_page(MAP, course_id=name)
    assert not at.exception
    assert S.PREVIEW_NOTICE in shown(at)
    assert S.PREVIEW_LABEL.format(course="My notes") in shown(at)
    assert drawn["edges"]
    assert {title for _, _, title in drawn["edges"]} == {S.MAP_HELP_LABEL}


def test_a_preview_path_keeps_its_helps_wording_too(tmp_path, monkeypatch, drawn):
    name = build_preview(tmp_path, monkeypatch)
    graph = common.preview_graph(name)
    target = graph["edges"][-1]["target"]
    state = {**answered_state(target), "quiz_course": name, "course_id": name}
    at = open_page(MAP, **state)
    assert not at.exception
    assert at.radio(key="map_view_mode").value == S.MAP_VIEW_PATH
    assert S.PREVIEW_NOTICE in shown(at)
    assert {title for _, _, title in drawn["edges"]} == {S.MAP_HELP_LABEL}


# --- the study plan's button ------------------------------------------------------------


def test_the_plan_draws_no_map_and_has_one_map_button(drawn):
    at = open_page(PLAN, **answered_state("avl_tree"))
    assert not at.exception
    assert not at.get("iframe")
    assert not drawn["nodes"]
    labelled = [b for b in at.button if b.label == S.PLAN_SEE_ON_MAP]
    assert len(labelled) == 1 and labelled[0].key == "plan_to_map"
    assert not [b for b in at.button if "Topic Map" in b.label]


def test_the_plan_with_everything_known_also_has_the_button(drawn):
    mastery = dict.fromkeys(["recursion", "trees", "binary_tree", "binary_search_tree"], 0.95)
    at = open_page(PLAN, **answered_state("avl_tree", {**mastery, "avl_tree": 0.95}))
    assert not at.exception
    assert not at.get("iframe")
    assert at.button(key="plan_to_map").label == S.PLAN_SEE_ON_MAP


def test_the_button_opens_the_topic_map_on_my_study_path(course, drawn):
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    at.button(key="home_quiz").click().run()
    at = at.button(key="topic_trees").click().run()
    item = next(
        q
        for q in json.loads((course / "quiz_items.json").read_text())["items"]
        if q["concept_id"] == "trees"
    )
    wrong = next(i for i, o in enumerate(item["options"]) if o != item["answer"])
    at = at.button(key=f"answer_{item['id']}_{wrong}").click().run()
    at = at.button(key="quiz_continue").click().run()  # a wrong answer waits on this screen
    assert at.title[0].value == S.PLAN_TITLE and not at.exception
    at = at.button(key="plan_to_map").click().run()
    assert not at.exception
    assert at.title[0].value == S.MAP_TITLE
    assert at.radio(key="map_view_mode").value == S.MAP_VIEW_PATH
    assert len(at.get("iframe")) == 1


# --- the look ---------------------------------------------------------------------------


def test_the_picture_sits_on_the_lavender_page_with_no_white_behind_it():
    pytest.importorskip("pyvis")  # not installed in CI
    at = open_page(MAP)
    assert not at.exception
    html = at.get("iframe")[0].proto.srcdoc
    assert "background-color: #F4F2FB" in html
    assert "background-color: #ffffff" not in html.lower()
    assert "html, body, .card { background: #F4F2FB !important; }" in html


# --- job status -------------------------------------------------------------------------


def test_a_locked_status_file_is_retried(tmp_path, monkeypatch):
    real = Path.replace
    calls = []

    def locked_twice(self, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError("in use")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", locked_twice)
    jobs._write_state(tmp_path, {"state": "running"})
    assert len(calls) == 3
    assert json.loads((tmp_path / "job.json").read_text())["state"] == "running"
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failed_status_write_is_logged_not_hidden(tmp_path, monkeypatch, caplog):
    def locked(self, target):
        raise PermissionError("in use")

    real_write = Path.write_text

    def write(self, *args, **kwargs):
        if self.name == "job.json":
            raise PermissionError("no room")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(Path, "write_text", write)
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)
    with caplog.at_level(logging.ERROR, logger=jobs.logger.name):
        jobs._write_state(tmp_path, {"state": "running"})
    assert "Could not write the job status" in caplog.text and "no room" in caplog.text
    assert "could not write the job status: no room" in (tmp_path / "pipeline.log").read_text()


def test_status_reads_the_result_written_just_after_the_runner_exits(tmp_path, monkeypatch):
    folder = jobs.job_dir("c1", tmp_path)
    folder.mkdir(parents=True)
    jobs._write_state(folder, {"state": "running", "pid": 999999, "created_at": 0})
    monkeypatch.setattr(jobs, "_alive", lambda pid: False)

    def finish_during_sleep(_):
        jobs._write_state(folder, {"state": "succeeded", "pid": 999999, "returncode": 0})

    monkeypatch.setattr(jobs.time, "sleep", finish_during_sleep)
    status = jobs.read_status("c1", tmp_path)
    assert status["state"] == "succeeded" and status["error"] is None


def test_status_still_fails_when_the_runner_died_without_a_result(tmp_path, monkeypatch):
    folder = jobs.job_dir("c1", tmp_path)
    folder.mkdir(parents=True)
    jobs._write_state(folder, {"state": "running", "pid": 999999, "created_at": 0})
    monkeypatch.setattr(jobs, "_alive", lambda pid: False)
    monkeypatch.setattr(jobs.time, "sleep", lambda _: None)
    status = jobs.read_status("c1", tmp_path)
    assert status["state"] == "failed"
    assert "stopped before" in status["error"]
