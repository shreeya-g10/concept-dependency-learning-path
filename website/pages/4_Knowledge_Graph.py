
"""Owner: Shrestha. Interactive validated prerequisite graph."""

import streamlit as st
import streamlit.components.v1 as components
import networkx as nx
from pyvis.network import Network

from common import concept_names, load, page_header


page_header("Knowledge Graph", "Shrestha", "validated_graph.json")

data = load("validated_graph.json")
names = concept_names()

graph = nx.DiGraph()

# Add concepts
for node in data["nodes"]:
    concept_id = node["id"]
    graph.add_node(concept_id)

# Add only accepted prerequisite relationships
for edge in data["edges"]:
    if edge.get("decision") == "ACCEPT":
        graph.add_edge(
            edge["source"],
            edge["target"],
            **{
                key: value
                for key, value in edge.items()
                if key not in ("source", "target")
            },
        )

st.subheader("Interactive Prerequisite Graph")

st.caption(
    "Arrows point from a prerequisite to the concept "
    "that depends on it. Drag nodes, zoom, or hover "
    "to explore relationships."
)

network = Network(
    height="550px",
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

    edge_color = (
        "#E67E22" if strength == "hard" else "#27AE60"
    )

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
    height=570,
    scrolling=False,
)

st.caption("🟠 Hard prerequisite  |  🟢 Soft prerequisite")

st.divider()

# Concept exploration
st.subheader("Explore a Concept")

concept_ids = sorted(
    graph.nodes,
    key=lambda concept: names.get(concept, concept),
)

selected = st.selectbox(
    "Select a concept",
    concept_ids,
    format_func=lambda concept: names.get(concept, concept),
)

if selected:
    prereqs = nx.ancestors(graph, selected)
    deps = nx.descendants(graph, selected)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Prerequisites**")

        if prereqs:
            for concept in sorted(prereqs):
                st.write(
                    "•", names.get(concept, concept)
                )
        else:
            st.info("No prerequisites.")

    with col2:
        st.markdown("**Dependent Concepts**")

        if deps:
            for concept in sorted(deps):
                st.write(
                    "•", names.get(concept, concept)
                )
        else:
            st.info("No dependent concepts.")

    st.divider()

    st.subheader("Dependency Evidence")

    incoming = list(graph.in_edges(selected, data=True))
    outgoing = list(graph.out_edges(selected, data=True))

    if not incoming and not outgoing:
        st.info("No accepted dependency evidence.")

    for source, target, attributes in incoming + outgoing:
        with st.expander(
            f"{names.get(source, source)} → "
            f"{names.get(target, target)}"
        ):
            st.write(
                "**Strength:**",
                attributes.get("strength", "Not specified"),
            )

            evidence = attributes.get("evidence", [])

            if evidence:
                st.write("**Evidence:**")
                st.json(evidence)
            else:
                st.write("No evidence available.")
