"""Step 1: upload files and read them into a course, in the background.

Upload: the files go to data/raw/<course_id>/ as they are (cdlp.extraction reads PDF, PPTX,
MD, TXT and DOCX). "Read my notes" starts `python pipeline.py --course <course_id>` as a
background job through jobs.start_job(); this page only reads the job's state and log.
Students type a name; the course id is made from it and never shown.
"""

from __future__ import annotations

import common
import jobs
import streamlit as st
import strings as S
import ui

ui.page_header(S.ADD_TITLE, S.ADD_INTRO, step=1, show_course=False)


def render_job(course_id: str) -> None:
    """Progress per stage and the outcome of the course's latest job."""
    status = jobs.read_status(course_id)
    state = status["state"]
    if state == "none":
        return
    st.markdown(S.ADD_PROGRESS_TITLE)
    st.progress(status.get("progress", 0.0))
    for row in status["stages"]:
        label = S.STAGE_LABELS.get(row["stage"], row["label"])
        st.markdown(f"{S.STATUS_WORDS[row['status']]}: {label}")
    if state in ("starting", "running"):
        st.session_state[f"polling_{course_id}"] = True
        st.caption(S.ADD_RUNNING)
    elif state == "succeeded":
        st.success(S.ADD_DONE)
        ui.action_button(S.ADD_NEXT, page="topics", icon="➡️")
    else:
        details = "\n\n".join(filter(None, [status["error"], status["log"]]))
        ui.friendly_error(S.ADD_FAILED, S.ADD_FAILED_NEXT, details=details or S.ADD_LOG)
    if state not in ("starting", "running") and st.session_state.pop(f"polling_{course_id}", False):
        st.cache_data.clear()  # pages cache contract files: show the new outputs
        st.rerun()


name = st.text_input(
    S.ADD_NAME,
    value=common.course_label(st.session_state["upload_course"])
    if st.session_state.get("upload_course")
    else "",
    placeholder=S.ADD_NAME_HELP,
).strip()
if not name:
    st.info(S.ADD_NAME_EMPTY, icon="ℹ️")
    st.stop()
course_id = common.course_id_from_name(name)
if not jobs.valid_course_id(course_id):
    ui.friendly_error(S.ADD_NAME_BAD, S.ADD_NAME_BAD_NEXT)
    st.stop()
st.session_state["upload_course"] = course_id

status = jobs.read_status(course_id)
busy = status["state"] in ("starting", "running")
uploaded = st.file_uploader(S.ADD_FILES, type=jobs.UPLOAD_TYPES, accept_multiple_files=True)
if uploaded and ui.action_button(S.ADD_SAVE, icon="💾", disabled=busy):
    try:
        saved = jobs.save_uploads(course_id, [(f.name, f.getvalue()) for f in uploaded])
        st.success(S.ADD_SAVED.format(files=", ".join(p.name for p in saved)))
    except Exception as exc:  # bad file or conversion error: say so, keep the page
        ui.friendly_error(S.ADD_SAVE_FAILED, S.ADD_SAVE_FAILED_NEXT, details=str(exc))

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
    st.info(S.ADD_NO_FILES, icon="ℹ️")
else:
    st.markdown(S.ADD_FILES_HERE.format(files=", ".join(readable)))
    try:
        low, high = jobs.estimate(folder)["total_minutes"]
        st.markdown(S.ADD_TIME.format(low=low, high=high))
    except Exception:
        st.caption(S.ADD_TIME_FAILED)
    llm_ok, llm_message = jobs.llm_status()
    if not llm_ok:
        ui.friendly_error(S.ADD_AI_OFF, S.ADD_AI_OFF_NEXT, details=llm_message)
    if (common.OUTPUTS / course_id).is_dir():
        st.warning(S.ADD_REPLACES, icon="ℹ️")
    if busy:
        st.info(S.ADD_BUSY, icon="⏳")
    if ui.action_button(S.ADD_BUILD, icon="📖", disabled=busy or not llm_ok, key="build"):
        try:
            jobs.start_job(course_id)
            st.session_state["course_id"] = course_id
            st.rerun()
        except (RuntimeError, ValueError, OSError) as exc:
            ui.friendly_error(S.ADD_BUILD_FAILED, S.ADD_BUILD_FAILED_NEXT, details=str(exc))

if busy:
    st.fragment(run_every=3)(render_job)(course_id)
else:
    render_job(course_id)
