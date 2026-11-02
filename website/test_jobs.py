"""Upload -> background pipeline job (website/jobs.py), the course list and the add-notes page.

The pipeline is never run: jobs get a fake command that prints pipeline.py's stage
markers ("==> cdlp.extraction", ...) and exits 0 or 1. No LLM is called.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SITE = Path(__file__).parent
if str(SITE) not in sys.path:  # as `streamlit run website/Home.py` does
    sys.path.insert(0, str(SITE))

import common  # noqa: E402
import jobs  # noqa: E402

PAGE = SITE / "pages" / "1_Add_your_notes.py"
ALL_STAGES = "".join(f"print('==> {key}', flush=True)\n" for key, _ in jobs.STAGES[:5])
SUCCESS = ALL_STAGES + (
    "print('==> cdlp.root_cause skipped (no student_answers.json)')\nprint('==> contract check')\n"
)
LLM_DOWN = (
    "print('==> cdlp.extraction')\nprint('==> cdlp.discovery')\n"
    "print('requests.exceptions.ConnectionError: [Errno 61] Connection refused')\n"
    "raise SystemExit(1)\n"
)


def fake_pipeline(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_pipeline.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def wait_until_finished(course: str, jobs_dir: Path, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = jobs.read_status(course, jobs_dir)
        if status["state"] in ("succeeded", "failed"):
            return status
        time.sleep(0.1)
    raise AssertionError(f"job did not finish: {jobs.read_status(course, jobs_dir)}")


def make_pdf(path: Path, pages: list[str]) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)


# --- course ids and uploads -------------------------------------------------------


@pytest.mark.parametrize("course", ["ds101", "os_2026", "ab"])
def test_valid_course_ids(course):
    assert jobs.valid_course_id(course)


@pytest.mark.parametrize("course", ["", "a", "DS101", "1ds", "ds-101", "../etc", "ds 101"])
def test_invalid_course_ids(course):
    assert not jobs.valid_course_id(course)


def test_safe_name_drops_folders_and_odd_characters():
    assert jobs.safe_name("../../My Notes!.PDF") == "My_Notes.pdf"
    assert jobs.safe_name("C:\\x\\lec 1.pptx") == "lec_1.pptx"


def test_save_uploads_rejects_bad_input_before_writing(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        jobs.save_uploads("c1", [("a.pdf", b"%PDF"), ("b.exe", b"x")], raw=tmp_path)
    with pytest.raises(ValueError, match="course id"):
        jobs.save_uploads("../x", [("a.pdf", b"%PDF")], raw=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_every_format_is_saved_unchanged(tmp_path):
    files = [
        ("lec1.pdf", b"%PDF-1"),
        ("s.pptx", b"PK"),
        ("notes.md", b"# Graphs\n\nA graph has vertices."),
        ("notes.txt", b"Recursion."),
        ("week 3.docx", b"PK-docx"),
    ]
    saved = jobs.save_uploads("c1", files, raw=tmp_path)
    assert [p.name for p in saved] == ["lec1.pdf", "s.pptx", "notes.md", "notes.txt", "week_3.docx"]
    course = tmp_path / "c1"
    assert (course / "notes.md").read_bytes() == b"# Graphs\n\nA graph has vertices."
    assert sorted(p.name for p in course.iterdir()) == sorted(p.name for p in saved)  # no PDFs


def test_readme_uploads_are_refused(tmp_path):
    with pytest.raises(ValueError, match="README"):
        jobs.save_uploads("c1", [("README.md", b"# notes")], raw=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_estimate_counts_sections_of_text_formats(tmp_path):
    docx = pytest.importorskip("docx")
    (tmp_path / "a.md").write_text("# One\n" + "w " * 600 + "\n## Two\nshort\n")
    (tmp_path / "b.txt").write_text("page one\fpage two")
    (tmp_path / "README.md").write_text("# skipped\nnot course material")
    document = docx.Document()
    document.add_heading("Heaps", level=1)
    document.add_paragraph("A heap keeps the smallest key at the root.")
    document.save(tmp_path / "c.docx")
    est = jobs.estimate(tmp_path)
    assert est["files"] == 3
    # md: 2 sections (600 words -> 2 chunks, 1 word -> 1); txt: 2 pages; docx: 1 section
    assert est["chunks"] == 2 + 1 + 2 + 1


# --- estimate and LLM check ---------------------------------------------------------


def test_estimate_counts_pages_chunks_and_llm_time(tmp_path):
    make_pdf(tmp_path / "a.pdf", ["Trees and binary trees", "Binary search trees"])
    (tmp_path / "skip.csv").write_text("not read by extraction")
    est = jobs.estimate(tmp_path)
    assert (est["files"], est["pages"], est["chunks"]) == (1, 2, 2)
    assert est["extraction_calls"] == 2
    assert est["extraction_minutes"] == round(2 * jobs.LONG_S / 60)
    low, high = est["total_minutes"]
    assert est["extraction_minutes"] <= low <= high


def test_llm_status_reports_an_unreachable_endpoint_clearly():
    with socket.socket() as s:  # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    ok, message = jobs.llm_status(f"http://127.0.0.1:{port}", timeout=0.2)
    assert not ok
    assert "No LLM is reachable" in message and "ollama serve" in message


def test_llm_status_reachable():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        ok, _ = jobs.llm_status(f"http://127.0.0.1:{server.getsockname()[1]}")
    assert ok


def test_llm_base_url_env_first_then_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("LLM_MODEL=x\nLLM_BASE_URL='http://box:1234/'\n")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert jobs.llm_base_url(tmp_path) == "http://box:1234"
    monkeypatch.setenv("LLM_BASE_URL", "http://other:9")
    assert jobs.llm_base_url(tmp_path) == "http://other:9"


# --- background jobs (fake pipeline) ------------------------------------------------


def test_start_job_launches_a_detached_runner(tmp_path):
    calls = []
    state = jobs.start_job(
        "c1", ["echo", "hi"], jobs=tmp_path, popen=lambda *a, **k: calls.append((a, k))
    )
    (args,), kwargs = calls[0]
    assert args[-3:] == ["--", "echo", "hi"] and "run" in args
    assert kwargs["start_new_session"] is True
    assert state["state"] == "starting"
    assert jobs.read_status("c1", tmp_path)["state"] == "starting"


def test_default_command_is_the_pipeline_for_the_course():
    command = jobs.pipeline_command("os101")
    assert command[-4:] == [str(jobs.ROOT / "pipeline.py"), "--course", "os101", "--skip-necessity"]


def test_successful_run_marks_every_stage(tmp_path):
    jobs.start_job("c1", fake_pipeline(tmp_path, SUCCESS), jobs=tmp_path / "jobs")
    status = wait_until_finished("c1", tmp_path / "jobs")
    assert status["state"] == "succeeded" and status["returncode"] == 0
    assert {s["stage"]: s["status"] for s in status["stages"]} == {
        "cdlp.extraction": "done",
        "cdlp.discovery": "done",
        "cdlp.validation": "done",
        "cdlp.learning_path.quiz": "done",
        "cdlp.learning_path": "done",
        "cdlp.root_cause": "skipped",
        "contract check": "done",
    }
    assert status["progress"] == 1.0 and "==> contract check" in status["log"]


def test_failed_run_names_the_stage_and_the_missing_llm(tmp_path):
    jobs.start_job("c1", fake_pipeline(tmp_path, LLM_DOWN), jobs=tmp_path / "jobs")
    status = wait_until_finished("c1", tmp_path / "jobs")
    assert status["state"] == "failed" and status["returncode"] == 1
    stages = {s["stage"]: s["status"] for s in status["stages"]}
    assert stages["cdlp.extraction"] == "done"
    assert stages["cdlp.discovery"] == "failed"
    assert stages["cdlp.validation"] == "pending"
    assert "LLM endpoint could not be reached" in status["error"]


def test_other_failures_show_the_last_log_line(tmp_path):
    body = "print('==> cdlp.extraction')\nprint('ValueError: bad pdf')\nraise SystemExit(2)\n"
    jobs.start_job("c1", fake_pipeline(tmp_path, body), jobs=tmp_path / "jobs")
    status = wait_until_finished("c1", tmp_path / "jobs")
    assert "code 2" in status["error"] and "ValueError: bad pdf" in status["error"]


def test_a_running_job_blocks_a_second_start(tmp_path):
    folder = tmp_path / "c1"
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps({"state": "running", "pid": os.getpid()}))
    with pytest.raises(RuntimeError, match="already running"):
        jobs.start_job("c1", ["true"], jobs=tmp_path, popen=lambda *a, **k: None)


def test_a_dead_runner_counts_as_failed(tmp_path):
    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True
    )
    folder = tmp_path / "c1"
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps({"state": "running", "pid": int(finished.stdout)}))
    status = jobs.read_status("c1", tmp_path)
    assert status["state"] == "failed" and "stopped" in status["error"]


def test_a_runner_that_never_started_counts_as_failed(tmp_path):
    folder = tmp_path / "c1"
    folder.mkdir()
    old = time.time() - jobs.START_TIMEOUT - 1
    (folder / "job.json").write_text(json.dumps({"state": "starting", "created_at": old}))
    assert jobs.read_status("c1", tmp_path)["state"] == "failed"


def test_no_job_yet(tmp_path):
    status = jobs.read_status("c1", tmp_path)
    assert status["state"] == "none" and status["error"] is None


# --- dynamic course list ------------------------------------------------------------


def test_course_list_comes_from_output_folders(tmp_path):
    for name in ["ml101", "os101", ".jobs", "_tmp"]:
        (tmp_path / name).mkdir()
        for file in common.COURSE_FILES:
            (tmp_path / name / file).write_text("{}")
    (tmp_path / "concepts.json").write_text("{}")  # legacy top-level file: not a course
    (tmp_path / "half_done").mkdir()  # a folder without a finished run: not a course
    (tmp_path / "half_done" / "concepts.json").write_text("{}")
    assert common.list_courses(tmp_path) == ["ml101", "os101"]


def test_course_names_never_show_a_raw_id():
    assert common.course_label("ds101") == "Data Structures & Algorithms"
    assert common.course_label("biology_notes") == "Biology notes"
    assert common.course_id_from_name("  Biology notes! ") == "biology_notes"
    assert jobs.valid_course_id(common.course_id_from_name("Biology notes"))
    assert not jobs.valid_course_id(common.course_id_from_name("2024"))


def test_course_list_falls_back_to_the_built_in_courses(tmp_path):
    assert common.list_courses(tmp_path) == ["ds101", "ml101"]
    assert common.list_courses(tmp_path / "missing") == ["ds101", "ml101"]


# --- page 1 -------------------------------------------------------------------------


@pytest.fixture
def page(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(jobs, "RAW", tmp_path / "raw")
    monkeypatch.setattr(jobs, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "llm_status", lambda *a, **k: (False, "No LLM is reachable (test)"))

    def open_page(course: str):
        at = AppTest.from_file(str(PAGE), default_timeout=60)
        at.session_state["upload_course"] = course
        return at.run()

    return open_page


def build_button(at):
    return at.button(key="build")


def test_page_blocks_the_build_without_an_llm(page, tmp_path):
    (tmp_path / "raw" / "c1").mkdir(parents=True)
    make_pdf(tmp_path / "raw" / "c1" / "lec.pdf", ["Trees"])
    at = page("c1")
    assert not at.exception
    assert any("AI helper is off" in e.value and "What to do" in e.value for e in at.error)
    assert any("No LLM is reachable" in c.value for c in at.code)  # kept for the teacher
    assert build_button(at).disabled
    assert any("rough guess" in m.value for m in at.markdown)


def test_page_shows_progress_of_a_running_job(page, tmp_path):
    folder = tmp_path / "jobs" / "c1"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"state": "running", "pid": os.getpid()}))
    (folder / "pipeline.log").write_text("==> cdlp.extraction\n==> cdlp.discovery\n")
    at = page("c1")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert (
        "✅ Done: Finding topics" in text and "⏳ Working: Finding which topics come first" in text
    )


def test_page_shows_why_a_job_failed(page, tmp_path):
    folder = tmp_path / "jobs" / "c1"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"state": "failed", "returncode": 1}))
    (folder / "pipeline.log").write_text("==> cdlp.extraction\nConnectionError: refused\n")
    at = page("c1")
    assert not at.exception
    assert any("What to do" in e.value for e in at.error)
    assert any("LLM endpoint could not be reached" in c.value for c in at.code)  # for the teacher


def test_page_rejects_a_name_it_cannot_use(page):
    at = page("9 lives")
    assert not at.exception
    assert any("We cannot use that name" in e.value for e in at.error)


def test_website_builds_skip_the_necessity_test():
    cmd = jobs.pipeline_command("notes101")
    assert cmd[-2:] == ["notes101", "--skip-necessity"]
    assert jobs.VALIDATION_S_PER_EDGE == 2 * jobs.VALIDATOR_S  # evidence + semantic only
