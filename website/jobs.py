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
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RAW = ROOT / "data" / "raw"
OUTPUTS = ROOT / "outputs"
JOBS = OUTPUTS / ".jobs"
PREVIEW_FOLDER = "_previews"  # the same name as common.PREVIEW_FOLDER

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
            "LLM_BASE_URL in .env to a free OpenAI-compatible endpoint, then "
            "reload this page."
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
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            return exit_code.value == 259
        except Exception:
            return False

    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False
    except PermissionError:
        return True
    return True


def pipeline_command(
    course_id: str, demo_subset: int | None = None, fast_demo: bool = False
) -> list[str]:
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


# Words in the question lists' keywords that also appear in ordinary headings ("Reasons For
# Change", "Linked Lists"): on their own they do not show the topic is what a list asks about.
AMBIGUOUS_KEYWORDS = frozenset(
    "address char do for if index io layout list memory null page return text web".split()
)
# The hand-written lists are about programming: without these words the notes are on something
# else, and "Cell Function" or "Tree Anatomy" must not get questions about C.
PROGRAMMING_WORDS = (
    "programming",
    "compiler",
    "algorithm",
    "printf",
    "#include",
    "source code",
    "syntax",
    "html",
    "data structure",
    "pointer",
    "python",
)


def notes_are_about_programming(chunks: list[dict]) -> bool:
    text = " ".join(c["text"] for c in chunks).lower()
    return sum(word in text for word in PROGRAMMING_WORDS) >= 2


def topic_matches(topic: str, keywords: list[str]) -> bool:
    """A whole word of the topic is a keyword: "for" is not in "information"."""
    words = set(re.findall(r"[a-z0-9]+", topic.lower()))
    words |= {w[:-1] for w in words if w.endswith("s")}
    return bool(words & (set(keywords) - AMBIGUOUS_KEYWORDS))


def generate_course_from_uploads(course_id: str, out_dir: Path) -> bool:
    """List headings from data/raw/<course_id>/ as a preview. No AI, decisions or grades."""
    from cdlp.extraction.parse import apply_chunk_limit, parse_directory
    from cdlp.shared.validate import check

    raw_dir = RAW / course_id
    if not raw_dir.is_dir():
        return False
    chunks, truncated = apply_chunk_limit(parse_directory(raw_dir, course_id=course_id))
    if not chunks:
        return False

    with open(out_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    def slug(text: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return s[:35] or "concept"

    def is_code(s: str) -> bool:
        return any(
            tok in s
            for tok in [
                ";",
                "{",
                "}",
                "==",
                "!=",
                "++",
                "--",
                "=",
                "printf",
                "scanf",
                "#include",
                "void ",
                "int ",
                "return ",
            ]
        )

    skip_phrases = [
        "LEARNING GUIDE",
        "HANDBOOK",
        "BEGINNER FRIENDLY",
        "MINI PROJECT",
        "PROJECT 1",
        "PROJECT 2",
        "PRACTICE SET",
        "PRACTICE",
        "EXERCISE",
        "INDEX",
        "PREFACE",
        "CONTENTS",
        "PAGE",
        "HTTP",
        "WWW",
        "COPYRIGHT",
        "ALL RIGHTS",
        "TABLE OF",
    ]

    def clean_heading(h: str) -> str:
        h = re.sub(r"^CHAPTER\s*\d+\s*[–—\-~\s:]*", "", h, flags=re.IGNORECASE).strip()
        h = re.sub(r"^[0-9.]+\s*", "", h).strip()
        h = re.sub(r"\s*&\s*", " and ", h)
        h = re.sub(r"\bI/O\b", "Input / Output", h, flags=re.IGNORECASE)
        return h.strip()

    def find_description(text: str) -> str:
        for line in text.splitlines():
            line = line.strip()
            if (
                len(line) >= 20
                and not is_code(line)
                and not any(sp in line.upper() for sp in skip_phrases)
            ):
                line = re.sub(r"\s+", " ", line)
                return line[:140]
        return text.strip().split("\n")[0][:140].strip()

    raw_topics = []
    seen_norms = set()

    for c in chunks:
        h = c.get("heading")
        if not h:
            continue
        h_clean = clean_heading(h)
        norm = re.sub(r"[^a-z0-9]", "", h_clean.lower())
        if not norm or norm in seen_norms:
            continue
        if any(sp.lower() in h_clean.lower() for sp in skip_phrases):
            continue
        if is_code(h_clean) or len(h_clean) < 3 or len(h_clean) > 45:
            continue
        seen_norms.add(norm)
        desc = find_description(c["text"])
        raw_topics.append((h_clean.title(), c, desc))

    if len(raw_topics) < 4:
        for c in chunks:
            for line in c["text"].splitlines():
                line = re.sub(r"^[#*•\-0-9.\s]+", "", line).strip()
                words = line.split()
                if (
                    2 <= len(words) <= 6
                    and not is_code(line)
                    and not any(sp in line.upper() for sp in skip_phrases)
                ):
                    h_clean = clean_heading(line)
                    norm = re.sub(r"[^a-z0-9]", "", h_clean.lower())
                    if norm and norm not in seen_norms and len(h_clean) <= 45:
                        seen_norms.add(norm)
                        desc = find_description(c["text"])
                        raw_topics.append((h_clean.title(), c, desc))
                        break

    if not raw_topics:
        doc_title = Path(chunks[0]["doc"]).stem.replace("_", " ").title()
        raw_topics.append((doc_title, chunks[0], chunks[0]["text"][:140]))

    concepts = []
    for title, chunk, desc in raw_topics[:10]:
        cid = slug(title)
        concepts.append(
            {
                "id": cid,
                "name": title,
                "aliases": [title, cid.replace("_", " ")],
                "description": desc or f"Core concept covering {title}.",
                "sources": [
                    {"doc": chunk["doc"], "page": chunk["page"], "chunk_id": chunk["chunk_id"]}
                ],
            }
        )

    (out_dir / "concepts.json").write_text(
        json.dumps(
            {"schema_version": "1.0", "course_id": course_id, "concepts": concepts}, indent=2
        ),
        encoding="utf-8",
    )

    preview = {
        "schema_version": "1.12",
        "course_id": course_id,
        "kind": "quick_preview",
        "ai_used": False,
        "link_rule": "heading_order",
        "nodes": [{"id": c["id"], "name": c["name"]} for c in concepts],
        "links": [
            {
                "id": f"l{i + 1}",
                "source": concepts[i]["id"],
                "target": concepts[i + 1]["id"],
                **concepts[i]["sources"][0],
            }
            for i in range(len(concepts) - 1)
        ],
        **({"chunks_truncated": truncated} if truncated else {}),
    }
    errors = check(preview, "preview")
    if errors:
        raise ValueError("preview.json breaks the contract:\n  " + "\n  ".join(errors))
    (out_dir / "preview.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")

    quiz_categories = [
        (
            ["variable", "constant", "keyword", "datatype", "identifier"],
            [
                (
                    "What is a variable in programming?",
                    "A named storage location in memory used to hold data that can "
                    "change during "
                    "execution.",
                    [
                        "A fixed instruction that cannot be modified once written in source code.",
                        "A compiler directive used exclusively for importing header files.",
                        "A hardware register reserved exclusively for operating system processes.",
                    ],
                ),
                (
                    "Which of the following is a key rule for naming identifiers and variables?",
                    "An identifier cannot start with a digit and cannot be a reserved keyword.",
                    [
                        "An identifier must begin with a number from 0 to 9.",
                        "An identifier can contain spaces and punctuation marks like @ and #.",
                        "An identifier is strictly limited to exactly three characters in length.",
                    ],
                ),
                (
                    "What distinguishes a constant from a variable?",
                    "A constant maintains a fixed value that cannot be altered during "
                    "program execution.",
                    [
                        "A constant is automatically deleted from memory after its first read.",
                        "A constant can only hold boolean values.",
                        "A constant must be re-declared inside every loop.",
                    ],
                ),
            ],
        ),
        (
            ["operator", "instruction", "expression", "arithmetic", "precedence"],
            [
                (
                    "What is the primary function of operators in programming expressions?",
                    "To perform arithmetic, relational, or logical evaluations on operands.",
                    [
                        "To allocate dynamic heap memory for data structures.",
                        "To define class hierarchies and inheritance trees.",
                        "To convert high-level source files into assembly instructions.",
                    ],
                ),
                (
                    "What is the key difference between the equality operator (==) "
                    "and the assignment "
                    "operator (=)?",
                    "The equality operator compares two values, whereas the "
                    "assignment operator assigns a "
                    "value to a variable.",
                    [
                        "The equality operator stores a value, whereas the assignment "
                        "operator checks for "
                        "equivalence.",
                        "The equality operator is only valid for floating-point calculations.",
                        "Both operators perform identical operations and can be used "
                        "interchangeably.",
                    ],
                ),
                (
                    "In operator precedence rules, how are mixed arithmetic expressions evaluated?",
                    "Multiplication and division are evaluated before addition and "
                    "subtraction unless "
                    "parentheses are used.",
                    [
                        "All operators are always evaluated strictly from right to left.",
                        "Addition and subtraction always take priority over multiplication.",
                        "Expressions are evaluated in random order depending on CPU "
                        "thread availability.",
                    ],
                ),
            ],
        ),
        (
            ["conditional", "if", "else", "switch", "branch"],
            [
                (
                    "What is the purpose of conditional control statements (such as if-else)?",
                    "To choose between different blocks of code based on whether a "
                    "condition is true or "
                    "false.",
                    [
                        "To repeat a block of code continuously until user termination.",
                        "To declare global functions and their parameters.",
                        "To free memory buffers allocated on the stack.",
                    ],
                ),
                (
                    "How are numeric conditions evaluated in conditional expressions "
                    "in languages like C "
                    "and Python?",
                    "Zero evaluates to false, while non-zero values evaluate to true.",
                    [
                        "Zero always evaluates to true, while non-zero values evaluate to false.",
                        "Only negative integers evaluate to true; positive integers are "
                        "always false.",
                        "Numeric values cannot be used in conditional expressions without "
                        "string conversion.",
                    ],
                ),
                (
                    "When is a switch-case statement preferred over a long chain of "
                    "if-else statements?",
                    "When testing a single variable against multiple discrete "
                    "constant values for cleaner "
                    "readability.",
                    [
                        "When evaluating complex range checks with relational inequalities.",
                        "When checking floating-point numbers with decimal precision.",
                        "When defining recursive algorithms on tree data structures.",
                    ],
                ),
            ],
        ),
        (
            ["loop", "iteration", "while", "for", "do"],
            [
                (
                    "What is the fundamental purpose of loop control instructions?",
                    "To execute a block of statements repeatedly as long as a "
                    "specified condition remains "
                    "true.",
                    [
                        "To jump immediately to the end of the program without executing "
                        "further code.",
                        "To declare user-defined structures and data types.",
                        "To allocate contiguous array blocks on the heap.",
                    ],
                ),
                (
                    "What is the difference between a while loop and a do-while loop?",
                    "A while loop tests the condition before execution, while a "
                    "do-while loop executes at "
                    "least once before testing.",
                    [
                        "A while loop cannot use counter variables, whereas a do-while "
                        "loop requires one.",
                        "A do-while loop is only used for file input and output operations.",
                        "A while loop runs indefinitely, while a do-while loop never executes.",
                    ],
                ),
                (
                    "What happens when a 'break' statement is encountered inside a loop?",
                    "The loop is terminated immediately and control passes to the "
                    "statement following the "
                    "loop.",
                    [
                        "The current iteration is skipped, continuing immediately with "
                        "the next loop "
                        "iteration.",
                        "The program halts and prompts the user for keyboard input.",
                        "The loop counter resets to zero and restarts from the beginning.",
                    ],
                ),
            ],
        ),
        (
            ["function", "recursion", "modular", "parameter", "return"],
            [
                (
                    "Why are functions used in computer programs?",
                    "To break complex code into reusable, modular, and testable blocks.",
                    [
                        "To prevent other developers from modifying variables.",
                        "To replace the main function with multiple parallel threads.",
                        "To allocate virtual memory partitions in the operating system.",
                    ],
                ),
                (
                    "What is recursion in computer programming?",
                    "A technique where a function calls itself to solve smaller "
                    "sub-problems until "
                    "reaching a base condition.",
                    [
                        "A memory error caused when two functions have identical names.",
                        "A loop structure that executes strictly on GPU hardware.",
                        "A compiler mechanism that converts interpreted scripts to C bytecode.",
                    ],
                ),
                (
                    "What is the consequence of omitting a base case in a recursive function?",
                    "The function calls itself indefinitely, exhausting stack memory "
                    "and causing a stack "
                    "overflow.",
                    [
                        "The function executes once and returns null without error.",
                        "The compiler automatically generates an iterative loop replacement.",
                        "The program slows down by a factor of two but produces correct results.",
                    ],
                ),
            ],
        ),
        (
            ["pointer", "address", "dereference", "memory"],
            [
                (
                    "What is a pointer in programming?",
                    "A variable that stores the memory address of another variable.",
                    [
                        "A special data type that can only hold positive floating-point numbers.",
                        "A hardware register reserved exclusively for graphics rendering.",
                        "A compiler error that occurs when a variable is used before declaration.",
                    ],
                ),
                (
                    "What is the purpose of the dereference operator (*) when used with a pointer?",
                    "To access or modify the value stored at the memory address the pointer holds.",
                    [
                        "To multiply the memory address by the size of the underlying data type.",
                        "To retrieve the address where the pointer variable itself is stored.",
                        "To free the dynamic memory allocated to the pointer.",
                    ],
                ),
                (
                    "What does the address-of operator (&) return when prefixed to a variable?",
                    "The memory address where the variable is located.",
                    [
                        "The total number of bytes the variable occupies in memory.",
                        "A boolean value indicating whether the variable is positive.",
                        "A duplicate copy of the variable's value on the heap.",
                    ],
                ),
            ],
        ),
        (
            ["array", "list", "index", "vector"],
            [
                (
                    "What is an array in computer programming?",
                    "A fixed-size collection of elements of the same data type stored "
                    "in contiguous memory "
                    "locations.",
                    [
                        "A dynamically linked set of nodes scattered arbitrarily across memory.",
                        "A key-value data structure with constant-time lookup for "
                        "arbitrary strings.",
                        "A hierarchical tree structure where each element has two child pointers.",
                    ],
                ),
                (
                    "In zero-indexed languages, what are the valid index bounds for "
                    "an array of size N?",
                    "Indices range from 0 to N - 1.",
                    [
                        "Indices range from 1 to N.",
                        "Indices range from -1 to N - 1.",
                        "Indices range from 0 to N.",
                    ],
                ),
                (
                    "What is the primary risk of accessing an array index that "
                    "exceeds its declared "
                    "boundary?",
                    "Accessing unauthorized memory, causing segmentation faults or "
                    "undefined behavior.",
                    [
                        "The array will automatically expand its capacity and initialize "
                        "new elements.",
                        "The compiler will halt and delete the source file from disk.",
                        "The operating system automatically wraps the index back to zero.",
                    ],
                ),
            ],
        ),
        (
            ["string", "char", "text", "null"],
            [
                (
                    "How is a string represented in memory in C-style programming?",
                    "As an array of characters terminated by a null character ('\\0').",
                    [
                        "As a primitive integer representing the byte length of the text.",
                        "As a doubly linked list of unicode code points.",
                        "As a compressed binary file stored in secondary storage.",
                    ],
                ),
                (
                    "Why is the null terminator ('\\0') required at the end of a string?",
                    "To mark the boundary where the string data ends in memory.",
                    [
                        "To tell the operating system to capitalize the first letter of "
                        "the string.",
                        "To prevent the string from being modified during runtime.",
                        "To convert the string into an executable binary instruction.",
                    ],
                ),
                (
                    "What does the standard strlen function calculate?",
                    "The number of characters in the string, excluding the "
                    "terminating null character.",
                    [
                        "The total allocated buffer size including the null character.",
                        "The number of words separated by whitespace.",
                        "The memory address where the string is stored.",
                    ],
                ),
            ],
        ),
        (
            ["struct", "union", "record"],
            [
                (
                    "What is the primary purpose of a 'struct' in C and systems programming?",
                    "To group heterogeneous data types together under a single "
                    "user-defined record name.",
                    [
                        "To define a set of constant values with sequential integer IDs.",
                        "To restrict access to private member variables in procedural languages.",
                        "To create a dynamic FIFO queue with enqueue and dequeue operations.",
                    ],
                ),
                (
                    "How are member variables accessed from a structure variable vs a "
                    "structure pointer?",
                    "The dot operator (.) is used with a variable, while the arrow "
                    "operator (->) is used "
                    "with a pointer.",
                    [
                        "The arrow operator (->) is used for variables, and the dot "
                        "operator (.) for pointers.",
                        "The colon operator (:) is used for all structure member accesses.",
                        "Members can only be accessed through public getter methods.",
                    ],
                ),
                (
                    "How does memory allocation differ between a 'struct' and a 'union'?",
                    "A struct allocates separate memory for all members, whereas a "
                    "union shares the same "
                    "memory space for all members.",
                    [
                        "A struct is stored on the heap, whereas a union is stored in CPU "
                        "registers.",
                        "A union can hold unlimited fields, whereas a struct is limited "
                        "to ten fields.",
                        "Struct and union have identical memory allocation semantics.",
                    ],
                ),
            ],
        ),
        (
            ["file", "io", "stream", "disk"],
            [
                (
                    "What is the primary purpose of File I/O operations?",
                    "To persist data on secondary storage so information is retained "
                    "after program "
                    "termination.",
                    [
                        "To allocate temporary cache space in the CPU during arithmetic "
                        "operations.",
                        "To convert high-level programming logic into assembly instructions.",
                        "To allow multiple functions to share local stack variables.",
                    ],
                ),
                (
                    "Why is it essential to close an open file using fclose after "
                    "operations are complete?",
                    "To flush write buffers to disk and release file descriptor "
                    "resources back to the OS.",
                    [
                        "To delete the contents of the file from the hard drive.",
                        "To encrypt the file contents with a random password.",
                        "Closing files is completely optional and has no impact on system "
                        "resources.",
                    ],
                ),
                (
                    "What does an open file call (such as fopen) return if the file "
                    "cannot be opened?",
                    "A NULL pointer indicating that the file could not be accessed.",
                    [
                        "A newly created empty file with the same name automatically.",
                        "An operating system crash with immediate machine restart.",
                        "A pointer to the root directory of the operating system.",
                    ],
                ),
            ],
        ),
        (
            ["html", "tag", "layout", "web", "page", "browser", "css"],
            [
                (
                    "What is the primary function of HTML in web architecture?",
                    "Defining the structural content and semantic hierarchy of web pages.",
                    [
                        "Styling colors, layout grids, and animations.",
                        "Handling database connections and user authentication on the server.",
                        "Compiling JavaScript code into machine bytecode.",
                    ],
                ),
                (
                    "What is the difference between block elements (e.g., <div>, <p>) "
                    "and inline elements "
                    "(e.g., <span>, <a>)?",
                    "Block elements begin on a new line and occupy the full container "
                    "width, whereas "
                    "inline elements sit within text flow.",
                    [
                        "Block elements cannot contain text, while inline elements can "
                        "contain images and "
                        "tables.",
                        "Inline elements are exclusively used within the <head> section "
                        "of an HTML document.",
                        "Block elements are strictly rendered on mobile devices only.",
                    ],
                ),
                (
                    "Which HTML attribute provides alternative descriptive text for images for "
                    "accessibility and screen readers?",
                    "The 'alt' attribute.",
                    [
                        "The 'src' attribute.",
                        "The 'href' attribute.",
                        "The 'title_text' attribute.",
                    ],
                ),
            ],
        ),
        (
            ["tree", "bst", "avl", "heap", "binary", "graph"],
            [
                (
                    "What is the defining invariant of a Binary Search Tree (BST)?",
                    "For every node, all keys in its left subtree are smaller, and "
                    "all keys in its right "
                    "subtree are greater.",
                    [
                        "Every non-leaf node must have exactly two child nodes.",
                        "All leaf nodes must reside at the exact same depth.",
                        "Node values must be stored in alphabetical order across sibling nodes.",
                    ],
                ),
                (
                    "What is the balancing invariant of an AVL tree?",
                    "For any node, the height difference between its left and right "
                    "subtrees is at most 1.",
                    [
                        "All levels of the tree must be completely full of nodes.",
                        "Every parent node must be smaller than both of its child nodes.",
                        "Nodes must be colored red or black to maintain balance.",
                    ],
                ),
                (
                    "What is the average time complexity of searching for an element "
                    "in a balanced BST or "
                    "AVL tree with N nodes?",
                    "O(log N)",
                    [
                        "O(N^2)",
                        "O(1)",
                        "O(N!)",
                    ],
                ),
            ],
        ),
    ]

    quiz_items = []
    programming_notes = notes_are_about_programming(chunks)
    for c in concepts:
        c_name = c["name"].lower()
        matched = False
        for keywords, q_defs in quiz_categories:
            if programming_notes and topic_matches(c_name, keywords):
                matched = True
                for idx, (q_text, ans, distractors) in enumerate(q_defs, 1):
                    quiz_items.append(
                        {
                            "id": f"q_{c['id']}_{idx}",
                            "concept_id": c["id"],
                            "origin": "general_practice",
                            "question": q_text,
                            "options": [ans] + distractors,
                            "answer": ans,
                        }
                    )
                break
        if not matched:
            ans1 = (
                f"It provides the foundational rules, terminology, and mechanics for {c['name']}."
            )
            quiz_items.append(
                {
                    "id": f"q_{c['id']}_1",
                    "concept_id": c["id"],
                    "origin": "general_practice",
                    "question": "Which statement best describes the primary role of "
                    f"{c['name']} in this "
                    "subject?",
                    "options": [
                        ans1,
                        "It is a deprecated configuration that has been phased out.",
                        "It is an internal hardware interrupt that cannot be controlled "
                        "in software.",
                        "It is an optional decorative element with no logical effect.",
                    ],
                    "answer": ans1,
                }
            )
            ans2 = (
                "It establishes structured techniques and constraints applied by advanced topics."
            )
            quiz_items.append(
                {
                    "id": f"q_{c['id']}_2",
                    "concept_id": c["id"],
                    "origin": "general_practice",
                    "question": "In the learning progression of this course, how "
                    f"does {c['name']} support "
                    "subsequent topics?",
                    "options": [
                        ans2,
                        "It completely supersedes and eliminates the need for any other concepts.",
                        "It only operates in simulated sandbox environments without "
                        "practical utility.",
                        "It resets the system state to default values after every execution.",
                    ],
                    "answer": ans2,
                }
            )

    (out_dir / "quiz_items.json").write_text(
        json.dumps(
            {"schema_version": "1.12", "course_id": course_id, "items": quiz_items}, indent=2
        ),
        encoding="utf-8",
    )

    return True


def fast_demo_run(course_id: str, state_dir: Path) -> int:
    """Quick Preview: list the headings in the uploads. Its log says only what it really did."""
    state = _read_state(state_dir) or {}
    state.update(state="running", pid=os.getpid(), started_at=time.time())
    _write_state(state_dir, state)

    out_dir = OUTPUTS / PREVIEW_FOLDER / course_id
    shutil.rmtree(out_dir, ignore_errors=True)  # only ever a preview: real runs are not here
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(state_dir / "pipeline.log", "w", encoding="utf-8") as log:
        log.write("Quick Preview: no AI was used.\n")
        generated = generate_course_from_uploads(course_id, out_dir)
        if generated:
            preview = json.loads((out_dir / "preview.json").read_text(encoding="utf-8"))
            log.write(f"Listed {len(preview['nodes'])} possible topics from the headings.\n")
            log.write(f"Joined them with {len(preview['links'])} links, in heading order.\n")
            cut = preview.get("chunks_truncated")
            if cut:
                log.write(f"Read only {cut['kept']} of {cut['total']} parts of the notes.\n")
        else:
            log.write("No text could be read from the uploaded files.\n")

    code = 0 if generated else 1
    state.update(
        state="succeeded" if generated else "failed", returncode=code, finished_at=time.time()
    )
    _write_state(state_dir, state)
    return code


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
