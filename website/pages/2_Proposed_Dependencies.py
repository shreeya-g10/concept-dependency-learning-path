"""Owner: Sneha. Shows the prerequisite edges the LLM proposed, before validation."""

import streamlit as st
from common import concept_names, load, page_header

page_header("Proposed Dependencies", "Sneha", "relationships.json")

names = concept_names()
st.dataframe(
    [
        {
            "from": names.get(r["source"], r["source"]),
            "to": names.get(r["target"], r["target"]),
            "strength": r["strength"],
            "confidence": r["confidence"],
            "evidence chunks": len(r["evidence"]),
        }
        for r in load("relationships.json")["relationships"]
    ],
    width="stretch",
)
# TODO(Sneha): filter by concept, show evidence quotes, candidate-filter stats.
