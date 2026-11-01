"""Owner: Vaidehi (inherited from Shrestha). Interactive validated prerequisite graph."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from common import concept_names, load, page_header, render_sidebar

from cdlp.learning_path.graph import ancestors, descendants, load_graph

try:
    from pyvis.network import Network
except ImportError:
    Network = None

page_header("Knowledge Graph", "Vaidehi", "validated_graph.json")
render_sidebar()

data = load("validated_graph.json")
names = concept_names()
graph = load_graph(data)

st.subheader("Interactive Prerequisite Graph")

st.caption(
    "Arrows point from a prerequisite to the concept that depends on it. "
    "Drag nodes, zoom, or hover to explore relationships."
)

if len(graph.nodes) > 0:
    if Network is not None:
        network = Network(
            height="520px",
            width="100%",
            directed=True,
            bgcolor="#ffffff",
            font_color="#222222",
            cdn_resources="in_line",
        )

        for concept_id in graph.nodes:
            network.add_node(
                concept_id,
                label=names.get(concept_id, concept_id),
                title=names.get(concept_id, concept_id),
                color="#4F8EF7",
                size=22,
            )

        for source, target, attributes in graph.edges(data=True):
            strength = attributes.get("strength", "hard")
            edge_color = "#E67E22" if strength == "hard" else "#27AE60"
            network.add_edge(
                source,
                target,
                arrows="to",
                color=edge_color,
                title=f"Dependency: {strength}",
            )

        network.barnes_hut()

        components.html(
            network.generate_html(),
            height=540,
            scrolling=False,
        )

        st.caption("🟠 Hard prerequisite  |  🟢 Soft prerequisite")
    else:
        st.info("Showing graph relationships:")
        for source, target, attributes in graph.edges(data=True):
            strength = attributes.get("strength", "hard")
            st.markdown(
                f"- {names.get(source, source)} → **{names.get(target, target)}** ({strength})"
            )
else:
    st.info("No accepted prerequisite relationships to visualize.")

st.divider()

# Concept exploration
st.subheader("Explore Concept Dependencies")

concept_ids = sorted(
    graph.nodes,
    key=lambda c: names.get(c, c),
)

if concept_ids:
    selected = st.selectbox(
        "Select a concept to inspect",
        concept_ids,
        format_func=lambda c: names.get(c, c),
    )

    if selected:
        prereqs = ancestors(graph, selected)
        deps = descendants(graph, selected)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### ⬅️ Prerequisites (Ancestors)")
            if prereqs:
                for concept in sorted(prereqs):
                    st.write("•", names.get(concept, concept))
            else:
                st.info("No upstream prerequisites (Root concept).")

        with col2:
            st.markdown("#### ➡️ Dependent Concepts (Descendants)")
            if deps:
                for concept in sorted(deps):
                    st.write("•", names.get(concept, concept))
            else:
                st.info("No downstream dependent concepts (Leaf concept).")

        st.divider()

        st.subheader("Dependency Evidence & Validation")

        incoming = list(graph.in_edges(selected, data=True))
        outgoing = list(graph.out_edges(selected, data=True))

        if not incoming and not outgoing:
            st.info("No accepted dependency evidence records for this node.")

        for source, target, attributes in incoming + outgoing:
            with st.expander(f"{names.get(source, source)} → {names.get(target, target)}"):
                st.write("**Strength:**", attributes.get("strength", "Not specified"))
                st.write("**Validation Decision:**", attributes.get("decision", "ACCEPT"))
                evidence = attributes.get("evidence", [])
                if evidence:
                    st.write("**Evidence Excerpts:**")
                    st.json(evidence)
                if "rationale" in attributes:
                    st.write("**Rationale:**", attributes["rationale"])
