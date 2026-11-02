"""Every website page must render without an exception (on example data)."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
PAGES = [SITE / "Home.py", *sorted((SITE / "pages").glob("*.py"))]
# `streamlit run website/Home.py` puts website/ on sys.path (for common.py, jobs.py);
# a single page run by AppTest does not, so add it here.
if str(SITE) not in sys.path:
    sys.path.insert(0, str(SITE))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_renders(page):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception
