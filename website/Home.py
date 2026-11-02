"""Website entry point (initial code: Vaidehi).

streamlit run website/Home.py
"""

from __future__ import annotations

import streamlit as st
from common import demo_subset_note, load, render_sidebar, using_examples

st.set_page_config(
    page_title="Concept Dependency Learning Path",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_sidebar()

st.title("🎓 Concept Dependency Learning Path")
st.subheader("Agent-Validated Prerequisite Graphs for Student-Adaptive Learning Paths")

st.markdown(
    """
> *"I don't understand AVL Trees."*  
> A generic system says "revise AVL Trees". This system runs a short adaptive quiz, finds
> that the student knows binary trees but breaks the BST ordering rule, and recommends
> **BST ordering rule $\\rightarrow$ AVL Trees**, with the lecture page for each step.  
> *(Illustrative example.)*
"""
)

st.divider()

# Pipeline Statistics Banner
graph = load("validated_graph.json")
concepts_data = load("concepts.json")
concepts_list = concepts_data.get("concepts", []) if isinstance(concepts_data, dict) else []
edges = graph.get("edges", []) if isinstance(graph, dict) else []
accepted_edges = sum(1 for e in edges if e.get("decision") == "ACCEPT")
review_edges = sum(1 for e in edges if e.get("decision") == "HUMAN_REVIEW")
rejected_edges = sum(1 for e in edges if e.get("decision") == "REJECT")

status_badge = (
    "🟢 Live Pipeline (`outputs/`)"
    if not using_examples("validated_graph.json")
    else "🟡 Shared Examples (`cdlp/shared/examples/`)"
)
st.markdown(f"**Current Status:** {status_badge}")
if note := demo_subset_note():
    st.warning(note)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Concepts Extracted", len(concepts_list))
col2.metric("Accepted Prerequisites", accepted_edges)
col3.metric("Under Human Review", review_edges)
col4.metric("Rejected Edges", rejected_edges)

st.divider()

# System Architecture & Flow
st.markdown("### 🗺️ Pipeline Architecture")
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.info("**1. Course Material**\n\nPDFs / PPTX parsed into chunks & canonical concepts.")
with c2:
    st.info("**2. Proposed Dependencies**\n\nCandidate filtering and LLM pairwise hypothesis.")
with c3:
    st.info("**3. Validation Agent**\n\nSimulated learner necessity test & semantic checks.")
with c4:
    st.info("**4. Knowledge Graph**\n\nValidated DAG & transitive reduction.")
with c5:
    st.info("**5. My Learning Path**\n\nAdaptive diagnostic quiz and personalized path.")

st.divider()

# Research contributions: kept in sync with "What's new" in README.md
st.markdown("### 🔬 What's new")
st.caption(
    "We don't claim prerequisite discovery itself is new. "
    "Results are reported in the paper once experiments complete; no numbers are shown here."
)
exp1, exp2, exp3 = st.columns(3)

with exp1:
    st.markdown("#### 1. Validation agent")
    st.write(
        "Before an edge $A \\rightarrow B$ enters the graph, a separate validator model checks "
        "it against the course material (evidence), for teaching sense (semantic) and for graph "
        "consistency (cycles, redundant shortcuts), then decides ACCEPT / REJECT / HUMAN_REVIEW. "
        "An experimental necessity test (an LLM plays a student who does not know $A$) is "
        "recorded but does not affect decisions: in our first runs its score was unstable."
    )

with exp2:
    st.markdown("#### 2. Graph-guided adaptive diagnosis")
    st.write(
        "The validated graph chooses the most informative next quiz question: a correct answer "
        "on BST implies its prerequisites are known. The aim is to find a student's gaps with "
        "fewer questions than testing every concept (not yet measured)."
    )

with exp3:
    st.markdown("#### 3. Personalized, explainable paths")
    st.write(
        "One course graph, a different path per student: the target's prerequisites minus what "
        "the student has mastered, in dependency order. Every step cites the lecture and page "
        "it comes from."
    )

st.divider()

st.markdown("### 👥 Team")
st.markdown(
    """
- **Shreeya (@shreeya-g10)**: maintainer; validation agent, root-cause tracing, benchmarks
- **Vaidehi (@vkumaw)**: extraction, learning path, website shell, gold labels, root-cause test set
- **Sneha (@snehadebnath26)**: initial discovery code
- **Shrestha (@shrestha035)**: initial learning-path code

*Built with Python, Streamlit, PyMuPDF, python-pptx, NetworkX, and Ollama. Free & local.*
"""
)
