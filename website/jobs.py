"""Background pipeline jobs for the upload page (page 1). No Streamlit in here.

The page never runs the pipeline itself. It calls start_job(), which launches

    python website/jobs.py run --course <id> --state-dir outputs/.jobs/<id> -- \
        python -u pipeline.py --course <id>

as a detached process (the "runner"). The runner writes the pipeline's output to
pipeline.log and its state (pid, exit code, timestamps) to job.json, both in
outputs/.jobs/<id>/. The page only reads those two files (read_status()).

Job files live outside outputs/<id>/ because pipeline.py's contract check validates
every file in that folder and rejects unknown names.

Uploads: PDF and PPTX are saved as they are. Extraction reads only PDF and PPTX, so
TXT, MD and DOCX are converted to a PDF next to them (`notes.docx` -> `notes.docx.pdf`)
and the original is kept in data/raw/<id>/originals/ (extraction ignores subfolders).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUTPUTS = ROOT / "outputs"
JOBS = OUTPUTS / ".jobs"

UPLOAD_TYPES = ["pdf", "pptx", "txt", "md", "docx"]
NATIVE = {".pdf", ".pptx"}  # read by cdlp.extraction as they are
CONVERTED = {".txt", ".md", ".docx"}  # converted to PDF first
COURSE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

# (marker printed by pipeline.py as "==> <marker>", label shown on the page)
STAGES = [
    ("cdlp.extraction", "Concept extraction"),
    ("cdlp.discovery", "Dependency discovery"),
    ("cdlp.validation", "Validation agent"),
    ("cdlp.learning_path.quiz", "Quiz generation"),
    ("cdlp.learning_path", "Learning paths"),
    ("cdlp.root_cause", "Root-cause tracing"),
    ("contract check", "Contract check"),
]
START_TIMEOUT = 30  # s a job may stay "starting" before it counts as failed to start

# Time estimate. Per-call times measured on the team laptop with llama3.1:8b
# (CLAUDE.local.md): ~18 s for a short reply, ~36 s for a long one. Cached calls ~0 s.
SHORT_S, LONG_S = 18, 36
CHUNK_WORDS = 500  # cdlp.extraction splits a page into chunks of at most ~500 words
# Discovery and validation depend on how many concepts extraction finds, which is
# unknown before the run. These are ASSUMPTIONS for a rough range, not measurements.
CONCEPTS_PER_CHUNK = (0.15, 0.4)
CANDIDATES_PER_CONCEPT = 3  # candidate pairs sent to discovery per concept
EDGE_SHARE = 0.5  # share of candidate pairs proposed as edges (then validated)
# Validation per edge: evidence (short) + semantic (short) + necessity test
# (question writing and 3 learner runs: long; 3 grades: short).
VALIDATION_S_PER_EDGE = 2 * SHORT_S + 4 * LONG_S + 3 * SHORT_S

LLM_HINTS = ("Connection refused", "ConnectionError", "Max retries exceeded", "NewConnectionError")


# --- courses and uploads ------------------------------------------------------------


def valid_course_id(course_id: str) -> bool:
    return bool(COURSE_ID.match(course_id or ""))


def safe_name(name: str) -> str:
    """A file name without folders or odd characters (`../My Notes!.pdf` -> `My_Notes.pdf`)."""
    base = Path(name.replace("\\", "/")).name
    stem, dot, ext = base.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem if dot else base).strip("_") or "file"
    return f"{stem}.{ext.lower()}" if dot else stem


def save_uploads(
    course_id: str, files: list[tuple[str, bytes]], raw: Path | None = None
) -> list[Path]:
    """Save uploads to raw/<course_id>/ and return the files extraction will read.

    files: (original file name, content). Raises ValueError for a bad course id or
    file type, before anything is written.
    """
    if not valid_course_id(course_id):
        raise ValueError(f"invalid course id {course_id!r}")
    names = [safe_name(n) for n, _ in files]
    bad = [n for n in names if Path(n).suffix.lower() not in NATIVE | CONVERTED]
    if bad:
        raise ValueError(f"unsupported file type: {', '.join(bad)}")
    folder = (raw or RAW) / course_id
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, (_, data) in zip(names, files, strict=True):
        suffix = Path(name).suffix.lower()
        if suffix in NATIVE:
            (folder / name).write_bytes(data)
            saved.append(folder / name)
            continue
        originals = folder / "originals"
        originals.mkdir(exist_ok=True)
        (originals / name).write_bytes(data)
        pdf = folder / f"{name}.pdf"
        text_to_pdf(blocks_of(name, data), pdf, title=name)
        saved.append(pdf)
    return saved


def blocks_of(name: str, data: bytes) -> list[tuple[str, str]]:
    """(kind, text) blocks of a TXT / MD / DOCX file; kind is 'h' (heading) or 'p'."""
    suffix = Path(name).suffix.lower()
    if suffix == ".docx":
        import io

        import docx  # python-docx

        document = docx.Document(io.BytesIO(data))
        blocks = []
        for p in document.paragraphs:
            if p.text.strip():
                heading = (p.style.name or "").lower().startswith(("heading", "title"))
                blocks.append(("h" if heading else "p", p.text.strip()))
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    blocks.append(("p", " | ".join(cells)))
        return blocks
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if suffix == ".md":
            lines = para.splitlines()
            while lines and re.match(r"^#{1,6}\s", lines[0]):  # one heading per line
                blocks.append(("h", lines.pop(0).lstrip("#").strip()))
            para = "\n".join(lines).strip()
            if not para:
                continue
        blocks.append(("p", para))
    return blocks


def text_to_pdf(blocks: list[tuple[str, str]], out: Path, title: str) -> int:
    """Lay out text blocks on A4 pages with PyMuPDF; returns the page count."""
    import pymupdf

    body = (
        "".join(
            f"<h2>{html.escape(t)}</h2>" if kind == "h" else f"<p>{html.escape(t)}</p>"
            for kind, t in blocks
        )
        or f"<p>{html.escape(title)}</p>"
    )
    story = pymupdf.Story(html=body)
    writer = pymupdf.DocumentWriter(str(out))
    page_rect = pymupdf.paper_rect("a4")
    area = page_rect + (54, 54, -54, -54)
    pages, more = 0, True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


# --- estimate -----------------------------------------------------------------------


def _page_words(path: Path) -> list[int]:
    """Word count of each page (PDF) or slide (PPTX)."""
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as doc:
            return [len(page.get_text().split()) for page in doc]
    from pptx import Presentation

    words = []
    for slide in Presentation(str(path)).slides:
        text = " ".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)
        words.append(len(text.split()))
    return words


def estimate(folder: Path) -> dict:
    """Size and a rough LLM-time estimate for running the pipeline on folder/."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in NATIVE)
    pages = words = chunks = 0
    for path in files:
        per_page = _page_words(path)
        pages += len(per_page)
        words += sum(per_page)
        chunks += sum(max(1, math.ceil(w / CHUNK_WORDS)) for w in per_page if w)
    extraction_s = chunks * LONG_S

    def later_stages_s(concepts_per_chunk: float) -> float:
        candidates = chunks * concepts_per_chunk * CANDIDATES_PER_CONCEPT
        quiz_s = chunks * concepts_per_chunk * LONG_S  # one quiz call per concept, long reply
        return candidates * SHORT_S + candidates * EDGE_SHARE * VALIDATION_S_PER_EDGE + quiz_s

    low, high = (extraction_s + later_stages_s(r) for r in CONCEPTS_PER_CHUNK)
    return {
        "files": len(files),
        "megabytes": round(sum(p.stat().st_size for p in files) / 1e6, 1),
        "pages": pages,
        "words": words,
        "chunks": chunks,
        "extraction_calls": chunks,
        "extraction_minutes": round(extraction_s / 60),
        "total_minutes": (round(low / 60), round(high / 60)),
    }


# --- LLM check ----------------------------------------------------------------------


def llm_base_url(root: Path | None = None) -> str:
    """LLM_BASE_URL from the environment, else from .env, else Ollama's default."""
    url = os.environ.get("LLM_BASE_URL")
    env = (root or ROOT) / ".env"
    if not url and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "LLM_BASE_URL":
                url = value.strip().strip("'\"")
    return (url or "http://localhost:11434").rstrip("/")


def llm_status(url: str | None = None, timeout: float = 1.0) -> tuple[bool, str]:
    """(reachable, message). Only opens a TCP connection; makes no LLM call."""
    url = url or llm_base_url()
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname or "localhost", port), timeout=timeout):
            return True, f"LLM endpoint reachable at {url}."
    except OSError:
        return False, (
            f"No LLM is reachable at {url}. Extraction, discovery and validation need one, "
            "so the pipeline would stop at discovery. Start Ollama (`ollama serve`) or set "
            "LLM_BASE_URL in .env to a free OpenAI-compatible endpoint, then reload this page. "
            "(The hosted website has no LLM: run the website locally to build a course.)"
        )


# --- jobs ---------------------------------------------------------------------------


def job_dir(course_id: str, jobs: Path | None = None) -> Path:
    return (jobs or JOBS) / course_id


def _write_state(folder: Path, state: dict) -> None:
    tmp = folder / "job.json.tmp"
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(folder / "job.json")


def _read_state(folder: Path) -> dict | None:
    try:
        return json.loads((folder / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pipeline_command(course_id: str) -> list[str]:
    return [sys.executable, "-u", str(ROOT / "pipeline.py"), "--course", course_id]


def start_job(
    course_id: str,
    command: list[str] | None = None,
    jobs: Path | None = None,
    popen=subprocess.Popen,
) -> dict:
    """Launch the runner in the background; returns the initial state.

    Raises ValueError for a bad course id and RuntimeError if a job for this course
    is still running. command defaults to pipeline.py for the course (tests pass a fake).
    """
    if not valid_course_id(course_id):
        raise ValueError(f"invalid course id {course_id!r}")
    folder = job_dir(course_id, jobs)
    if read_status(course_id, jobs)["state"] in ("starting", "running"):
        raise RuntimeError(f"a pipeline job for {course_id} is already running")
    folder.mkdir(parents=True, exist_ok=True)
    command = command or pipeline_command(course_id)
    state = {
        "course_id": course_id,
        "state": "starting",
        "command": command,
        "created_at": time.time(),
    }
    _write_state(folder, state)
    (folder / "pipeline.log").write_text("", encoding="utf-8")
    runner = [sys.executable, str(Path(__file__).resolve()), "run", "--state-dir", str(folder)]
    popen(
        [*runner, "--", *command],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # keeps running if Streamlit restarts
    )
    return state


def run(state_dir: Path, command: list[str]) -> int:
    """The runner: run command, log its output, record the result in job.json."""
    state = _read_state(state_dir) or {}
    state.update(state="running", pid=os.getpid(), started_at=time.time())
    _write_state(state_dir, state)
    try:
        with open(state_dir / "pipeline.log", "ab") as log:
            code = subprocess.run(
                command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT
            ).returncode
    except OSError as exc:
        with open(state_dir / "pipeline.log", "a", encoding="utf-8") as log:
            log.write(f"\ncould not start the pipeline: {exc}\n")
        code = 127
    state.update(
        state="succeeded" if code == 0 else "failed", returncode=code, finished_at=time.time()
    )
    _write_state(state_dir, state)
    return code


def stage_progress(log: str, state: str) -> list[dict]:
    """Status per stage (done / running / failed / skipped / pending) from the log."""
    seen = {}
    for line in log.splitlines():
        if line.startswith("==> "):
            marker = line[4:].strip()
            for key, _ in STAGES:
                if marker == key:
                    seen[key] = "started"
                elif marker.startswith(f"{key} skipped"):  # e.g. "cdlp.root_cause skipped (...)"
                    seen[key] = "skipped"
    started = [k for k, _ in STAGES if seen.get(k) == "started"]
    last = started[-1] if started else None
    rows = []
    for key, label in STAGES:
        status = seen.get(key)
        if status == "skipped":
            pass
        elif status is None:
            status = "pending"
        elif key != last or state == "succeeded":
            status = "done"
        else:
            status = "failed" if state == "failed" else "running"
        rows.append({"stage": key, "label": label, "status": status})
    return rows


def failure_reason(log: str, returncode: int | None) -> str:
    if any(hint in log for hint in LLM_HINTS):
        return "The LLM endpoint could not be reached during the run. Start Ollama and retry."
    lines = [line for line in log.strip().splitlines() if line.strip()]
    last = lines[-1] if lines else "no output"
    return f"The pipeline exited with code {returncode}. Last log line: {last}"


def read_status(course_id: str, jobs: Path | None = None, tail: int = 60) -> dict:
    """What the page shows: state, per-stage progress, log tail and a failure reason.

    state: none / starting / running / succeeded / failed.
    """
    folder = job_dir(course_id, jobs)
    state = _read_state(folder)
    if state is None:
        return {"state": "none", "stages": stage_progress("", "none"), "log": "", "error": None}
    log_path = folder / "pipeline.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    current = state.get("state", "failed")
    error = None
    if current == "starting" and time.time() - state.get("created_at", 0) > START_TIMEOUT:
        current, error = "failed", "The background runner did not start."
    elif current == "running" and not _alive(state.get("pid")):
        current, error = "failed", "The background runner stopped before the pipeline finished."
    elif current == "failed":
        error = failure_reason(log, state.get("returncode"))
    stages = stage_progress(log, current)
    done = sum(s["status"] in ("done", "skipped") for s in stages)
    return {
        **state,
        "state": current,
        "stages": stages,
        "progress": done / len(stages),
        "log": "\n".join(log.splitlines()[-tail:]),
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pipeline job runner (started by page 1)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--state-dir", type=Path, required=True)
    runner.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run(args.state_dir, command)


if __name__ == "__main__":
    sys.exit(main())
