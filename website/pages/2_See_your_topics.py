"""Step 2: the topics found in the course material, with search and source pages."""

from __future__ import annotations

import common
import streamlit as st
import strings as S
import ui

ui.page_header(S.TOPICS_TITLE, S.TOPICS_INTRO, step=2, source_file="concepts.json")

concepts_data = common.load("concepts.json")
concepts = concepts_data.get("concepts", []) if isinstance(concepts_data, dict) else []
if not concepts:
    ui.empty_state(S.TOPICS_NONE, S.TOPICS_NONE_NEXT, action=S.TOPICS_ADD, page="add", icon="📄")
    st.stop()

ui.action_button(S.TOPICS_NEXT, page="quiz", icon="➡️")

chunks_map = common.get_chunks_map()
query = st.text_input(S.TOPICS_SEARCH, value="").lower()
all_docs = sorted({src["doc"] for c in concepts for src in c.get("sources", []) if "doc" in src})
selected_doc = st.selectbox(S.TOPICS_FILTER, [S.TOPICS_ALL_FILES, *all_docs])


def matches(concept: dict) -> bool:
    text = [concept.get("name", ""), *concept.get("aliases", []), concept.get("description", "")]
    in_doc = selected_doc == S.TOPICS_ALL_FILES or any(
        s.get("doc") == selected_doc for s in concept.get("sources", [])
    )
    return in_doc and (not query or any(query in t.lower() for t in text))


filtered = [c for c in concepts if matches(c)]
st.markdown(S.TOPICS_COUNT.format(shown=len(filtered), total=len(concepts)))
if not filtered:
    st.info(S.TOPICS_NO_MATCH, icon="ℹ️")

for concept in filtered:
    sources = concept.get("sources", [])
    with st.container(border=True):
        st.markdown(f"### {concept.get('name', '')}")
        if concept.get("aliases"):
            st.caption(S.TOPICS_ALIASES.format(aliases=", ".join(concept["aliases"])))
        st.write(concept.get("description", ""))
        if not sources:
            continue
        st.markdown(
            " · ".join(common.citation(s.get("doc", ""), s.get("page", 1)) for s in sources)
        )
        with st.expander(S.TOPICS_SOURCE_TEXT):
            for source in sources:
                st.markdown(common.citation(source.get("doc", ""), source.get("page", 1)))
                chunk = chunks_map.get(source.get("chunk_id", ""))
                if chunk and "text" in chunk:
                    st.info(chunk["text"])
                else:
                    st.caption(S.TOPICS_TEXT_MISSING)
