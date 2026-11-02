"""Website entry point: sets up the page and the menu, then draws the current page.

    streamlit run website/Home.py

The Home screen itself is pages/0_Start_here.py. Streamlit runs this file on every page view.
"""

from __future__ import annotations

import logging

import common  # noqa: F401  (puts the repo root on sys.path for cdlp imports)
import strings as S
import ui

ui.setup_page()
current = ui.navigation()
try:
    current.run()
except Exception:  # Streamlit's stop and rerun signals are not Exceptions, so they pass through
    logging.getLogger(__name__).exception("page failed: %s", current.title)
    ui.friendly_error(S.ERROR_PAGE, S.ERROR_PAGE_NEXT)
    ui.action_button(S.GO_HOME, page="home", icon="🏠")
