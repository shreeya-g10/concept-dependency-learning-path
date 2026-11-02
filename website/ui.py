"""Shared page parts: use these on every page so the whole site looks and reads the same.

One column, one main action per screen, large text and tap targets, an icon always next to
a word. Text comes from strings.py.
"""

from __future__ import annotations

from typing import NamedTuple

import common
import streamlit as st
import strings as S

TOTAL_STEPS = 4


class Page(NamedTuple):
    path: str  # relative to website/Home.py, the entry point
    title: str
    icon: str


PAGES = {
    # Not "0_Home.py": Streamlit would see two pages named Home (with the entry point).
    "home": Page("pages/0_Start_here.py", S.NAV_HOME, "🏠"),
    "add": Page("pages/1_Add_your_notes.py", S.NAV_ADD, "📄"),
    "topics": Page("pages/2_See_your_topics.py", S.NAV_TOPICS, "🔎"),
    "quiz": Page("pages/3_Quick_check.py", S.NAV_QUIZ, "✏️"),
    "plan": Page("pages/4_My_study_plan.py", S.NAV_PLAN, "🗺️"),
    "map": Page("pages/5_Topic_map.py", S.NAV_MAP, "🔗"),
    "ai_checks": Page("pages/teacher_AI_checks_and_review.py", S.NAV_AI_CHECKS, "✅"),
    "ai_suggestions": Page("pages/teacher_AI_suggestions.py", S.NAV_AI_SUGGESTIONS, "💡"),
}
STUDENT_PAGES = ["home", "add", "topics", "quiz", "plan", "map"]
TEACHER_PAGES = ["ai_checks", "ai_suggestions"]

# Larger text and tap targets than Streamlit's defaults, darker small text and notices, a
# clear keyboard focus ring, and the word "Menu" beside the phone menu icon (the icon alone
# breaks the "icon always with a word" rule). Colors match .streamlit/config.toml.
_CSS = """
<style>
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
  min-height: 3.25rem; font-size: 1.15rem; font-weight: 600;
}
.stRadio label, .stCheckbox label, [data-testid="stWidgetLabel"] p { font-size: 1.05rem; }
.stRadio [role="radiogroup"] label { min-height: 2.75rem; align-items: center; }
.stSelectbox [data-baseweb="select"] > div, .stTextInput input { min-height: 3rem; }
[data-testid="stSidebarNav"] a { min-height: 2.75rem; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] strong {
  color: #1F1B3D !important; opacity: 1 !important;
}
[data-testid="stMainBlockContainer"] { padding-top: 4rem; }
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"] script) { display: none; }
.st-key-demo_line [data-testid="stAlertContainer"] { padding: 0.5rem 0.625rem; }
.st-key-demo_line [data-testid="stAlertContainer"] p { font-size: 0.95rem; }
h1 { font-size: 2.1rem !important; line-height: 1.2 !important; }
[data-testid="stExpandSidebarButton"]::after {
  content: "__MENU__"; margin-left: 0.25rem; font-size: 1.05rem; font-weight: 600;
  color: #1F1B3D;
}
[data-testid="stExpandSidebarButton"] { width: auto !important; min-height: 2.75rem; }
:focus-visible { outline: 3px solid #4B3F8F !important; outline-offset: 2px; }
</style>
""".replace("__MENU__", S.MENU)


# On a phone the open menu covers the whole page, and Streamlit leaves it open after a tap. The
# listener sits on the document, so it is added once and survives page changes. 768px is the
# width below which Streamlit draws the menu over the page.
_CLOSE_MENU_ON_PHONE = """
<script>
if (!window.cdlpCloseMenu) {
  window.cdlpCloseMenu = true;
  document.addEventListener("click", (event) => {
    if (window.innerWidth >= 768) return;
    if (!event.target.closest('[data-testid="stSidebarNavLink"]')) return;
    const close = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if (close) close.click();
  });
}
</script>
"""


def setup_page() -> None:
    """Call once, from the entry point, before anything else is drawn."""
    st.set_page_config(
        page_title=S.APP_NAME,
        page_icon="📚",
        layout="centered",
        initial_sidebar_state="auto",
    )
    st.markdown(_CSS, unsafe_allow_html=True)
    st.html(_CLOSE_MENU_ON_PHONE, unsafe_allow_javascript=True)


def navigation():
    """The site menu. Call .run() on the result to draw the current page."""

    def group(keys: list[str]) -> list:
        return [
            st.Page(PAGES[k].path, title=PAGES[k].title, icon=PAGES[k].icon, default=k == "home")
            for k in keys
        ]

    return st.navigation(
        {
            S.NAV_GROUP_STUDENTS: group(STUDENT_PAGES),
            S.NAV_GROUP_TEACHERS: group(TEACHER_PAGES),
        }
    )


def step_indicator(step: int) -> None:
    """'Step 2 of 4' with a progress bar. The words matter; the bar only supports them."""
    st.markdown(f"**{S.STEP_OF.format(step=step, total=TOTAL_STEPS)}**")
    st.progress(step / TOTAL_STEPS)


def page_header(
    title: str,
    intro: str | None = None,
    *,
    step: int | None = None,
    source_file: str | None = None,
    show_course: bool = True,
    teacher: bool = False,
) -> None:
    """Title, step, subject and the honesty notices of a page.

    Pass `source_file` on every page that shows course results: it adds the sample notice
    (the file is example data) and the demo notice (the graph is only a demo subset).
    Students get the notice in one short line. `teacher=True` shows it in full, with the
    written rule that picked the demo subset.
    """
    if step is not None:
        step_indicator(step)
    st.title(title)
    if intro:
        st.write(intro)
    if show_course:
        course = common.course_label(common.get_active_course())
        st.caption(S.COURSE_LINE.format(course=course))
    if source_file:
        sample_notice(source_file)
        demo_notice(teacher=teacher)


def scroll_to_top(screen: str) -> None:
    """Start a new screen at its top. Call with text that changes when the screen does.

    Streamlit keeps the scroll position, so on a phone the next question could start above the
    fold. A script runs when its text changes, so the same screen drawn again does not jump. It
    runs again shortly after, because the old screen's height can hold the position at first.
    """
    st.html(
        f"""<script>/* {screen} */
        for (const wait of [0, 150, 400]) setTimeout(() => {{
          document.querySelector('[data-testid="stMain"]')?.scrollTo(0, 0);
        }}, wait);
        </script>""",
        unsafe_allow_javascript=True,
    )


def action_button(
    label: str,
    *,
    page: str | None = None,
    icon: str | None = None,
    key: str | None = None,
    primary: bool = True,
    disabled: bool = False,
) -> bool:
    """A big full-width button. With `page` (a key of PAGES), a tap opens that page.

    Keep one primary button per screen; use primary=False for any other choice.
    """
    clicked = st.button(
        label,
        key=key,
        icon=icon,
        type="primary" if primary else "secondary",
        disabled=disabled,
        width="stretch",
    )
    if clicked and page:
        st.switch_page(PAGES[page].path)
    return clicked


def info_card(title: str, body: str | None = None, *, icon: str | None = None):
    """A bordered card. Returns its container, so `with info_card(...):` can add a button."""
    card = st.container(border=True)
    heading = f"{icon} {title}" if icon else title
    card.markdown(f"**{heading}**")
    if body:
        card.write(body)
    return card


def friendly_error(problem: str, next_step: str, *, details: str | None = None) -> None:
    """What went wrong and what to do next. `details` stay folded away for a teacher."""
    st.error(f"{problem}\n\n**{S.WHAT_TO_DO}:** {next_step}", icon="⚠️")
    if details:
        with st.expander(S.MORE_DETAILS):
            st.code(details, language="text")


def empty_state(
    message: str,
    next_step: str | None = None,
    *,
    action: str | None = None,
    page: str | None = None,
    icon: str | None = None,
) -> None:
    """Nothing to show yet: say why and offer the one thing to do about it."""
    st.info(f"{message} {next_step}" if next_step else message, icon="ℹ️")
    if action:
        action_button(action, page=page, icon=icon)


def demo_notice(course_id: str | None = None, *, teacher: bool = False) -> None:
    """Says so when the course's graph covers only a demo subset. Must never be removed."""
    note = common.demo_subset_note(course_id) if teacher else common.demo_subset_short(course_id)
    if note and teacher:
        st.warning(note, icon="ℹ️")
    elif note:
        with st.container(key="demo_line"):  # tighter, so it stays one line on a small phone
            st.warning(note, icon="ℹ️")
    rule = common.demo_subset_rule(course_id) if teacher else None
    if rule:
        st.caption(f"How the demo links were picked: {rule}")


def sample_notice(source_file: str, course_id: str | None = None) -> None:
    """Says so when a page shows example data, not this subject's own data."""
    if common.using_examples(source_file, course_id=course_id):
        st.info(S.SAMPLE_NOTICE, icon="ℹ️")
