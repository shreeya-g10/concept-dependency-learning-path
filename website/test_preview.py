"""Quick Preview: no AI, no invented results, clearly labelled, and never a validated course."""

import ast
import json
import re
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402
import jobs  # noqa: E402
import strings as S  # noqa: E402

from cdlp.root_cause import api as root_cause_api  # noqa: E402
from cdlp.shared.validate import check_file  # noqa: E402

COURSE = "my_notes"
INVENTED_KEYS = {"decision", "confidence", "checks", "necessity_gap", "discovery_confidence"}
PROGRAMMING_NOTES = (
    "# Variables\n\nC programming with a compiler stores data in a variable.\n\n"
    "# Loops\n\nA loop repeats statements until the condition is false.\n\n"
    "# Pointers\n\nA pointer holds an address in C programming.\n\n"
    "# Sorting Plans\n\nAn algorithm may sort a list of numbers.\n"
)
BIOLOGY_NOTES = (
    "# Cell Function\n\nThe cell keeps itself alive by taking in food from outside.\n\n"
    "# Tree Anatomy\n\nA tree moves water from the roots up to its leaves.\n\n"
    "# String Theory Of Vines\n\nVines climb walls by growing thin threads around them.\n\n"
    "# Loops In Rivers\n\nA river bends as water wears away the outer bank.\n"
)


@pytest.fixture(autouse=True)
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RAW", tmp_path / "raw")
    monkeypatch.setattr(jobs, "JOBS", tmp_path / "outputs" / ".jobs")
    monkeypatch.setattr(jobs, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(common, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (True, "reachable (test)"))
    monkeypatch.delenv("CDLP_MAX_CHUNKS", raising=False)
    common.st.cache_data.clear()
    yield tmp_path / "outputs"
    common.st.cache_data.clear()


def build(notes: str = PROGRAMMING_NOTES, course: str = COURSE) -> tuple[int, Path]:
    raw = jobs.RAW / course
    raw.mkdir(parents=True)
    (raw / "notes.md").write_text(notes, encoding="utf-8")
    state = jobs.job_dir(course)
    state.mkdir(parents=True)
    return jobs.fast_demo_run(course, state), jobs.OUTPUTS / jobs.PREVIEW_FOLDER / course


def page(name: str, course: str = COURSE) -> AppTest:
    at = AppTest.from_file(str(SITE / "pages" / name), default_timeout=60)
    at.session_state["course_id"] = course
    return at.run()


def shown(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.error] + [e.value for e in at.success]
    return " ".join(parts + [i.value for i in at.info] + [w.value for w in at.warning])


def keys_in(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_in(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_in(v)}
    return set()


# --- what a preview writes ---------------------------------------------------------------


def test_a_preview_writes_no_decision_confidence_or_grade():
    code, folder = build()
    assert code == 0
    assert {p.name for p in folder.iterdir()} == {
        "chunks.jsonl",
        "concepts.json",
        "preview.json",
        "quiz_items.json",
    }
    for name in ("concepts.json", "preview.json", "quiz_items.json"):
        path = folder / name
        assert not keys_in(json.loads(path.read_text(encoding="utf-8"))) & INVENTED_KEYS
        assert check_file(path) == []
    text = "".join(p.read_text(encoding="utf-8") for p in folder.iterdir())
    assert not re.search(r"ACCEPT|\b0\.95\b|\b0\.7\b|\"strong\"", text)


def test_the_contract_refuses_a_grade_on_a_preview(tmp_path):
    good = json.loads((Path(common.EXAMPLES) / "preview.json").read_text(encoding="utf-8"))
    for extra in ({"decision": "ACCEPT"}, {"confidence": 0.95}, {"necessity_gap": 0.7}):
        bad = json.loads(json.dumps(good))
        bad["links"][0].update(extra)
        path = tmp_path / "preview.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert check_file(path), extra
    good["ai_used"] = True
    path.write_text(json.dumps(good), encoding="utf-8")
    assert check_file(path)


def test_the_log_says_only_what_really_happened():
    build()
    log = (jobs.job_dir(COURSE) / "pipeline.log").read_text(encoding="utf-8")
    assert "no AI was used" in log and "4 possible topics" in log and "3 links" in log
    assert "==>" not in log and "contract" not in log and "cdlp." not in log
    assert jobs.read_status(COURSE)["state"] == "succeeded"


def test_no_text_fails_and_never_copies_another_courses_files(site):
    site.mkdir()
    (site / "concepts.json").write_text('{"from": "another course"}', encoding="utf-8")
    jobs.RAW.mkdir()
    state = jobs.job_dir(COURSE)
    state.mkdir(parents=True)
    assert jobs.fast_demo_run(COURSE, state) == 1
    assert jobs.read_status(COURSE)["state"] == "failed"
    assert not list((site / jobs.PREVIEW_FOLDER / COURSE).iterdir())
    assert not (site / COURSE).exists()
    assert not common.is_preview(COURSE)


def test_a_cut_preview_says_so(monkeypatch):
    monkeypatch.setenv("CDLP_MAX_CHUNKS", "2")
    _, folder = build()
    preview = json.loads((folder / "preview.json").read_text(encoding="utf-8"))
    assert preview["chunks_truncated"]["kept"] == 2
    assert "Read only 2 of" in (jobs.job_dir(COURSE) / "pipeline.log").read_text(encoding="utf-8")


# --- never a validated course ------------------------------------------------------------


def test_a_preview_never_counts_as_a_validated_course(site):
    _, folder = build()
    assert common.is_preview(COURSE) and not common.has_real_run(COURSE)
    assert COURSE not in common.list_courses(site)
    assert COURSE in common.list_previews()
    # What a results script finds when it looks for finished runs.
    assert not list(site.glob("*/validated_graph.json"))
    assert not (site / COURSE).exists()
    assert not (folder / "validated_graph.json").exists()


def test_preview_files_never_fall_back_to_examples_or_other_courses(site):
    build()
    (site / "relationships.json").write_text("{}", encoding="utf-8")
    assert common.resolve_path("relationships.json", COURSE).parent == common.preview_dir(COURSE)
    assert not common.using_examples("concepts.json", COURSE)


def test_a_finished_real_run_wins_and_is_left_alone(site):
    _, folder = build()
    real = site / COURSE
    real.mkdir()
    (real / "concepts.json").write_text(
        (Path(common.EXAMPLES) / "concepts.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    graph = (Path(common.EXAMPLES) / "validated_graph.json").read_text(encoding="utf-8")
    (real / "validated_graph.json").write_text(graph, encoding="utf-8")
    assert not common.is_preview(COURSE)
    assert common.has_real_run(COURSE)
    assert COURSE in common.list_courses(site) and COURSE not in common.list_previews()
    assert common.resolve_path("concepts.json", COURSE).parent == real
    assert common.answers_path(COURSE).parent == real
    assert folder.is_dir()
    assert (real / "validated_graph.json").read_text(encoding="utf-8") == graph


def test_preview_answers_stay_away_from_the_real_answer_log(site):
    _, folder = build()
    row = {"student_id": "s", "item_id": "q", "concept_id": "loops", "answer": "a", "correct": True}
    common.log_answer(COURSE, row)
    assert (folder / "student_answers.json").is_file()
    assert not (site / COURSE / "student_answers.json").exists()


def test_the_preview_graph_is_never_written_and_reads_as_soft():
    _, folder = build()
    graph = common.load("validated_graph.json", COURSE)
    assert graph["edges"] and all(e["strength"] == "soft" for e in graph["edges"])
    assert not (folder / "validated_graph.json").exists()
    assert not keys_in(graph) & (INVENTED_KEYS - {"decision"})


# --- nothing in website/ writes a decision ------------------------------------------------


def site_sources() -> list[Path]:
    return [
        p
        for p in sorted(SITE.rglob("*.py"))
        if not p.name.startswith("test_") and "__pycache__" not in p.parts
    ]


def test_nothing_in_website_writes_a_decision_except_through_the_real_pipeline():
    """The only literal is the in-memory preview_graph. Teacher decisions go to apply_review."""
    found = set()
    for path in site_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value in INVENTED_KEYS:
                        found.add((path.name, key.value))
    assert found == {("common.py", "decision")}

    jobs_source = (SITE / "jobs.py").read_text(encoding="utf-8")
    assert "validated_graph.json" not in jobs_source
    assert "relationships.json" not in jobs_source

    writes = re.compile(r"write_text|write_json|json\.dump\b|open\([^)]*[\"']w")
    for path in site_sources():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "validated_graph" in line:
                assert not writes.search(line), f"{path.name}: {line}"


# --- questions ---------------------------------------------------------------------------


def quiz(folder: Path) -> list[dict]:
    return json.loads((folder / "quiz_items.json").read_text(encoding="utf-8"))["items"]


def test_every_question_is_marked_general_and_names_its_topic():
    _, folder = build()
    items = quiz(folder)
    assert items and all(q["origin"] == "general_practice" for q in items)
    for q in items:
        text = " ".join([q["question"], *q["options"]])
        assert "{" not in text and "}" not in text and q["answer"] in q["options"]
    fallback = [q for q in items if q["concept_id"] == "sorting_plans"]
    assert "primary role of Sorting Plans in this subject?" in fallback[0]["question"]
    assert "how does Sorting Plans support subsequent topics?" in fallback[1]["question"]


def test_no_words_are_joined_in_the_question_lists():
    source = (SITE / "jobs.py").read_text(encoding="utf-8")
    joined = """otherconcepts assignmentoperator arithmeticexpressions tofalse neverexecutes
        Cbytecode correctresults pointnumbers beforedeclaration usedwith thepointer underlyingdata
        avariable acrossmemory childpointers ofthe procedurallanguages arithmeticoperations
        siblingnodes""".split()
    for word in joined:
        assert word not in source
    # Read as text, not tokens: Python 3.11 and 3.12 tokenize f-strings differently.
    block = source[source.index("    quiz_categories = [") : source.index("def fast_demo_run")]
    assert not re.findall(r'[^ ]"\n\s+f?"[^ ]', block)


def test_c_questions_appear_only_when_the_topic_really_matches():
    _, folder = build()
    by_topic = {}
    for q in quiz(folder):
        by_topic.setdefault(q["concept_id"], []).append(q["question"])
    assert "What is a variable in programming?" in by_topic["variables"]
    assert any("pointer" in q for q in by_topic["pointers"])
    assert any("loop" in q for q in by_topic["loops"])


def test_notes_on_another_subject_get_no_c_questions():
    _, folder = build(BIOLOGY_NOTES)
    text = " ".join(q["question"] for q in quiz(folder))
    assert not re.search(r"\bBST\b|struct|recursion|programming|null terminator|loop control", text)
    assert "primary role of Cell Function" in text


@pytest.mark.parametrize(
    "topic, keywords, expected",
    [
        ("Pointers", ["pointer"], True),
        ("Information Theory", ["for", "io"], False),
        ("Window Frames", ["do"], False),
        ("Linked Lists", ["list"], False),
        ("Stage Lighting", ["tag"], False),
        ("Street Trees", ["tree"], True),
    ],
)
def test_topic_matches_whole_words_only(topic, keywords, expected):
    assert jobs.topic_matches(topic, keywords) is expected


# --- labels ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "0_Start_here.py",
        "2_See_your_topics.py",
        "3_Quick_check.py",
        "4_My_study_plan.py",
        "5_Topic_map.py",
    ],
)
def test_the_preview_notice_is_on_every_student_page(name):
    build()
    at = page(name)
    assert not at.exception
    assert S.PREVIEW_NOTICE in shown(at)


def test_the_notice_is_word_for_word_what_was_asked():
    assert S.PREVIEW_NOTICE == (
        "Preview only. No AI was used. Links follow the order of headings, "
        "and questions are not from your AI check."
    )
    assert S.QUIZ_GENERAL == "General practice question, not from your notes"


def test_the_subject_name_is_marked_wherever_it_shows():
    build()
    assert common.course_title(COURSE) == "My notes (preview, no AI)"
    assert common.course_label(COURSE) == "My notes"  # the upload page turns this back into an id
    at = page("2_See_your_topics.py")
    assert "My notes (preview, no AI)" in shown(at)
    picker = page("0_Start_here.py").selectbox[0]
    assert "My notes (preview, no AI)" in picker.options


@pytest.mark.parametrize("name", ["teacher_AI_checks_and_review.py", "teacher_AI_suggestions.py"])
def test_teacher_pages_show_not_checked_and_never_a_grade(name):
    build()
    at = page(name)
    assert not at.exception
    text = shown(at)
    assert "Not checked by the AI" in text and S.PREVIEW_NOTICE in text
    assert not at.metric and not at.button and not at.dataframe
    assert not re.search(r"Accepted|Rejected|🟢|Decisions|0\.95", text)


def test_preview_questions_are_labelled_and_a_wrong_answer_asks_no_ai(monkeypatch):
    build()
    calls = []
    monkeypatch.setattr(root_cause_api, "trace", lambda *a, **k: calls.append(a) or {})
    at = page("3_Quick_check.py")
    at.button(key="topic_loops").click().run()
    assert S.QUIZ_GENERAL in shown(at)
    question = next(m.value for m in at.markdown if m.value.startswith("### "))[4:]
    items = common.load("quiz_items.json", COURSE)["items"]
    item = next(q for q in items if q["question"] == question)
    wrong = next(i for i, o in enumerate(item["options"]) if o != item["answer"])
    at.button(key=f"answer_{item['id']}_{wrong}").click().run()
    assert not at.exception
    assert not calls
    assert S.QUIZ_THE_ANSWER.split("{")[0] in shown(at)


# --- the add page ------------------------------------------------------------------------


def add_page() -> AppTest:
    at = AppTest.from_file(str(SITE / "pages" / "1_Add_your_notes.py"), default_timeout=60)
    at.session_state["upload_course"] = COURSE
    return at.run()


def with_upload(notes: str = PROGRAMMING_NOTES) -> None:
    raw = jobs.RAW / COURSE
    raw.mkdir(parents=True)
    (raw / "notes.md").write_text(notes, encoding="utf-8")


def test_quick_preview_is_off_by_default_and_named_honestly():
    with_upload()
    at = add_page()
    box = at.checkbox(key="fast_mode_toggle")
    assert box.value is False
    assert box.label == S.ADD_FAST_MODE and "Quick Preview" in box.label
    assert "recommended" not in box.label.lower() and "Fast Demo" not in box.label


def test_the_notice_shows_only_when_the_box_is_ticked():
    """Unticked, the AI does read the notes, so "No AI was used" would be untrue."""
    with_upload()
    at = add_page()
    assert S.PREVIEW_NOTICE not in shown(at)
    at.checkbox(key="fast_mode_toggle").check().run()
    assert S.PREVIEW_NOTICE in shown(at)
    at.checkbox(key="fast_mode_toggle").uncheck().run()
    assert S.PREVIEW_NOTICE not in shown(at)


def test_the_normal_button_starts_the_real_pipeline(monkeypatch):
    with_upload()
    started = []
    monkeypatch.setattr(jobs, "start_job", lambda c, **k: started.append((c, k)))
    at = add_page()
    next(b for b in at.button if b.label == S.ADD_BUILD).click().run()
    assert started == [(COURSE, {"fast_demo": False})]
    command = jobs.pipeline_command(COURSE, fast_demo=False)
    assert any(part.endswith("pipeline.py") for part in command)
    assert "--demo-subset" not in command


def test_a_ticked_preview_starts_the_preview_and_works_with_the_ai_off(monkeypatch):
    with_upload()
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (False, "off (test)"))
    started = []
    monkeypatch.setattr(jobs, "start_job", lambda c, **k: started.append((c, k)))
    at = add_page()
    assert next(b for b in at.button if b.label == S.ADD_BUILD).disabled
    at.checkbox(key="fast_mode_toggle").check().run()
    assert S.ADD_FAST_SECONDS in shown(at)
    button = next(b for b in at.button if b.label == S.ADD_BUILD)
    assert not button.disabled
    button.click().run()
    assert started == [(COURSE, {"fast_demo": True})]


def test_no_preview_beside_a_checked_subject(site):
    with_upload()
    real = site / COURSE
    real.mkdir(parents=True)
    for name in common.COURSE_FILES:
        (real / name).write_text(
            (Path(common.EXAMPLES) / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    at = add_page()
    assert at.checkbox(key="fast_mode_toggle").disabled
    assert S.PREVIEW_NOT_NEEDED in shown(at)


def test_a_finished_preview_says_it_is_not_checked():
    build()
    at = add_page()
    # Streamlit shows a leading emoji as the alert's icon, not as part of its text.
    text = shown(at)
    assert S.PREVIEW_DONE.removeprefix("✅ ") in text
    assert S.ADD_DONE.removeprefix("✅ ") not in text


def test_start_page_makes_no_fast_demo_promise():
    build()
    assert "Fast Demo" not in shown(page("0_Start_here.py"))
    assert "Fast Demo" not in (SITE / "strings.py").read_text(encoding="utf-8")
