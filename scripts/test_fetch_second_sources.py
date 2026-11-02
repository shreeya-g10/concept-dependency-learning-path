"""Offline tests of the second-source converters (no download)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "fetch_second_sources", Path(__file__).parent / "fetch_second_sources.py"
)
fss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fss)

RST = """.. avmetadata::
   :author: X

The AVL Tree
============

An AVL tree is a :term:`BST <binary search tree>` with balance :math:`O(\\log n)`.

.. odsafig:: Images/AVLins.png
   :width: 500

Rotations
---------

#. single rotation
(#) double rotation

.. note::
   Keep this note.
"""

HTML = """<html><body><nav><p>menu</p></nav>
<main id="quarto-document-content"><h2>9.1 Logit</h2><p>The <em>logit</em> link.</p>
<div class="cell"><pre><code>glm(y ~ x)</code></pre><div class="cell-output"><p>out</p></div></div>
<figure><p>caption</p></figure><ul><li>odds</li></ul>
<h2>9.6 Exercises</h2><p>exercise text</p></main></body></html>"""


def test_rst_keeps_headings_and_prose_and_drops_directives():
    md = fss.convert(RST, "<!-- header -->")
    assert md.startswith("<!-- header -->")
    assert "# The AVL Tree" in md and "## Rotations" in md
    assert "is a BST with balance O(\\log n)." in md
    assert "- single rotation" in md and "- double rotation" in md
    assert "Keep this note." in md
    assert "avmetadata" not in md and "odsafig" not in md and ":width:" not in md


def test_html_keeps_text_and_drops_code_output_figures_and_exercises():
    md = fss.html_to_markdown(HTML, "<!-- header -->")
    assert md.split("\n\n") == ["<!-- header -->", "# 9.1 Logit", "The logit link.", "odds\n"]


def test_every_source_has_a_pinned_hash():
    assert all(len(sha) == 64 for _, sha, _ in fss.SOURCES) and len(fss.IMS_SHA256) == 64
