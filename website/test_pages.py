"""Every website page must render without an exception (on example data)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

SITE = Path(__file__).parent
PAGES = [SITE / "Home.py", *sorted((SITE / "pages").glob("*.py"))]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_renders(page):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception
