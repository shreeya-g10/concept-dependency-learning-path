"""Helpers every page uses. Owner: Vaidehi. Everyone may use it; only Vaidehi edits it.

Pages read pipeline outputs from outputs/ and fall back to cdlp/shared/examples/,
so every page works before the real pipeline exists.
"""

import json
import sys
from pathlib import Path

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
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return json.loads(path.read_text())


def using_examples(name: str) -> bool:
    return not (OUTPUTS / name).exists()


def concept_names() -> dict[str, str]:
    return {c["id"]: c["name"] for c in load("concepts.json")["concepts"]}


def page_header(title: str, owner: str, source_file: str) -> None:
    st.title(title)
    note = " · showing example data" if using_examples(source_file) else ""
    st.caption(f"Owner: {owner} · data: {source_file}{note}")
