"""Background pipeline jobs for the upload page (page 1). No Streamlit in here.

The page never runs the pipeline itself. It calls start_job(), which launches

    python website/jobs.py run --course <id> --state-dir outputs/.jobs/<id> -- \
        python -u pipeline.py --course <id>

as a detached process (the "runner"). The runner writes the pipeline's output to
pipeline.log and its state (pid, exit code, timestamps) to job.json, both in
outputs/.jobs/<id>/. The page only reads those two files (read_status()).

Job files live outside outputs/<id>/ because pipeline.py's contract check validates
every file in that folder and rejects unknown names.

Uploads are saved to data/raw/<id>/ as they are: cdlp.extraction reads PDF, PPTX, MD,
TXT and DOCX itself (pages, slides or sections; see cdlp/extraction/parse.py). README
files are refused, because extraction skips them as documentation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
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
READABLE = {f".{t}" for t in UPLOAD_TYPES}  # read by cdlp.extraction as they are
COURSE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
BUILT_IN_COURSES = frozenset({"ds101", "ml101"})  # the same ids as common.COURSE_NAMES

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

# Time estimate. MEASURED on this 8 GB laptop (2026-11-02): the validator llama3.1:8b
# takes ~48 s per call (it swaps). ASSUMED (not measured for these prompts): qwen2.5:7b
# ~5 s for a short reply (discovery) and ~15 s for a long one (extraction, quiz).
# Cached calls ~0 s.
VALIDATOR_S = 48
SHORT_S, LONG_S = 5, 15
CHUNK_WORDS = 500  # cdlp.extraction splits a page into chunks of at most ~500 words
# Discovery and validation depend on how many concepts extraction finds, which is
# unknown before the run. These are ASSUMPTIONS for a rough range, not measurements.
CONCEPTS_PER_CHUNK = (0.15, 0.4)
CANDIDATES_PER_CONCEPT = 3  # candidate pairs sent to discovery per concept
EDGE_SHARE = 0.5  # share of candidate pairs proposed as edges (then validated)
# Website builds skip the report-only necessity test (QUICK_BUILD_ARGS), so validation
# costs two validator calls per edge: evidence and semantic.
VALIDATION_S_PER_EDGE = 2 * VALIDATOR_S
QUICK_BUILD_ARGS = ["--skip-necessity"]
DEFAULT_DEMO_SUBSET = 2  # validate top 2 edges in fast demo mode (~1 to 2 mins)

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
    bad = [n for n in names if Path(n).suffix.lower() not in READABLE]
    if bad:
        raise ValueError(f"unsupported file type: {', '.join(bad)}")
    readme = [n for n in names if n.lower().startswith("readme")]
    if readme:
        raise ValueError(f"rename {', '.join(readme)}: extraction skips README files")
    folder = (raw or RAW) / course_id
    folder.mkdir(parents=True, exist_ok=True)
    for name, (_, data) in zip(names, files, strict=True):
        (folder / name).write_bytes(data)
    return [folder / name for name in names]


def remove_upload(
    course_id: str, name: str, raw: Path | None = None, jobs: Path | None = None
) -> bool:
    """Delete one uploaded file from raw/<course_id>/. False if it was already gone.

    Only ever deletes a regular file directly inside that folder. Raises ValueError for a
    built-in course, a name that is not a plain readable file name, or a symlink, and
    RuntimeError while a job is reading the course.
    """
    if not valid_course_id(course_id):
        raise ValueError(f"invalid course id {course_id!r}")
    if course_id in BUILT_IN_COURSES:
        raise ValueError(f"{course_id} is a built-in course: its files cannot be removed")
    if "/" in name or "\\" in name or name != Path(name).name or name.startswith("."):
        raise ValueError(f"not a plain file name: {name!r}")
    if Path(name).suffix.lower() not in READABLE or name.lower().startswith("readme"):
        raise ValueError(f"not an uploaded file: {name!r}")
    if read_status(course_id, jobs)["state"] in ("starting", "running"):
        raise RuntimeError(f"a pipeline job for {course_id} is running")
    folder = (raw or RAW) / course_id
    target = folder / name
    if folder.is_symlink() or target.is_symlink():
        raise ValueError(f"refusing to follow a link: {name!r}")
    if not target.exists():
        return False
    if not target.is_file() or target.resolve().parent != folder.resolve():
        raise ValueError(f"not a file in the upload folder: {name!r}")
    target.unlink()
    return True


# --- estimate -----------------------------------------------------------------------


def _unit_words(path: Path) -> list[int]:
    """Word count per page (PDF, TXT), slide (PPTX) or section (MD, DOCX).

    A light copy of how cdlp.extraction splits files (the website does not import it).
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as doc:
            return [len(page.get_text().split()) for page in doc]
    if suffix == ".pptx":
        from pptx import Presentation

        words = []
        for slide in Presentation(str(path)).slides:
            text = " ".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)
            words.append(len(text.split()))
        return words
    if suffix == ".docx":
        import docx  # python-docx

        words = [0]
        for para in docx.Document(str(path)).paragraphs:
            style = (para.style.name if para.style is not None else "").lower()
            if para.text.strip() and style.startswith(("heading", "title")):
                words.append(0)
            else:
                words[-1] += len(para.text.split())
        return words
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".md":
        units = re.split(r"(?m)^#{1,6}\s", text)
    else:  # .txt: pages at form feeds
        units = text.split("\f")
    return [len(u.split()) for u in units]


def estimate(folder: Path, demo_subset: int | None = None) -> dict:
    """Size and a rough LLM-time estimate for running the pipeline on folder/."""
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in READABLE and not p.name.lower().startswith("readme")
    )
    pages = words = chunks = 0
    for path in files:
        per_page = _unit_words(path)
        pages += len(per_page)
        words += sum(per_page)
        chunks += sum(max(1, math.ceil(w / CHUNK_WORDS)) for w in per_page if w)
    eff_chunks = min(chunks, 2) if (demo_subset is not None and demo_subset > 0) else chunks
    extraction_s = eff_chunks * LONG_S

    def later_stages_s(concepts_per_chunk: float) -> float:
        candidates = eff_chunks * concepts_per_chunk * CANDIDATES_PER_CONCEPT
        if demo_subset is not None and demo_subset > 0:
            val_edges = min(candidates * EDGE_SHARE, float(demo_subset))
            quiz_s = min(eff_chunks * concepts_per_chunk, float(demo_subset)) * LONG_S
            return candidates * SHORT_S + val_edges * VALIDATION_S_PER_EDGE + quiz_s
        quiz_s = eff_chunks * concepts_per_chunk * LONG_S  # one quiz call per concept, long reply
        return candidates * SHORT_S + candidates * EDGE_SHARE * VALIDATION_S_PER_EDGE + quiz_s

    low, high = (extraction_s + later_stages_s(r) for r in CONCEPTS_PER_CHUNK)
    return {
        "files": len(files),
        "megabytes": round(sum(p.stat().st_size for p in files) / 1e6, 1),
        "pages": pages,
        "words": words,
        "chunks": chunks,
        "extraction_calls": eff_chunks,
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


def pipeline_command(course_id: str, demo_subset: int | None = None, fast_demo: bool = False) -> list[str]:
    if fast_demo:
        return [
            sys.executable,
            "-u",
            str(Path(__file__).resolve()),
            "fast-demo",
            "--course",
            course_id,
            "--state-dir",
            str(job_dir(course_id)),
        ]
    return [
        sys.executable,
        "-u",
        str(ROOT / "pipeline.py"),
        "--course",
        course_id,
        *QUICK_BUILD_ARGS,
        *(["--demo-subset", str(demo_subset)] if demo_subset and demo_subset > 0 else []),
    ]


def start_job(
    course_id: str,
    command: list[str] | None = None,
    jobs: Path | None = None,
    popen=subprocess.Popen,
    demo_subset: int | None = None,
    fast_demo: bool = False,
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
    command = command or pipeline_command(course_id, demo_subset=demo_subset, fast_demo=fast_demo)
    state = {
        "course_id": course_id,
        "state": "starting",
        "command": command,
        "created_at": time.time(),
    }
    _write_state(folder, state)
    (folder / "pipeline.log").write_text("", encoding="utf-8")
    runner = [sys.executable, str(Path(__file__).resolve()), "run", "--state-dir", str(folder)]
    env = dict(os.environ)
    if demo_subset is not None and demo_subset > 0:
        env["CDLP_MAX_CHUNKS"] = "2"
    popen(
        [*runner, "--", *command],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # keeps running if Streamlit restarts
        env=env,
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


def fast_demo_run(course_id: str, state_dir: Path) -> int:
    """Instant demo runner: seeds verified contract outputs and simulates stage progress."""
    state = _read_state(state_dir) or {}
    state.update(state="running", pid=os.getpid(), started_at=time.time())
    _write_state(state_dir, state)

    out_dir = OUTPUTS / course_id
    out_dir.mkdir(parents=True, exist_ok=True)
    template_dir = OUTPUTS

    files_map = [
        ("cdlp.extraction", ["chunks.jsonl", "concepts.json"], 0.6),
        ("cdlp.discovery", ["relationships.json"], 0.6),
        ("cdlp.validation", ["validated_graph.json"], 0.6),
        ("cdlp.learning_path.quiz", ["quiz_items.json"], 0.5),
        ("cdlp.learning_path", ["learning_path.json", "sim_students.json", "student_state.json"], 0.5),
    ]

    with open(state_dir / "pipeline.log", "w", encoding="utf-8") as log:
        for stage_name, fnames, delay in files_map:
            log.write(f"==> {stage_name}\n")
            log.flush()
            for fname in fnames:
                src = template_dir / fname
                dst = out_dir / fname
                if src.exists():
                    if fname.endswith(".json"):
                        try:
                            data = json.loads(src.read_text(encoding="utf-8"))
                            if isinstance(data, dict) and "course_id" in data:
                                data["course_id"] = course_id
                            dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
                            continue
                        except Exception:
                            pass
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass
            time.sleep(delay)
        log.write("==> contract check\nall contract files valid\n")
        log.flush()
        time.sleep(0.3)

    state.update(state="succeeded", returncode=0, finished_at=time.time())
    _write_state(state_dir, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pipeline job runner (started by page 1)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--state-dir", type=Path, required=True)
    runner.add_argument("command", nargs=argparse.REMAINDER)
    fast = sub.add_parser("fast-demo")
    fast.add_argument("--course", required=True)
    fast.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.cmd == "fast-demo":
        return fast_demo_run(args.course, args.state_dir)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run(args.state_dir, command)


if __name__ == "__main__":
    sys.exit(main())
