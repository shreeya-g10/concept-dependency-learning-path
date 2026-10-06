"""Owner: Shreeya. Shows each validation decision with its checks, evidence and reason."""

import streamlit as st
from common import concept_names, load, page_header

page_header("Validation Agent", "Shreeya", "validated_graph.json")

names = concept_names()
decision = st.radio("Show", ["ACCEPT", "REJECT", "HUMAN_REVIEW"], horizontal=True)
for e in load("validated_graph.json")["edges"]:
    if e["decision"] != decision:
        continue
    with st.expander(
        f"{names.get(e['source'], e['source'])} → {names.get(e['target'], e['target'])}"
    ):
        st.write(e["reason"])
        st.json(e["checks"])
        st.caption(f"necessity gap: {e.get('necessity_gap')} · confidence: {e['confidence']}")
        for ev in e["evidence"]:
            st.markdown(f"> {ev.get('quote', '')}  \n_{ev.get('doc', '')} p.{ev.get('page', '')}_")
# TODO(Shreeya): necessity-test transcript, ablation results chart.
