"""Unit tests for PDF and PPTX parsing in extraction module.

Owner: Vaidehi.
"""

from pathlib import Path

import pytest

from cdlp.extraction.parse import (
    chunk_text,
    clean_text,
    extract_heading_and_body,
    parse_directory,
)
from cdlp.shared.validate import check_file


def test_clean_text():
    raw = "  Hello   world \r\n\r\n\r\n This is   a test.  "
    cleaned = clean_text(raw)
    assert cleaned == "Hello world\n\nThis is a test."


def test_chunk_text_short():
    text = "Short text with only a few words."
    chunks = chunk_text(text, max_words=100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long():
    paragraphs = ["Word " * 100 for _ in range(10)]
    full_text = "\n\n".join(paragraphs)
    chunks = chunk_text(full_text, target_words=250, max_words=350)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.split()) <= 450


def test_extract_heading_explicit():
    text = "Heading: Binary Search Trees\nA BST is a binary tree with ordering."
    h, body = extract_heading_and_body(text, "Default")
    assert h == "Binary Search Trees"
    assert "A BST is" in body
    assert "Heading:" not in body


def test_parse_data_raw(tmp_path):
    chunks = parse_directory(Path("data/raw"))
    if not chunks:
        pytest.skip("PyMuPDF / python-pptx not available in this environment")
    assert len(chunks) >= 6

    # Verify every chunk conforms to the contract
    out_file = tmp_path / "chunks.jsonl"
    from cdlp.shared.io import write_jsonl

    write_jsonl(out_file, chunks)
    errors = check_file(out_file)
    assert errors == []
