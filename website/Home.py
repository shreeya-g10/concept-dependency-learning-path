"""Website entry point. Owner: Vaidehi.

streamlit run website/Home.py
"""

import streamlit as st
from common import load

st.set_page_config(page_title="Concept Dependency Learning Path", layout="wide")

st.title("Concept Dependency Learning Path")
st.write(
    "Course material in, a validated prerequisite graph out, "
    "and a different learning path for every student."
)

graph = load("validated_graph.json")
accepted = sum(e["decision"] == "ACCEPT" for e in graph["edges"])
col1, col2, col3 = st.columns(3)
col1.metric("Concepts", len(graph["nodes"]))
col2.metric("Proposed edges", len(graph["edges"]))
col3.metric("Accepted edges", accepted)

st.markdown(
    """
**Pages**
1. Course Material: concepts extracted from the lectures
2. Proposed Dependencies: what the LLM suggested
3. Validation Agent: what was accepted, rejected or sent for review, and why
4. Knowledge Graph: the validated graph
5. My Learning Path: a short quiz, then your personal path
"""
)
# TODO(Vaidehi): course selector, styling, About page, deployment.
