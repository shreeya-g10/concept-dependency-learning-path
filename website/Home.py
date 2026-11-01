"""Website entry point. Owner: Vaidehi.

streamlit run website/Home.py
"""

from __future__ import annotations

import streamlit as st
from common import load, render_sidebar, using_examples

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
> A generic platform tells the student to re-watch the AVL lecture.  
> Our system runs a short graph-guided adaptive quiz, identifies that the student knows
> binary trees but breaks the BST ordering property, and recommends:  
> **BST Ordering Rule (Lec 7, p.18) $\\rightarrow$ AVL Trees (Lec 9, p.4)**.
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
    st.info("**5. My Learning Path**\n\nAdaptive diagnostic quiz and personalized shortest path.")

st.divider()

# Novel Research Contributions
st.markdown("### 🔬 Three Novel Contributions")
exp1, exp2, exp3 = st.columns(3)

with exp1:
    st.markdown("#### 1. Necessity-Testing Validation Agent")
    st.write(
        "Before edge $A \\rightarrow B$ enters the graph, a simulated learner plays a student "
        "who lacks $A$ and tries problems on $B$. The score gap provides empirical evidence."
    )

with exp2:
    st.markdown("#### 2. Graph-Guided Adaptive Diagnosis")
    st.write(
        "Prerequisite links connect concepts. A correct answer on BST implies binary trees "
        "are known, narrowing uncertainty across prerequisite chains via adaptive inquiry."
    )

with exp3:
    st.markdown("#### 3. Root-Cause Gap Tracing")
    st.write(
        "Instead of binary scoring, wrong answers are analyzed against prerequisite concepts "
        "to trace the exact cognitive root cause (e.g. failing AVL because of BST ordering)."
    )

st.divider()

# Team & Project Details
st.markdown("### 👥 Research Team & Implementation")
st.markdown(
    """
- **Vaidehi (@vkumaw)**: Parsing, Concept Extraction, Gold Standard Evaluation & Website Shell
- **Sneha (@snehadebnath26)**: Candidate Generation, Dependency Discovery & Simulated Learners
- **Shreeya (@shreeya-g10, Lead)**: Validation Agent, Necessity Testing & System Scaffolding
- **Shrestha (@shrestha035)**: Knowledge Graph, Adaptive Diagnosis & Personalized Learning Paths

*Built with Python, Streamlit, PyMuPDF, python-pptx, NetworkX, and Ollama. Free & local.*
"""
)
