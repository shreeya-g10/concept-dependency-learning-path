"""Step 2: the topics found in the notes, most-used first, a few at a time.

"Most-used" counts the different places (file and page) a topic was found in. Source text
stays behind a button: it is only sent to the browser when a student asks for it.
"""

from __future__ import annotations

import re
import textwrap

import common
import streamlit as st
import strings as S
import ui

PAGE_SIZE = 10
MAX_MEANING = 140  # about two lines on a phone
MAX_PASSAGES = 3  # a topic can have 14 sources: the rest are named, not shown

course = common.get_active_course()
concepts_data = common.load("concepts.json")
concepts = concepts_data.get("concepts", []) if isinstance(concepts_data, dict) else []


def found_line(n: int) -> str | None:
    if not n:
        return None
    if common.using_examples("concepts.json"):
        return S.TOPICS_FOUND_SAMPLE.format(n=n)
    return S.TOPICS_FOUND_ONE if n == 1 else S.TOPICS_FOUND.format(n=n)


ui.page_header(S.TOPICS_TITLE, found_line(len(concepts)), step=2, source_file="concepts.json")

if not concepts:
    ui.empty_state(S.TOPICS_NONE, S.TOPICS_NONE_NEXT, action=S.TOPICS_ADD, page="add", icon="📄")
    st.stop()


def times_used(concept: dict) -> int:
    return len({(s.get("doc"), s.get("page")) for s in concept.get("sources", [])})


def one_line(description: str) -> str:
    """The first sentence, cut to fit: a card stays short."""
    first = re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0]
    return textwrap.shorten(first, MAX_MEANING, placeholder="…")


def where(source: dict) -> str:
    return common.citation(source.get("doc", ""), source.get("page", 1))


def read_this_part(concept: dict, description: str) -> None:
    """The full meaning, when the card had to cut it, and the text from the notes."""
    if description.strip() != one_line(description):
        st.write(description)
    sources = concept.get("sources", [])
    for source in sources[:MAX_PASSAGES]:
        st.markdown(where(source))
        chunk = chunks_map.get(source.get("chunk_id", ""))
        if chunk and "text" in chunk:
            st.info(chunk["text"])
        else:
            st.caption(S.TOPICS_TEXT_MISSING)
    if sources[MAX_PASSAGES:]:
        st.caption(S.TOPICS_ALSO.format(places=" · ".join(map(where, sources[MAX_PASSAGES:]))))


def topic_card(concept: dict) -> None:
    description = concept.get("description", "")
    sources = concept.get("sources", [])
    with ui.info_card(concept.get("name", ""), one_line(description) if description else None):
        if not sources:
            return
        extra = len(sources) - 1
        more = S.TOPICS_WHERE_MORE.format(n=extra) if extra else ""
        st.markdown(S.TOPICS_WHERE.format(place=where(sources[0]) + more))
        key = f"read_{course}_{concept.get('id', concept.get('name', ''))}"
        is_open = st.session_state.get(key, False)
        label = S.TOPICS_HIDE if is_open else S.TOPICS_READ
        if ui.action_button(label, icon="📖", key=f"button_{key}", primary=False):
            st.session_state[key] = not is_open
            st.rerun()
        if is_open:
            read_this_part(concept, description)


chunks_map = common.get_chunks_map()
query = st.text_input(S.TOPICS_SEARCH, value="").strip().lower()
all_docs = sorted({src["doc"] for c in concepts for src in c.get("sources", []) if "doc" in src})
selected_doc = S.TOPICS_ALL_FILES
if len(all_docs) > 1:
    selected_doc = st.selectbox(S.TOPICS_FILTER, [S.TOPICS_ALL_FILES, *all_docs])


def matches(concept: dict) -> bool:
    text = [concept.get("name", ""), *concept.get("aliases", []), concept.get("description", "")]
    in_doc = selected_doc == S.TOPICS_ALL_FILES or any(
        s.get("doc") == selected_doc for s in concept.get("sources", [])
    )
    return in_doc and (not query or any(query in t.lower() for t in text))


filtered = sorted(
    (c for c in concepts if matches(c)),
    key=lambda c: (-times_used(c), c.get("name", "").lower()),
)

# A new search, file or subject starts again from the top of its list.
view = (course, query, selected_doc)
if st.session_state.get("topics_view") != view:
    st.session_state["topics_view"] = view
    st.session_state["topics_limit"] = PAGE_SIZE
shown = filtered[: st.session_state["topics_limit"]]

st.caption(S.TOPICS_RANKED)
st.markdown(S.TOPICS_COUNT.format(shown=len(shown), total=len(filtered)))
if not filtered:
    st.info(S.TOPICS_NO_MATCH, icon="ℹ️")

for concept in shown:
    topic_card(concept)

left = len(filtered) - len(shown)
if left and ui.action_button(
    S.TOPICS_MORE.format(n=min(left, PAGE_SIZE)), key="topics_more", primary=False
):
    st.session_state["topics_limit"] += PAGE_SIZE
    st.rerun()

ui.action_button(S.TOPICS_NEXT, page="quiz", icon="➡️")
