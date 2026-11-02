"""Helpers every page uses.

Pages read pipeline outputs from outputs/ and fall back to cdlp/shared/examples/,
so every page works before the real pipeline exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
EXAMPLES = ROOT / "cdlp" / "shared" / "examples"

# Lets pages import cdlp (the learning-path api.py).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Display names for the two built-in courses; any other course shows its id.
COURSE_NAMES = {
    "ds101": "Data Structures & Algorithms",
    "ml101": "Introduction to Machine Learning",
}


def list_courses(outputs: Path | None = None) -> list[str]:
    """Course ids with a folder in outputs/ (hidden folders such as outputs/.jobs/ excluded).

    New courses built from page 1 appear automatically. With no outputs at all, the
    built-in courses are listed so the pages still show the example data.
    """
    outputs = outputs or OUTPUTS
    found = (
        sorted(
            p.name for p in outputs.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
        )
        if outputs.is_dir()
        else []
    )
    return found or list(COURSE_NAMES)


def get_active_course() -> str:
    """Return the currently selected course id (default: ds101)."""
    return st.session_state.get("course_id", "ds101")


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
def load(name: str, course_id: str | None = None) -> dict | list:
    """Load a contract file by name, e.g. load('validated_graph.json')."""
    path = resolve_path(name, course_id=course_id)
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return json.loads(path.read_text(encoding="utf-8"))


def using_examples(name: str, course_id: str | None = None) -> bool:
    course = course_id or get_active_course()
    return not ((OUTPUTS / course / name).exists() or (OUTPUTS / name).exists())


def concept_names(course_id: str | None = None) -> dict[str, str]:
    return {c["id"]: c["name"] for c in load("concepts.json", course_id=course_id)["concepts"]}


@st.cache_data
def get_chunks_map(course_id: str | None = None) -> dict[str, dict[str, Any]]:
    """Return a mapping of chunk_id -> chunk dict."""
    try:
        chunks = load("chunks.jsonl", course_id=course_id)
        if isinstance(chunks, list):
            return {c["chunk_id"]: c for c in chunks if isinstance(c, dict) and "chunk_id" in c}
    except Exception:
        pass
    return {}


def page_header(title: str, owner: str, source_file: str) -> None:
    st.title(title)
    course = get_active_course()
    is_example = using_examples(source_file, course_id=course)
    badge = "🟡 Example Mock Data" if is_example else f"🟢 Live Pipeline Data (outputs/{course}/)"
    st.caption(f"Owner: **{owner}** · Course: `{course}` · Source: `{source_file}` · {badge}")


def render_sidebar():
    """Render common course selector and navigation info in sidebar."""
    with st.sidebar:
        st.markdown("### 📚 Course Selection")
        courses = list_courses()
        active = st.session_state.get("course_id")
        if active and active not in courses:  # e.g. a course whose first run just started
            courses.append(active)
        index = courses.index(active) if active in courses else 0
        course_id = st.selectbox(
            "Active Course",
            courses,
            index=index,
            format_func=lambda c: f"{c} — {COURSE_NAMES[c]}" if c in COURSE_NAMES else c,
        )
        st.session_state["course_id"] = course_id
        st.caption(f"Target Course ID: `{course_id}`")
        st.divider()
        st.markdown("### 🔍 System Info")
        st.caption("Verify, Diagnose, Adapt System")
        st.caption("Gen AI Lab — Educational Prerequisite Graphs")
