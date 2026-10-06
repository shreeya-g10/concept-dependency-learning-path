"""Owner: Shrestha. Interactive view of the validated graph (ACCEPT edges only)."""

import streamlit as st
from common import concept_names, load, page_header

page_header("Knowledge Graph", "Shrestha", "validated_graph.json")

names = concept_names()
for e in load("validated_graph.json")["edges"]:
    if e["decision"] == "ACCEPT":
        st.markdown(f"- {names[e['source']]} → **{names[e['target']]}** ({e['strength']})")
# TODO(Shrestha): replace the list with an interactive pyvis graph; click a concept to see
# its prerequisites, dependents and evidence.
