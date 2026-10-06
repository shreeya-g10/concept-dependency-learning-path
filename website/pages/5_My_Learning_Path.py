"""Owner: Shrestha. Short adaptive quiz, then the student's personal learning path.

Uses only cdlp/learning_path/api.py (the one public API the website may import).
"""

import streamlit as st
from common import concept_names, load, page_header

from cdlp.learning_path import api

page_header("My Learning Path", "Shrestha", "learning_path.json")

names = concept_names()
target = st.selectbox("What do you want to learn?", list(names), format_func=names.get)

# TODO(Shrestha): live quiz loop with api.next_question(...) and api.update_mastery(...).
mastery: dict[str, float] = {}
for step_no, step in enumerate(
    api.personalized_path(load("validated_graph.json"), mastery, target), 1
):
    st.markdown(f"**{step_no}. {names[step['concept_id']]}** — {step['why']}")
