"""Home: pick a subject, see the 4 steps, start."""

from __future__ import annotations

import common
import streamlit as st
import strings as S
import ui

st.title(S.HOME_TITLE)

courses = common.course_options()
active = common.get_active_course()
st.session_state["course_id"] = st.selectbox(
    S.HOME_PICK_SUBJECT,
    courses,
    index=courses.index(active) if active in courses else 0,
    format_func=common.course_label,
    key="home_course_picker",
)
ui.sample_notice("validated_graph.json")
ui.demo_notice()

col1, col2 = st.columns(2)
with col1:
    with ui.info_card(
        "Explore Sample Subject (Data Structures)",
        "Recommended for live demo: Instant access to topics, check questions, "
        "and personalized study path.",
        icon="📚",
    ):
        if ui.action_button(
            "Start Demo (Data Structures)", icon="🚀", key="demo_start_card", primary=True
        ):
            st.session_state["course_id"] = "ds101"
            st.switch_page(ui.PAGES["quiz"].path)

with col2:
    with ui.info_card(
        "Upload Custom Notes (PDF / PPTX)",
        "Add your class notes. Fast Demo Mode processes files in seconds with zero laptop strain.",
        icon="📄",
    ):
        if ui.action_button("Upload Your Notes", icon="📤", key="upload_start_card", primary=False):
            st.switch_page(ui.PAGES["add"].path)

st.write(S.HOME_INTRO)
buttons = [
    (S.HOME_START, "add", True),
    (S.HOME_HAVE_NOTES, "topics", False),
    (S.HOME_QUIZ, "quiz", False),
    (S.HOME_PLAN, "plan", False),
]
for (icon, title, body), (label, page, primary) in zip(S.HOME_STEPS, buttons, strict=True):
    with ui.info_card(title, body, icon=icon):
        ui.action_button(label, page=page, icon=icon, primary=primary, key=f"home_{page}")
