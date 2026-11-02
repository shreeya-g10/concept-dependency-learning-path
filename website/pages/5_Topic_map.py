"""Topic map: which topics come before and after a topic, and an optional picture.

The picture is off by default: it sends the whole drawing library, which is slow on weak
internet. The lists carry the same information.
"""

from __future__ import annotations

import common
import streamlit as st
import streamlit.components.v1 as components
import strings as S
import ui

from cdlp.learning_path.graph import ancestors, descendants, load_graph

try:
    from pyvis.network import Network
except ImportError:
    Network = None

ui.page_header(S.MAP_TITLE, S.MAP_INTRO, source_file="validated_graph.json")

names = common.concept_names()
graph = load_graph(common.load("validated_graph.json"))


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def strength_words(attributes: dict) -> str:
    return S.MAP_NEED_LABEL if attributes.get("strength", "hard") == "hard" else S.MAP_HELP_LABEL


if not graph.nodes:
    ui.empty_state(S.MAP_EMPTY, S.MAP_EMPTY_NEXT, action=S.TOPICS_ADD, page="add", icon="📄")
    st.stop()

selected = st.selectbox(S.MAP_PICK, sorted(graph.nodes, key=name), format_func=name)

st.markdown(S.MAP_BEFORE)
before = sorted(name(c) for c in ancestors(graph, selected))
st.markdown("\n".join(f"- {n}" for n in before) or S.MAP_NOTHING_BEFORE)

st.markdown(S.MAP_AFTER)
after = sorted(name(c) for c in descendants(graph, selected))
st.markdown("\n".join(f"- {n}" for n in after) or S.MAP_NOTHING_AFTER)

st.markdown(S.MAP_LINKS)
links = [*graph.in_edges(selected, data=True), *graph.out_edges(selected, data=True)]
if not links:
    st.info(S.MAP_NO_LINKS, icon="ℹ️")
for source, target, attributes in links:
    with st.expander(f"{name(source)} → {name(target)}"):
        st.write(strength_words(attributes))
        if attributes.get("rationale"):
            st.markdown(S.MAP_REASON.format(reason=attributes["rationale"]))
        for ev in attributes.get("evidence", []):
            if ev.get("quote"):
                st.markdown(f"> {ev['quote']}")
            st.caption(common.citation(ev.get("doc", ""), ev.get("page", "")))

if st.toggle(S.MAP_SHOW_PICTURE):
    st.caption(S.MAP_PICTURE_NOTE)
    if Network is None:
        for source, target, attributes in graph.edges(data=True):
            st.markdown(
                S.MAP_LIST_ONLY.format(
                    source=name(source), target=name(target), strength=strength_words(attributes)
                )
            )
    else:
        network = Network(
            height="520px",
            width="100%",
            directed=True,
            bgcolor="#ffffff",
            font_color="#14202B",
            cdn_resources="in_line",
        )
        for concept_id in graph.nodes:
            network.add_node(
                concept_id, label=name(concept_id), title=name(concept_id), color="#8DB9E8", size=22
            )
        for source, target, attributes in graph.edges(data=True):
            network.add_edge(
                source,
                target,
                arrows="to",
                color="#14202B",
                dashes=attributes.get("strength", "hard") != "hard",
                title=strength_words(attributes),
            )
        network.barnes_hut()
        components.html(network.generate_html(), height=540, scrolling=False)
        st.caption(S.MAP_KEY)
