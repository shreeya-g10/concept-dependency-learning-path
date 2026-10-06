"""Owner: Vaidehi. Shows concepts and where they come from in the lectures."""

import streamlit as st
from common import load, page_header

page_header("Course Material", "Vaidehi", "concepts.json")

for c in load("concepts.json")["concepts"]:
    src = ", ".join(f"{s['doc']} p.{s['page']}" for s in c["sources"])
    aliases = f" (also: {', '.join(c['aliases'])})" if c.get("aliases") else ""
    st.markdown(f"**{c['name']}**{aliases} — {c.get('description', '')}  \n_{src}_")
# TODO(Vaidehi): search box, show source chunk text, upload new course material.
