"""Owner: Vaidehi (@vkumaw).
Course Material & Concept Extraction Explorer.
Shows extracted concepts, aliases, definitions, and citations with chunk text previews.
"""

from __future__ import annotations

import streamlit as st
from common import get_chunks_map, load, page_header, render_sidebar

page_header("Course Material & Concepts", "Vaidehi", "concepts.json")
render_sidebar()

concepts_data = load("concepts.json")
concepts = concepts_data.get("concepts", []) if isinstance(concepts_data, dict) else []
chunks_map = get_chunks_map()

# Top Controls: Search and Filter
col1, col2 = st.columns([2, 1])

with col1:
    search_query = st.text_input("🔍 Search Concepts (name, alias, or description)", value="")

# Collect unique document names
all_docs = sorted({src["doc"] for c in concepts for src in c.get("sources", []) if "doc" in src})
with col2:
    selected_doc = st.selectbox("Filter by Lecture / Document", ["All Documents"] + all_docs)

# Filter concepts
filtered = []
for c in concepts:
    name = c.get("name", "")
    aliases = c.get("aliases", [])
    desc = c.get("description", "")
    sources = c.get("sources", [])

    # Text search match
    q = search_query.lower()
    matches_query = (
        not q or q in name.lower() or any(q in a.lower() for a in aliases) or q in desc.lower()
    )

    # Document filter match
    matches_doc = selected_doc == "All Documents" or any(
        s.get("doc") == selected_doc for s in sources
    )

    if matches_query and matches_doc:
        filtered.append(c)

st.markdown(f"**Showing {len(filtered)} of {len(concepts)} extracted concepts**")

# Render Concept Cards
for c in filtered:
    c_id = c.get("id", "")
    name = c.get("name", "")
    aliases = c.get("aliases", [])
    description = c.get("description", "")
    sources = c.get("sources", [])

    aliases_str = f" · *Aliases:* `{', '.join(aliases)}`" if aliases else ""

    with st.container():
        st.markdown(f"### `{c_id}` — {name}{aliases_str}")
        st.write(description)

        # Sources & Chunk Previews
        citations = []
        for s in sources:
            doc_name = s.get("doc", "")
            page_num = s.get("page", 1)
            chunk_id = s.get("chunk_id", "")
            citations.append(f"📄 **{doc_name}** (p. {page_num})")

        st.markdown(" · ".join(citations))

        num_src = len(sources)
        label = f"📖 View Source Text & Evidence ({num_src} citation{'s' if num_src > 1 else ''})"
        with st.expander(label):
            for s in sources:
                chunk_id = s.get("chunk_id", "")
                doc_name = s.get("doc", "")
                page_num = s.get("page", 1)
                chunk = chunks_map.get(chunk_id)

                st.markdown(f"**Source Document:** `{doc_name}`, Page {page_num} `({chunk_id})`")
                if chunk and "text" in chunk:
                    st.info(chunk["text"])
                else:
                    st.caption("Detailed text excerpt available in `outputs/chunks.jsonl`.")

        st.divider()

# Upload new course material section
with st.expander("📤 Add Course Material (PDF / PPTX)"):
    st.write("Upload additional lecture slides or course notes to parse new concepts.")
    uploaded_files = st.file_uploader(
        "Choose PDF or PPTX files",
        type=["pdf", "pptx"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        st.success(
            f"{len(uploaded_files)} file(s) selected. Place files into `data/raw/` to process."
        )
