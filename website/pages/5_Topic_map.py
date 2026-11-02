"""Topic map: learn before -> this topic -> learn next, as tappable cards.

Works on a phone and on weak internet: the full picture sends the whole drawing library, so
it stays behind a button. Everything here reads the ACCEPT links of validated_graph.json
directly; the machine-written `reason` of a link is for teachers and is not shown.
"""

from __future__ import annotations

import common
import streamlit as st
import streamlit.components.v1 as components
import strings as S
import ui

ui.page_header(S.MAP_TITLE, S.MAP_INTRO, source_file="validated_graph.json")

names = common.concept_names()
concepts = {c["id"]: c for c in common.load("concepts.json")["concepts"]}
graph_data = common.load("validated_graph.json")
accepted = [e for e in graph_data.get("edges", []) if e.get("decision") == "ACCEPT"]


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def strength_words(edge: dict) -> str:
    return S.MAP_NEED_LABEL if edge.get("strength", "hard") == "hard" else S.MAP_HELP_LABEL


if not names:
    ui.empty_state(S.MAP_EMPTY, S.MAP_EMPTY_NEXT, action=S.TOPICS_ADD, page="add", icon="📄")
    st.stop()

topic_ids = sorted(names, key=lambda c: names[c].lower())
linked = {end for edge in accepted for end in (edge["source"], edge["target"])}

# The topic in focus: kept under a plain key, because widget state does not survive other pages.
if st.session_state.get("map_focus") not in names:
    remembered = st.session_state.get("study_target")
    with_links = [c for c in topic_ids if c in linked]
    fallback = with_links[0] if with_links else topic_ids[0]
    st.session_state.map_focus = remembered if remembered in names else fallback
st.session_state.map_pick = st.session_state.map_focus


def focus_on(concept_id: str) -> None:
    st.session_state.map_focus = concept_id


def focus_on_picked() -> None:
    st.session_state.map_focus = st.session_state.map_pick


st.selectbox(S.MAP_PICK, topic_ids, key="map_pick", format_func=name, on_change=focus_on_picked)
focus = st.session_state.map_focus
before = sorted((e for e in accepted if e["target"] == focus), key=lambda e: name(e["source"]))
after = sorted((e for e in accepted if e["source"] == focus), key=lambda e: name(e["target"]))


def card(concept_id: str, where: str) -> None:
    st.button(
        name(concept_id),
        key=f"{where}_{concept_id}",
        width="stretch",
        on_click=focus_on,
        args=(concept_id,),
    )


if before:
    st.markdown(S.MAP_BEFORE)
    for edge in before:
        card(edge["source"], "before")
        st.caption(strength_words(edge))
    st.markdown(S.MAP_ARROW)

with st.container(border=True):
    st.markdown(S.MAP_THIS_TOPIC.format(topic=name(focus)))
    if concepts.get(focus, {}).get("description"):
        st.write(concepts[focus]["description"])
    sources = concepts.get(focus, {}).get("sources", [])
    if sources:
        st.caption(common.citation(sources[0].get("doc", ""), sources[0].get("page", "")))

if after:
    st.markdown(S.MAP_ARROW)
    st.markdown(S.MAP_AFTER)
    for edge in after:
        card(edge["target"], "after")

# Never say "nothing comes first": a missing link may only mean we have not found it yet.
if not before and not after:
    st.info(S.MAP_NO_LINKS, icon="ℹ️")
else:
    if not before:
        st.caption(S.MAP_NOTHING_BEFORE)
    if not after:
        st.caption(S.MAP_NOTHING_AFTER)

if before or after:
    st.markdown(S.MAP_LINKS)
for edge in [*before, *after]:
    with st.expander(f"{name(edge['source'])} → {name(edge['target'])}"):
        for ev in edge.get("evidence", []):
            if ev.get("quote"):
                st.markdown(f"> {ev['quote']}")
            st.caption(common.citation(ev.get("doc", ""), ev.get("page", "")))

st.divider()
showing = st.session_state.get("map_full", False)
if ui.action_button(
    S.MAP_HIDE_FULL if showing else S.MAP_SEE_FULL, icon="🗺️", primary=False, key="map_full_button"
):
    st.session_state.map_full = not showing
    st.rerun()

if showing and not accepted:
    st.info(S.MAP_NO_LINKS_AT_ALL, icon="ℹ️")
elif showing:
    try:
        from pyvis.network import Network
    except ImportError:
        Network = None

    st.caption(S.MAP_PICTURE_NOTE)
    if Network is None:
        for edge in accepted:
            st.markdown(
                S.MAP_LIST_ONLY.format(
                    source=name(edge["source"]),
                    target=name(edge["target"]),
                    strength=strength_words(edge),
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
        for concept_id in sorted(linked):
            network.add_node(
                concept_id, label=name(concept_id), title=name(concept_id), color="#8DB9E8", size=22
            )
        for edge in accepted:
            network.add_edge(
                edge["source"],
                edge["target"],
                arrows="to",
                color="#14202B",
                dashes=edge.get("strength", "hard") != "hard",
                title=strength_words(edge),
            )
        network.barnes_hut()
        components.html(network.generate_html(), height=540, scrolling=False)
        st.caption(S.MAP_KEY)
