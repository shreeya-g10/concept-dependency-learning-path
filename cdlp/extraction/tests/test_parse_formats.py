"""Markdown, plain-text and DOCX parsing: sections or pages kept as chunk references."""

from pathlib import Path

import pytest

from cdlp.extraction.parse import (
    is_course_file,
    parse_directory,
    parse_docx,
    parse_file,
    parse_markdown,
    parse_txt,
    strip_markdown,
)
from cdlp.shared.io import write_jsonl
from cdlp.shared.validate import check_file

MD = """Notes for week 3.

# Trees

A tree is a set of [nodes](https://example.org) with one **root**.

```python
def height(t):
    return 0
```

## Binary Trees ##

- Every node has at most *two* children.

## Empty section

# AVL Trees
![diagram](avl.png)
An AVL tree is a balanced binary search tree.
"""


def refs(chunks):
    return [(c["page"], c["heading"]) for c in chunks]


def test_markdown_sections_become_numbered_references(tmp_path):
    path = tmp_path / "week3.md"
    path.write_text(MD)
    chunks = parse_markdown(path, course_id="c1")
    # text before the first heading is section 1, titled after the file; the empty
    # section keeps its number (4) so later numbers match the document
    assert refs(chunks) == [(1, "week3"), (2, "Trees"), (3, "Binary Trees"), (5, "AVL Trees")]
    trees = chunks[1]["text"]
    assert "nodes with one root" in trees
    assert "def height" not in trees and "https://" not in trees  # code and link targets out
    assert chunks[2]["text"] == "Every node has at most two children."
    assert "avl.png" not in chunks[3]["text"]
    assert chunks[1]["chunk_id"] == "ch_week3_md_p2_0"
    assert {c["doc"] for c in chunks} == {"week3.md"} and {c["course_id"] for c in chunks} == {"c1"}


def test_markdown_starting_with_a_heading_starts_at_section_1(tmp_path):
    path = tmp_path / "n.md"
    path.write_text("# Heaps\nA heap is a tree.\n")
    assert refs(parse_markdown(path)) == [(1, "Heaps")]


def test_strip_markdown_keeps_plain_words():
    assert strip_markdown("> **BST** uses `key` and _order_") == "BST uses key and order"
    assert strip_markdown("1. first\n* second") == "first\nsecond"
    assert strip_markdown("snake_case_name stays") == "snake_case_name stays"


def test_txt_pages_split_at_form_feeds(tmp_path):
    path = tmp_path / "lecture.txt"
    path.write_text("Recursion\nA function that calls itself.\fStacks\nLast in, first out.")
    chunks = parse_txt(path)
    assert refs(chunks) == [(1, "Recursion"), (2, "Stacks")]
    assert chunks[0]["text"] == "A function that calls itself."
    assert chunks[1]["chunk_id"] == "ch_lecture_txt_p2_0"


def test_txt_without_form_feeds_is_one_page(tmp_path):
    path = tmp_path / "plain.txt"
    path.write_text("This is a long first sentence that is not a heading at all.\nMore text.")
    chunks = parse_txt(path)
    assert [c["page"] for c in chunks] == [1] and chunks[0]["heading"] == "plain Page 1"


def test_docx_sections_follow_headings_and_keep_tables_in_place(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Course intro.")
    document.add_heading("Graphs", level=1)
    document.add_paragraph("A graph has vertices and edges.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "BFS"
    table.rows[0].cells[1].text = "queue"
    document.add_heading("Heaps", level=2)
    document.add_paragraph("A heap keeps the smallest key on top.")
    path = tmp_path / "week 4.docx"
    document.save(path)
    chunks = parse_docx(path)
    assert refs(chunks) == [(1, "week 4"), (2, "Graphs"), (3, "Heaps")]
    assert chunks[1]["text"] == "A graph has vertices and edges.\n\nBFS | queue"
    assert chunks[2]["chunk_id"] == "ch_week_4_docx_p3_0"


def test_directory_reads_every_format_skips_readme_and_matches_the_contract(tmp_path):
    (tmp_path / "a.md").write_text("# Trees\nA tree has a root.\n")
    (tmp_path / "b.txt").write_text("Stacks\nLast in, first out.")
    (tmp_path / "README.md").write_text("# About\nThis folder holds the lectures.\n")
    (tmp_path / "data.csv").write_text("x,y\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("# Hidden\nnot read\n")
    assert not is_course_file(tmp_path / "README.md") and not is_course_file(tmp_path / "sub")
    chunks = parse_directory(tmp_path, course_id="c1")
    assert sorted({c["doc"] for c in chunks}) == ["a.md", "b.txt"]
    write_jsonl(tmp_path / "chunks.jsonl", chunks)
    assert check_file(tmp_path / "chunks.jsonl") == []


def test_unknown_types_give_no_chunks(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b")
    assert parse_file(Path(path)) == []


def test_chunk_limit_warns_and_reports_the_cut(monkeypatch, capsys):
    from cdlp.extraction.parse import apply_chunk_limit

    chunks = [{"chunk_id": str(n)} for n in range(5)]
    monkeypatch.delenv("CDLP_MAX_CHUNKS", raising=False)
    assert apply_chunk_limit(chunks) == (chunks, None)
    monkeypatch.setenv("CDLP_MAX_CHUNKS", "9")
    assert apply_chunk_limit(chunks) == (chunks, None)
    assert capsys.readouterr().err == ""

    monkeypatch.setenv("CDLP_MAX_CHUNKS", "2")
    kept, cut = apply_chunk_limit(chunks)
    assert kept == chunks[:2]
    assert cut == {"kept": 2, "total": 5, "limit_from": "CDLP_MAX_CHUNKS"}
    assert "kept 2 of 5 chunks" in capsys.readouterr().err


def test_a_cut_run_is_recorded_in_concepts_json(tmp_path, monkeypatch):
    import json
    import sys

    from cdlp.extraction import __main__ as cli
    from cdlp.shared.validate import check_file

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "notes.md").write_text(
        "# One\n\nFirst part.\n\n# Two\n\nSecond part.\n\n# Three\n\nEnd.\n"
    )
    out = tmp_path / "out"
    monkeypatch.setenv("CDLP_MAX_CHUNKS", "1")
    monkeypatch.setattr(
        cli,
        "extract_concepts_from_chunks",
        lambda chunks, **k: {
            "schema_version": "1.7",
            "course_id": "c1",
            "concepts": [{"id": "one", "name": "One", "sources": [{"doc": "notes.md", "page": 1}]}],
        },
    )
    argv = ["x", "--input", str(raw), "--out-dir", str(out), "--course-id", "c1"]
    monkeypatch.setattr(sys, "argv", [*argv, "--no-concept-filter"])
    cli.main()
    concepts = json.loads((out / "concepts.json").read_text())
    assert concepts["chunks_truncated"]["kept"] == 1 and concepts["chunks_truncated"]["total"] > 1
    assert concepts["schema_version"] == "1.12"
    assert check_file(out / "concepts.json") == []
    assert len((out / "chunks.jsonl").read_text().splitlines()) == 1
