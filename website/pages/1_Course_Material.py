"""Course Material: upload files, build a course graph in the background, explore concepts.

Upload: the files go to data/raw/<course_id>/ as they are (cdlp.extraction reads PDF, PPTX,
MD, TXT and DOCX). "Build course graph" starts `python pipeline.py --course <course_id>` as
a background job through jobs.start_job(); this page only reads the job's state and log.
"""

from __future__ import annotations

import jobs
import streamlit as st
from common import OUTPUTS, get_active_course, get_chunks_map, load, page_header, render_sidebar

page_header("Course Material & Concepts", "Shreeya", "concepts.json")
render_sidebar()

STATUS_ICON = {"done": "✅", "running": "⏳", "failed": "❌", "skipped": "⏭️", "pending": "▫️"}


def render_job(course_id: str) -> None:
    """Progress per stage, the log tail and the outcome of the course's latest job."""
    status = jobs.read_status(course_id)
    state = status["state"]
    if state == "none":
        return
    st.markdown(f"#### Pipeline job for `{course_id}`: **{state}**")
    st.progress(status.get("progress", 0.0))
    for row in status["stages"]:
        st.markdown(f"{STATUS_ICON[row['status']]} {row['label']} · `{row['status']}`")
    if state in ("starting", "running"):
        st.session_state[f"polling_{course_id}"] = True
        st.caption("Running in the background. You can leave this page; the job keeps going.")
    elif state == "succeeded":
        st.success(f"Done. outputs/{course_id}/ is updated; pick `{course_id}` in the sidebar.")
    else:
        st.error(status["error"] or "The pipeline failed.")
    with st.expander("Pipeline log (last lines)", expanded=state == "failed"):
        st.code(status["log"] or "(no output yet)", language="text")
    if state not in ("starting", "running") and st.session_state.pop(f"polling_{course_id}", False):
        st.cache_data.clear()  # pages cache contract files: show the new outputs
        st.rerun()


tab_concepts, tab_upload = st.tabs(["🔎 Concepts", "📤 Upload & build a course"])

with tab_concepts:
    concepts_data = load("concepts.json")
    concepts = concepts_data.get("concepts", []) if isinstance(concepts_data, dict) else []
    chunks_map = get_chunks_map()

    # Top Controls: Search and Filter
    col1, col2 = st.columns([2, 1])

    with col1:
        search_query = st.text_input("🔍 Search Concepts (name, alias, or description)", value="")

    # Collect unique document names
    all_docs = sorted(
        {src["doc"] for c in concepts for src in c.get("sources", []) if "doc" in src}
    )
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
                # MD / DOCX chunks count sections, not pages (cdlp/extraction/parse.py)
                where = "§" if doc_name.lower().endswith((".md", ".docx")) else "p."
                citations.append(f"📄 **{doc_name}** ({where} {page_num})")

            st.markdown(" · ".join(citations))

            num_src = len(sources)
            label = (
                f"📖 View Source Text & Evidence ({num_src} citation{'s' if num_src > 1 else ''})"
            )
            with st.expander(label):
                for s in sources:
                    chunk_id = s.get("chunk_id", "")
                    doc_name = s.get("doc", "")
                    page_num = s.get("page", 1)
                    chunk = chunks_map.get(chunk_id)

                    st.markdown(
                        f"**Source Document:** `{doc_name}`, Page {page_num} `({chunk_id})`"
                    )
                    if chunk and "text" in chunk:
                        st.info(chunk["text"])
                    else:
                        st.caption("Detailed text excerpt available in `outputs/chunks.jsonl`.")

            st.divider()

with tab_upload:
    st.write(
        "Upload course files and build the concept graph. Files are saved to "
        "`data/raw/<course_id>/`; a file with the same name is replaced."
    )
    course_id = st.text_input(
        "Course ID",
        value=st.session_state.get("upload_course", get_active_course()),
        help="Lowercase letters, digits and _ (2–40 characters), starting with a letter. "
        "Example: os101.",
    ).strip()
    st.session_state["upload_course"] = course_id
    if not jobs.valid_course_id(course_id):
        st.error("Course ID: use lowercase letters, digits and _ (2–40), starting with a letter.")
        st.stop()

    status = jobs.read_status(course_id)
    busy = status["state"] in ("starting", "running")
    uploaded = st.file_uploader(
        "Course files (PDF, PPTX, TXT, MD, DOCX)",
        type=jobs.UPLOAD_TYPES,
        accept_multiple_files=True,
    )
    if uploaded and st.button("💾 Save files", disabled=busy):
        try:
            saved = jobs.save_uploads(course_id, [(f.name, f.getvalue()) for f in uploaded])
            st.success("Saved: " + ", ".join(f"`{p.name}`" for p in saved))
        except Exception as exc:  # bad file or conversion error: say so, keep the page
            st.error(f"Could not save the files: {exc}")

    folder = jobs.RAW / course_id
    readable = (
        sorted(
            p.name
            for p in folder.iterdir()
            if p.suffix.lower() in jobs.READABLE and not p.name.lower().startswith("readme")
        )
        if folder.is_dir()
        else []
    )
    if not readable:
        st.info(f"No course files in `data/raw/{course_id}/` yet. Upload and save files first.")
    else:
        st.markdown(
            f"**Files in `data/raw/{course_id}/`:** " + ", ".join(f"`{n}`" for n in readable)
        )
        try:
            est = jobs.estimate(folder)
        except Exception as exc:
            est = None
            st.warning(f"Could not estimate the run size: {exc}")
        if est:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Files", est["files"])
            c2.metric("Size", f"{est['megabytes']} MB")
            c3.metric("Pages / slides / sections", est["pages"])
            c4.metric("Chunks", est["chunks"])
            low, high = est["total_minutes"]
            st.markdown(
                f"**Time estimate:** extraction makes {est['extraction_calls']} LLM calls "
                f"(≈ {est['extraction_minutes']} min). The whole pipeline takes roughly "
                f"**{low}–{high} min**: discovery and validation depend on how many concepts "
                "are found, so that part is a rough range. Only the validator speed is measured "
                "(llama3.1:8b, about 48 s per call on this laptop); the rest are assumptions "
                "(`website/jobs.py`). Website builds skip the report-only necessity test to stay "
                "quick. Cached LLM calls are almost free, so a re-run is faster."
            )
        llm_ok, llm_message = jobs.llm_status()
        if llm_ok:
            st.caption(llm_message)
        else:
            st.error(llm_message)
        if (OUTPUTS / course_id).is_dir():
            st.warning(f"A run replaces the files in `outputs/{course_id}/`.")
        if busy:
            st.info("A job for this course is already running.")
        if st.button("🚀 Build course graph", type="primary", disabled=busy or not llm_ok):
            try:
                jobs.start_job(course_id)
                st.session_state["course_id"] = course_id
                st.rerun()
            except (RuntimeError, ValueError, OSError) as exc:
                st.error(f"Could not start the pipeline: {exc}")

    if busy:
        st.fragment(run_every=3)(render_job)(course_id)
    else:
        render_job(course_id)
