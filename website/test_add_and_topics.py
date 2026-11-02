"""Step 1 (Add your notes) and step 2 (See your topics). No LLM; jobs are never started."""

import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402
import jobs  # noqa: E402
import strings as S  # noqa: E402
import ui  # noqa: E402

ADD = str(SITE / ui.PAGES["add"].path)
TOPICS = str(SITE / ui.PAGES["topics"].path)


@pytest.fixture(autouse=True)
def _fresh_cache():
    common.st.cache_data.clear()
    yield
    common.st.cache_data.clear()


def body_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [e.value for e in at.error] + [e.value for e in at.success]
    return " ".join(parts + [i.value for i in at.info] + [w.value for w in at.warning])


# --- step 1 ----------------------------------------------------------------------------


@pytest.fixture
def add_page(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RAW", tmp_path / "raw")
    monkeypatch.setattr(jobs, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(common, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (True, "reachable (test)"))

    def open_page(course: str | None = None) -> AppTest:
        at = AppTest.from_file(ADD, default_timeout=60)
        if course:
            at.session_state["upload_course"] = course
        return at.run()

    return open_page


def notes(tmp_path, course="c1", text="Trees have nodes. " * 20) -> Path:
    folder = tmp_path / "raw" / course
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text(text)
    return folder


def write_job(tmp_path, state: dict, log: str = "", course="c1") -> None:
    folder = tmp_path / "jobs" / course
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps(state))
    (folder / "pipeline.log").write_text(log)


def test_page_says_which_files_work_before_any_name_is_typed(add_page):
    at = add_page()
    assert not at.exception
    assert S.ADD_FILE_TYPES in [m.value for m in at.markdown]
    for kind in ("PDF", ".pptx", ".docx", ".txt", ".md"):
        assert kind in S.ADD_FILE_TYPES
    assert any(S.ADD_NAME_EMPTY in i.value for i in at.info)


def test_typing_a_name_makes_a_hidden_id(add_page, tmp_path):
    notes(tmp_path, "biology_notes")
    at = add_page()
    at.text_input[0].input("Biology notes").run()
    assert not at.exception
    assert at.session_state["upload_course"] == "biology_notes"
    assert "biology_notes" not in body_text(at)
    assert not at.button(key="build").disabled


def test_uploads_are_saved_without_a_separate_save_button(add_page, tmp_path):
    at = add_page("c1")
    at.file_uploader[0].set_value(("My Notes.txt", b"Trees etc", "text/plain")).run()
    assert not at.exception
    assert (tmp_path / "raw" / "c1" / "My_Notes.txt").read_bytes() == b"Trees etc"
    assert "My_Notes.txt" in body_text(at)
    assert at.button(key="build").label == S.ADD_BUILD
    assert "Save" not in " ".join(b.label for b in at.button)


def test_a_bad_upload_says_what_to_do(add_page, monkeypatch):
    upload = SimpleNamespace(name="old.ppt", size=1, getvalue=lambda: b"x")
    monkeypatch.setattr(common.st, "file_uploader", lambda *a, **k: [upload])
    at = add_page("c1")
    assert not at.exception
    assert any(S.ADD_SAVE_FAILED in e.value and S.WHAT_TO_DO in e.value for e in at.error)


def test_a_built_in_course_cannot_be_replaced_by_typing_its_id(add_page):
    at = add_page()
    at.text_input[0].input("DS101").run()
    assert not at.exception
    assert any(S.ADD_NAME_TAKEN in e.value for e in at.error)
    assert "upload_course" not in at.session_state


def test_time_estimate_appears_before_starting(add_page, tmp_path):
    notes(tmp_path)
    assert "rough guess" in body_text(add_page("c1"))


@pytest.mark.parametrize(
    ("minutes", "words"),
    [
        ((0, 0), "1 to 2 minutes"),
        ((3, 8), "3 to 8 minutes"),
        ((90, 400), "2 to 7 hours"),
    ],
)
def test_time_estimate_reads_well_at_any_size(add_page, tmp_path, monkeypatch, minutes, words):
    notes(tmp_path)
    monkeypatch.setattr(jobs, "estimate", lambda _: {"words": 9, "total_minutes": minutes})
    assert words in body_text(add_page("c1"))


def test_files_without_words_cannot_be_started(add_page, tmp_path):
    notes(tmp_path, text="   ")
    at = add_page("c1")
    assert any(S.ADD_NO_TEXT in e.value and S.WHAT_TO_DO in e.value for e in at.error)
    assert at.button(key="build").disabled


def test_no_ai_says_so_and_offers_the_sample_course(add_page, monkeypatch):
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (False, "No LLM (test)"))
    at = add_page()
    assert any(S.ADD_AI_OFF in e.value for e in at.error)
    assert at.button(key="sample").label == S.ADD_SAMPLE
    assert at.button(key="sample").proto.type == "primary"


def test_sample_button_opens_the_sample_course(add_page, monkeypatch):
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (False, "No LLM (test)"))
    home = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    home.switch_page(ui.PAGES["add"].path).run()
    home.button(key="sample").click().run()
    assert not home.exception
    assert home.title[0].value == S.TOPICS_TITLE
    assert home.session_state["course_id"] == "ds101"


def test_ai_on_hides_the_sample_offer(add_page):
    at = add_page()
    assert not at.error
    assert "sample" not in [b.key for b in at.button]


def test_progress_is_in_words_and_the_start_button_goes_away(add_page, tmp_path):
    notes(tmp_path)
    log = "==> cdlp.extraction\n==> cdlp.discovery\n==> cdlp.validation\n"
    write_job(tmp_path, {"state": "running", "pid": os.getpid()}, log)
    at = add_page("c1")
    text = body_text(at)
    assert not at.exception
    assert "⏳ Checking links…" in text and "✅ Reading your file and finding topics" in text
    assert "build" not in [b.key for b in at.button]
    for technical in ("cdlp", "pipeline", "Validation agent", "Waiting"):
        assert technical not in text


def test_job_just_started_says_it_is_reading_the_file(add_page, tmp_path):
    notes(tmp_path)
    write_job(tmp_path, {"state": "running", "pid": os.getpid()})
    assert "⏳ Reading your file…" in body_text(add_page("c1"))


def test_when_done_the_only_main_button_is_the_next_step(add_page, tmp_path):
    notes(tmp_path)
    write_job(tmp_path, {"state": "succeeded", "returncode": 0}, "==> cdlp.extraction\n")
    at = add_page("c1")
    assert any("We finished reading your notes" in s.value for s in at.success)
    assert at.session_state["course_id"] == "c1"
    primary = [b.label for b in at.button if b.proto.type == "primary"]
    assert primary == [S.ADD_NEXT]
    assert at.button(key="build").label == S.ADD_BUILD_AGAIN


def test_failure_says_what_to_do_and_can_be_retried(add_page, tmp_path):
    notes(tmp_path)
    write_job(tmp_path, {"state": "failed", "returncode": 1}, "==> cdlp.extraction\nboom\n")
    at = add_page("c1")
    assert any(S.ADD_FAILED in e.value and S.WHAT_TO_DO in e.value for e in at.error)
    assert any("boom" in c.value for c in at.code)  # folded away, for the teacher
    assert not at.button(key="build").disabled


# --- step 1: removing a file -------------------------------------------------------------


def test_each_file_has_a_remove_button_that_removes_only_that_file(add_page, tmp_path):
    folder = notes(tmp_path)
    (folder / "other.txt").write_text("Queues wait in line.")
    at = add_page("c1")
    assert at.button(key="remove_notes.txt").label == S.ADD_REMOVE
    at.button(key="remove_notes.txt").click().run()
    assert not at.exception
    assert [p.name for p in folder.iterdir()] == ["other.txt"]
    assert "remove_notes.txt" not in [b.key for b in at.button]
    assert any("Removed: notes.txt" in s.value for s in at.success)
    assert not at.button(key="build").disabled  # the other file can still be read


def test_removing_the_last_file_blocks_reading(add_page, tmp_path):
    notes(tmp_path)
    at = add_page("c1")
    at.button(key="remove_notes.txt").click().run()
    assert any(S.ADD_NO_FILES in i.value for i in at.info)
    assert "build" not in [b.key for b in at.button]


def test_a_removed_file_does_not_come_back_with_the_next_upload(add_page, tmp_path):
    at = add_page("c1")
    at.file_uploader[0].set_value(("wrong.txt", b"Wrong file", "text/plain")).run()
    at.button(key="remove_wrong.txt").click().run()
    folder = tmp_path / "raw" / "c1"
    assert not (folder / "wrong.txt").exists()
    at.file_uploader[0].set_value(("right.txt", b"Right file", "text/plain")).run()
    assert not at.exception
    assert [p.name for p in folder.iterdir()] == ["right.txt"]


def test_the_same_file_can_be_added_again_after_removing_it(add_page, tmp_path):
    at = add_page("c1")
    at.file_uploader[0].set_value(("notes.txt", b"Trees", "text/plain")).run()
    at.button(key="remove_notes.txt").click().run()
    at.file_uploader[0].set_value(("notes.txt", b"Trees", "text/plain")).run()
    assert (tmp_path / "raw" / "c1" / "notes.txt").read_bytes() == b"Trees"


def test_no_remove_button_while_reading(add_page, tmp_path):
    notes(tmp_path)
    write_job(tmp_path, {"state": "running", "pid": os.getpid()})
    assert "remove_notes.txt" not in [b.key for b in add_page("c1").button]


def test_a_failed_remove_says_what_to_do_and_keeps_the_file(add_page, tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise ValueError("refused (test)")

    folder = notes(tmp_path)
    monkeypatch.setattr(jobs, "remove_upload", refuse)
    at = add_page("c1")
    at.button(key="remove_notes.txt").click().run()
    assert not at.exception
    assert any(S.ADD_REMOVE_FAILED in e.value and S.WHAT_TO_DO in e.value for e in at.error)
    assert (folder / "notes.txt").exists()


def test_built_in_course_list_matches_the_display_names():
    assert jobs.BUILT_IN_COURSES == set(common.COURSE_NAMES)


@pytest.mark.parametrize("course", sorted(jobs.BUILT_IN_COURSES))
def test_remove_never_touches_a_built_in_course(tmp_path, course):
    (tmp_path / "raw" / course).mkdir(parents=True)
    keep = tmp_path / "raw" / course / "chapter.pdf"
    keep.write_bytes(b"x")
    with pytest.raises(ValueError, match="built-in"):
        jobs.remove_upload(course, "chapter.pdf", tmp_path / "raw", tmp_path / "jobs")
    assert keep.exists()


@pytest.mark.parametrize(
    "name",
    [
        "../outside.txt",
        "../c2/notes.txt",
        "..\\outside.txt",
        "sub/notes.txt",
        "..",
        ".hidden.txt",
        "",
        "script.py",
        "README.md",
    ],
)
def test_remove_refuses_anything_but_a_plain_uploaded_file(tmp_path, name):
    raw = tmp_path / "raw"
    (raw / "c1" / "sub").mkdir(parents=True)
    (raw / "c2").mkdir()
    files = [
        tmp_path / "raw" / "outside.txt",
        raw / "c2" / "notes.txt",
        raw / "c1" / "sub" / "notes.txt",
        raw / "c1" / ".hidden.txt",
        raw / "c1" / "script.py",
        raw / "c1" / "README.md",
    ]
    for file in files:
        file.write_text("keep")
    with pytest.raises(ValueError):
        jobs.remove_upload("c1", name, raw, tmp_path / "jobs")
    assert all(file.exists() for file in files)


def test_remove_refuses_a_bad_course_id(tmp_path):
    victim = tmp_path / "notes.txt"
    victim.write_text("keep")
    with pytest.raises(ValueError):
        jobs.remove_upload("../..", "notes.txt", tmp_path / "raw" / "a", tmp_path / "jobs")
    assert victim.exists()


def test_remove_does_not_follow_a_link_out_of_the_folder(tmp_path):
    raw = tmp_path / "raw"
    (raw / "c1").mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("keep")
    (raw / "c1" / "link.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="link"):
        jobs.remove_upload("c1", "link.txt", raw, tmp_path / "jobs")
    assert outside.exists() and (raw / "c1" / "link.txt").is_symlink()


def test_remove_does_not_follow_a_linked_course_folder(tmp_path):
    raw = tmp_path / "raw"
    (raw / "real").mkdir(parents=True)
    keep = raw / "real" / "notes.txt"
    keep.write_text("keep")
    (raw / "c1").symlink_to(raw / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="link"):
        jobs.remove_upload("c1", "notes.txt", raw, tmp_path / "jobs")
    assert keep.exists()


def test_remove_refuses_a_folder_with_a_file_name(tmp_path):
    folder = tmp_path / "raw" / "c1" / "odd.txt"
    folder.mkdir(parents=True)
    with pytest.raises(ValueError):
        jobs.remove_upload("c1", "odd.txt", tmp_path / "raw", tmp_path / "jobs")
    assert folder.is_dir()


def test_remove_waits_for_a_running_job(tmp_path):
    keep = tmp_path / "raw" / "c1" / "notes.txt"
    keep.parent.mkdir(parents=True)
    keep.write_text("keep")
    state = tmp_path / "jobs" / "c1"
    state.mkdir(parents=True)
    (state / "job.json").write_text(json.dumps({"state": "running", "pid": os.getpid()}))
    with pytest.raises(RuntimeError, match="running"):
        jobs.remove_upload("c1", "notes.txt", tmp_path / "raw", tmp_path / "jobs")
    assert keep.exists()


def test_removing_a_file_twice_is_harmless(tmp_path):
    file = tmp_path / "raw" / "c1" / "notes.txt"
    file.parent.mkdir(parents=True)
    file.write_text("x")
    assert jobs.remove_upload("c1", "notes.txt", tmp_path / "raw", tmp_path / "jobs") is True
    assert jobs.remove_upload("c1", "notes.txt", tmp_path / "raw", tmp_path / "jobs") is False


# --- step 2 ----------------------------------------------------------------------------


def concept(i: int, uses: int = 1, doc: str = "a.pdf", **extra) -> dict:
    sources = [{"doc": doc, "page": p + 1, "chunk_id": f"t{i}_{p}"} for p in range(uses)]
    return {
        "id": f"t{i}",
        "name": f"Topic {i:02d}",
        "aliases": [],
        "description": f"Meaning {i}.",
        "sources": sources,
        **extra,
    }


@pytest.fixture
def topics_page(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)

    def open_page(concepts: list[dict]) -> AppTest:
        course = tmp_path / "ds101"
        course.mkdir(exist_ok=True)
        (course / "concepts.json").write_text(json.dumps({"concepts": concepts}))
        chunks = [
            {"chunk_id": s["chunk_id"], "text": f"Passage {s['chunk_id']}"}
            for c in concepts
            for s in c["sources"]
        ]
        (course / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks))
        return AppTest.from_file(TOPICS, default_timeout=60).run()

    return open_page


def card_names(at: AppTest) -> list[str]:
    return [m.value.strip("*") for m in at.markdown if m.value.startswith("**Topic ")]


def test_says_how_many_topics_were_found(topics_page):
    at = topics_page([concept(i) for i in range(3)])
    assert not at.exception
    assert "### We found 3 topics in your notes" in [m.value for m in at.markdown]


def test_one_topic_is_not_called_topics(topics_page):
    at = topics_page([concept(1)])
    assert "### We found 1 topic in your notes" in [m.value for m in at.markdown]


def test_sample_data_is_not_called_your_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    at = AppTest.from_file(TOPICS, default_timeout=60).run()
    text = " ".join(m.value for m in at.markdown)
    assert "This sample has" in text and "We found" not in text


def test_most_used_topics_come_first(topics_page):
    at = topics_page([concept(1, uses=1), concept(2, uses=5), concept(3, uses=2)])
    assert card_names(at) == ["Topic 02", "Topic 03", "Topic 01"]


def test_a_repeated_page_counts_once(topics_page):
    twice = concept(1, uses=1)
    twice["sources"] = [twice["sources"][0] | {"chunk_id": c} for c in ("x", "y", "z")]
    at = topics_page([twice, concept(2, uses=2)])
    assert card_names(at) == ["Topic 02", "Topic 01"]


def test_long_lists_start_short_and_can_grow(topics_page):
    at = topics_page([concept(i) for i in range(23)])
    assert len(card_names(at)) == 10
    assert "**Showing 10 of 23 topics**" in [m.value for m in at.markdown]
    at.button(key="topics_more").click().run()
    assert len(card_names(at)) == 20
    assert at.button(key="topics_more").label == "Show 3 more topics"
    at.button(key="topics_more").click().run()
    assert len(card_names(at)) == 23
    assert "topics_more" not in [b.key for b in at.button]


def test_search_finds_topics_outside_the_first_ten(topics_page):
    at = topics_page([concept(i) for i in range(23)])
    at.text_input[0].input("topic 22").run()
    assert card_names(at) == ["Topic 22"]


def test_search_matches_aliases_and_says_when_nothing_matches(topics_page):
    at = topics_page([concept(1, aliases=["BST"]), concept(2)])
    at.text_input[0].input("bst").run()
    assert card_names(at) == ["Topic 01"]
    at.text_input[0].input("nothing like this").run()
    assert any(S.TOPICS_NO_MATCH in i.value for i in at.info)


def test_a_new_search_starts_from_the_top_of_its_list(topics_page):
    at = topics_page([concept(i) for i in range(23)])
    at.button(key="topics_more").click().run()
    at.text_input[0].input("topic").run()
    assert len(card_names(at)) == 10


def test_card_has_a_meaning_and_where_to_read(topics_page):
    at = topics_page([concept(1, uses=3)])
    text = [m.value for m in at.markdown]
    assert "Meaning 1." in text
    assert "**Where to read:** 📄 a.pdf, page 1 and 2 more" in text


def test_meaning_is_one_line_with_the_rest_behind_the_button(topics_page):
    long = "A very long meaning " * 15 + "ends here."
    at = topics_page([concept(1, description=f"First sentence. {long}"), concept(2)])
    assert "First sentence." in [m.value for m in at.markdown]
    assert not any(long in m.value for m in at.markdown)
    next(b for b in at.button if b.label == S.TOPICS_READ).click().run()
    assert any(long in m.value for m in at.markdown)


def test_source_text_stays_hidden_until_asked_for(topics_page):
    at = topics_page([concept(1), concept(2)])
    assert not any("Passage" in i.value for i in at.info)
    assert [b.label for b in at.button].count(S.TOPICS_READ) == 2
    next(b for b in at.button if b.label == S.TOPICS_READ).click().run()
    assert [i.value for i in at.info] == ["Passage t1_0"]
    next(b for b in at.button if b.label == S.TOPICS_HIDE).click().run()
    assert not at.info


def test_a_topic_used_often_shows_a_few_passages_and_names_the_rest(topics_page):
    at = topics_page([concept(1, uses=5)])
    next(b for b in at.button if b.label == S.TOPICS_READ).click().run()
    assert len(at.info) == 3
    assert any("Also in:" in c.value and "page 5" in c.value for c in at.caption)


def test_file_filter_only_appears_with_more_than_one_file(topics_page, tmp_path):
    assert not topics_page([concept(1)]).selectbox
    at = topics_page([concept(1), concept(2, doc="b.pdf")])
    at.selectbox[0].set_value("b.pdf").run()
    assert card_names(at) == ["Topic 02"]


def test_big_next_button_goes_to_the_quick_check(tmp_path, monkeypatch):
    course = tmp_path / "ds101"
    course.mkdir()
    for name in ("concepts.json", "chunks.jsonl", "validated_graph.json", "quiz_items.json"):
        shutil.copy(common.EXAMPLES / name, course / name)
    monkeypatch.setattr(common, "OUTPUTS", tmp_path)
    at = AppTest.from_file(str(SITE / "Home.py"), default_timeout=60).run()
    at.switch_page(ui.PAGES["topics"].path).run()
    primary = [b for b in at.button if b.proto.type == "primary"]
    assert [b.label for b in primary] == ["Next: Quick check"]
    primary[0].click().run()
    assert not at.exception
    assert at.title[0].value == S.QUIZ_TITLE


def test_no_topics_points_back_to_step_one(topics_page):
    at = topics_page([])
    assert any(S.TOPICS_NONE in i.value for i in at.info)
    assert [b.label for b in at.button] == [S.TOPICS_ADD]
