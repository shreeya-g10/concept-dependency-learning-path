"""Helpers every page uses. Owner: Vaidehi. Everyone may use it; only Vaidehi edits it.

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


@st.cache_data
def load(name: str) -> dict | list:
    """Load a contract file by name, e.g. load("validated_graph.json")."""
    path = OUTPUTS / name if (OUTPUTS / name).exists() else EXAMPLES / name
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return json.loads(path.read_text(encoding="utf-8"))


def using_examples(name: str) -> bool:
    return not (OUTPUTS / name).exists()


def concept_names() -> dict[str, str]:
    return {c["id"]: c["name"] for c in load("concepts.json")["concepts"]}


@st.cache_data
def get_chunks_map() -> dict[str, dict[str, Any]]:
    """Return a mapping of chunk_id -> chunk dict."""
    try:
        chunks = load("chunks.jsonl")
        if isinstance(chunks, list):
            return {c["chunk_id"]: c for c in chunks if isinstance(c, dict) and "chunk_id" in c}
    except Exception:
        pass
    return {}


def page_header(title: str, owner: str, source_file: str) -> None:
    st.title(title)
    is_example = using_examples(source_file)
    badge = "🟡 Example Mock Data" if is_example else "🟢 Live Pipeline Data (outputs/)"
    st.caption(f"Owner: **{owner}** · Source: `{source_file}` · {badge}")


def render_sidebar():
    """Render common course selector and navigation info in sidebar."""
    with st.sidebar:
        st.markdown("### 📚 Course Selection")
        courses = [
            "ds101 — Data Structures & Algorithms",
            "ml101 — Introduction to Machine Learning (Demo)",
        ]
        selected_course = st.selectbox("Active Course", courses, index=0)
        st.caption(f"Target Course ID: `{selected_course.split(' ')[0]}`")
        st.divider()
        st.markdown("### 🔍 System Info")
        st.caption("Verify, Diagnose, Adapt System")
        st.caption("Gen AI Lab — Educational Prerequisite Graphs")
