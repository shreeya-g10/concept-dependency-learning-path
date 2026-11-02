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

SAMPLE_COURSE = "ds101"
BIG_UPLOAD_AREA = """
<style>
[data-testid="stFileUploaderDropzone"] { min-height: 11rem; }
</style>
"""

ui.page_header(S.ADD_TITLE, S.ADD_INTRO, step=1, show_course=False)
st.markdown(BIG_UPLOAD_AREA, unsafe_allow_html=True)


def time_span(low: int, high: int) -> str:
    """'3 to 8 minutes', or hours for a long job. The estimate rounds small jobs down to 0."""
    if high >= 120:
        low, high = max(1, round(low / 60)), round(high / 60)
        return S.ADD_HOURS.format(low=low, high=max(low + 1, high))
    low = max(1, low)
    return S.ADD_MINUTES.format(low=low, high=max(low + 1, high))


def render_job(course_id: str) -> None:
    """What is happening now, in words, and the outcome of the course's latest job."""
    status = jobs.read_status(course_id)
    state = status["state"]
    if state == "none":
        return
    if state not in ("starting", "running") and st.session_state.pop(f"polling_{course_id}", False):
        st.cache_data.clear()  # pages cache contract files: show the new outputs
        st.rerun()
    if state in ("starting", "running"):
        st.session_state[f"polling_{course_id}"] = True
        working = [r["stage"] for r in status["stages"] if r["status"] == "running"]
        step = S.STAGE_LABELS[working[0]] if working else S.ADD_STARTING
        st.markdown(S.ADD_NOW.format(step=step))
        st.progress(status.get("progress", 0.0))
        for row in status["stages"]:
            if row["status"] == "done":
                st.markdown(S.ADD_STEP_DONE.format(step=S.STAGE_LABELS[row["stage"]].rstrip("…")))
        st.caption(S.ADD_RUNNING)
    elif state == "succeeded":
        st.success(S.ADD_DONE)
        st.session_state["course_id"] = course_id
        ui.action_button(S.ADD_NEXT, page="topics", icon="➡️")
    else:
        details = "\n\n".join(filter(None, [status["error"], status["log"]]))
        ui.friendly_error(S.ADD_FAILED, S.ADD_FAILED_NEXT, details=details or S.ADD_LOG)


llm_ok, llm_message = jobs.llm_status()
if not llm_ok:
    ui.friendly_error(S.ADD_AI_OFF, S.ADD_AI_OFF_NEXT, details=llm_message)
    if ui.action_button(S.ADD_SAMPLE, icon="📚", key="sample"):
        st.session_state["course_id"] = SAMPLE_COURSE
        st.switch_page(ui.PAGES["topics"].path)

st.markdown(S.ADD_FILE_TYPES)
uploaded = st.file_uploader(S.ADD_FILES, type=jobs.UPLOAD_TYPES, accept_multiple_files=True)

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
if course_id in common.COURSE_NAMES:  # the id is hidden: never overwrite a built-in course
    ui.friendly_error(S.ADD_NAME_TAKEN, S.ADD_NAME_TAKEN_NEXT)
    st.stop()
st.session_state["upload_course"] = course_id

status = jobs.read_status(course_id)
busy = status["state"] in ("starting", "running")
batch = (course_id, tuple((f.name, f.size) for f in uploaded))
if busy and uploaded:
    st.info(S.ADD_BUSY, icon="⏳")
elif uploaded and st.session_state.get("saved_batch") != batch:
    try:
        jobs.save_uploads(course_id, [(f.name, f.getvalue()) for f in uploaded])
        st.session_state["saved_batch"] = batch
    except Exception as exc:  # bad file or conversion error: say so, keep the page
        ui.friendly_error(S.ADD_SAVE_FAILED, S.ADD_SAVE_FAILED_NEXT, details=str(exc))

if busy:
    st.fragment(run_every=3)(render_job)(course_id)
    st.stop()
render_job(course_id)

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
    st.stop()

st.markdown(S.ADD_FILES_HERE.format(files=", ".join(readable)))
has_text = True
try:
    estimate = jobs.estimate(folder)
    has_text = estimate["words"] > 0
    if has_text:
        st.markdown(S.ADD_TIME.format(span=time_span(*estimate["total_minutes"])))
    else:
        ui.friendly_error(S.ADD_NO_TEXT, S.ADD_NO_TEXT_NEXT)
except Exception:
    st.caption(S.ADD_TIME_FAILED)
if (common.OUTPUTS / course_id).is_dir():
    st.warning(S.ADD_REPLACES, icon="ℹ️")
done = status["state"] == "succeeded"
if ui.action_button(
    S.ADD_BUILD_AGAIN if done else S.ADD_BUILD,
    icon="📖",
    key="build",
    primary=llm_ok and not done,  # one main button: the sample course or "Next" comes first
    disabled=not llm_ok or not has_text,
):
    try:
        jobs.start_job(course_id)
        st.session_state["course_id"] = course_id
        st.rerun()
    except (RuntimeError, ValueError, OSError) as exc:
        ui.friendly_error(S.ADD_BUILD_FAILED, S.ADD_BUILD_FAILED_NEXT, details=str(exc))
