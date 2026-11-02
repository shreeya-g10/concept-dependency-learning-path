"""Helpers every page uses: course list, contract files, answer log.

Pages read pipeline outputs from outputs/ and fall back to cdlp/shared/examples/,
so every page works before the real pipeline exists.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
import strings as S

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
EXAMPLES = ROOT / "cdlp" / "shared" / "examples"

# Lets pages import cdlp (the learning-path api.py).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Display names for the two built-in courses; any other course id was made from a name
# the student typed, so course_label() turns it back into words.
COURSE_NAMES = {
    "ds101": "Data Structures & Algorithms",
    "ml101": "Introduction to Machine Learning",
}


# A folder in outputs/ is a course only when a finished run left these files in it.
COURSE_FILES = ("concepts.json", "validated_graph.json")


def list_courses(outputs: Path | None = None) -> list[str]:
    """Course ids with a finished run in outputs/ (hidden and partial folders are left out).

    New courses built from the upload page appear automatically. With no outputs at all,
    the built-in courses are listed so the pages still show the example data.
    """
    outputs = outputs or OUTPUTS
    found = (
        sorted(
            p.name
            for p in outputs.iterdir()
            if p.is_dir()
            and not p.name.startswith((".", "_"))
            and all((p / name).is_file() for name in COURSE_FILES)
        )
        if outputs.is_dir()
        else []
    )
    return found or list(COURSE_NAMES)


def course_options() -> list[str]:
    """The course picker's choices: list_courses() plus a course whose first run just started."""
    courses = list_courses()
    active = st.session_state.get("course_id")
    return courses + [active] if active and active not in courses else courses


def course_label(course_id: str) -> str:
    """The name students see. Never shows a raw id for a built-in course."""
    return COURSE_NAMES.get(course_id) or course_id.replace("_", " ").strip().capitalize()


def course_id_from_name(name: str) -> str:
    """'Biology notes' -> 'biology_notes'. May be invalid: check with jobs.valid_course_id()."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40].rstrip("_")


def get_active_course() -> str:
    """The selected course id; before any choice, ds101 if it exists, else the first course."""
    active = st.session_state.get("course_id")
    if active:
        return active
    courses = list_courses()
    return "ds101" if "ds101" in courses else courses[0]


def resolve_path(name: str, course_id: str | None = None) -> Path:
    """Resolve file path checking outputs/<course>/, outputs/, then examples/."""
    course = course_id or get_active_course()
    course_path = OUTPUTS / course / name
    if course_path.exists():
        return course_path
    legacy_path = OUTPUTS / name
    if legacy_path.exists():
        return legacy_path
    return EXAMPLES / name


@st.cache_data
def _read_contract(path: str, modified: int) -> dict | list:
    """Cached per file and version: a course switch or a new run can never show old data."""
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def load(name: str, course_id: str | None = None) -> dict | list:
    """Load a contract file by name, e.g. load('validated_graph.json')."""
    path = resolve_path(name, course_id=course_id)
    return _read_contract(str(path), path.stat().st_mtime_ns)


def using_examples(name: str, course_id: str | None = None) -> bool:
    course = course_id or get_active_course()
    return not ((OUTPUTS / course / name).exists() or (OUTPUTS / name).exists())


def concept_names(course_id: str | None = None) -> dict[str, str]:
    return {c["id"]: c["name"] for c in load("concepts.json", course_id=course_id)["concepts"]}


def get_chunks_map(course_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Return a mapping of chunk_id -> chunk dict."""
    try:
        chunks = load("chunks.jsonl", course_id=course_id)
        if isinstance(chunks, list):
            return {c["chunk_id"]: c for c in chunks if isinstance(c, dict) and "chunk_id" in c}
    except Exception:
        pass
    return {}


def citation(doc: str, page: int | str) -> str:
    """'📄 file.pdf, page 3'. MD and DOCX chunks count sections, not pages (extraction/parse.py)."""
    is_section = str(doc).lower().endswith((".md", ".docx"))
    return (S.WHERE_SECTION if is_section else S.WHERE_PAGE).format(doc=doc, page=page)


def _demo_subset(course_id: str | None = None) -> dict | None:
    try:
        graph = load("validated_graph.json", course_id=course_id)
    except (OSError, ValueError):
        return None
    return (graph.get("subset") or None) if isinstance(graph, dict) else None


def demo_subset_note(course_id: str | None = None) -> str | None:
    """Plain-words notice when the course's validated graph covers only a demo subset."""
    subset = _demo_subset(course_id)
    return S.DEMO_NOTICE.format(n=subset["n"], of=subset["of"]) if subset else None


def demo_subset_short(course_id: str | None = None) -> str | None:
    """The one-line notice for student pages. Same check as demo_subset_note."""
    subset = _demo_subset(course_id)
    return S.DEMO_NOTICE_SHORT.format(n=subset["n"], of=subset["of"]) if subset else None


def demo_subset_rule(course_id: str | None = None) -> str | None:
    """The written rule that picked the demo subset (shown on the teacher pages)."""
    subset = _demo_subset(course_id)
    return subset.get("selection") if subset else None


# ---- anonymous answer log ---------------------------------------------------------
# Every quick-check answer is appended to outputs/<course>/student_answers.json
# (contract student_answers.json), the input of root-cause tracing (pipeline.py runs
# cdlp.root_cause when the file exists) and of the real-student study. The student is
# identified only by a random per-browser-session id: no name, login or IP is stored.


def session_id() -> str:
    """Random anonymous id, stable for this browser session (survives a quiz restart)."""
    if "anon_session_id" not in st.session_state:
        st.session_state.anon_session_id = f"anon_{secrets.token_hex(6)}"
    return st.session_state.anon_session_id


def answers_path(course_id: str) -> Path:
    return OUTPUTS / course_id / "student_answers.json"


def log_answer(course_id: str, row: dict) -> Path:
    """Append one answer {student_id, item_id, concept_id, answer, correct} to the log.

    The file is validated against the contract (cdlp.shared.io) and replaced atomically,
    so a crash never leaves half a file. Concurrent sessions are not locked against each
    other (fine for a classroom study on one server; see website/README.md).
    """
    from cdlp.shared.validate import check

    path = answers_path(course_id)
    doc = {"schema_version": "1.1", "course_id": course_id, "answers": []}
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
    doc["answers"].append(row)
    errors = check(doc, "student_answers")
    if errors:
        raise ValueError("student_answers.json breaks the contract:\n  " + "\n  ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path
