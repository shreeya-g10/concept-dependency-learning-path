"""Running headers never become chunk headings; deduplication never falls back silently.

No LLM call and no real embedding model (both faked).
"""

import sys

import pytest

from cdlp.extraction import extract
from cdlp.extraction.extract import (
    DedupError,
    dedup_method,
    extract_concepts_from_chunks,
    fallback_method,
)
from cdlp.extraction.parse import clean_page, looks_like_heading, running_lines
from cdlp.shared.validate import check

# ---- headings -----------------------------------------------------------------------

PROSE = "This line is ordinary running prose that wraps onto the next line and has no end"


@pytest.mark.parametrize(
    "line",
    [
        "Binary Trees",
        "BinaryTree: A Basic Binary Tree",
        "12.3.2 Multivariate Gradient Descent",
        "Forward Propagation, Backward Propagation, and Computational Graphs",
        "Removal",
    ],
)
def test_titles_are_headings(line):
    assert looks_like_heading(line)


@pytest.mark.parametrize(
    "line",
    [
        "83",
        "§6.1",
        "xii",
        "(continued from previous page)",
        "Chapter 6",
        "import torch",
        "x1, x2 = -5, -2",
        "Fig. 3.1.1",
        "Figure 6.2: A binary tree",
        "u",
        "To find the block that contains a particular element, we proceed the",
        "Taking logarithms on both sides of this equation gives",
        PROSE,
    ],
)
def test_noise_code_captions_and_prose_are_not(line):
    assert not looks_like_heading(line)


WORDS = "alpha beta gamma delta epsilon zeta theta kappa lambda sigma omega rho".split()


def body(page: int, lines: int = 8) -> list[str]:
    """Distinct prose lines per page, so only the real running lines repeat."""
    return [
        f"In this paragraph we discuss {WORDS[(page + i) % 12]} and {WORDS[(page * 3 + i) % 12]} "
        f"of the {WORDS[(page * 5 + i) % 12]} model in more detail than before"
        for i in range(lines)
    ]


def pages_like_a_book():
    """D2L-style pages: page number + running title on top, continuation markers."""
    return [
        ["82", "Linear Neural Networks for Regression", "Linear Regression", *body(1)],
        ["83", "Linear Regression", "(continued from previous page)", "import torch", *body(2)],
        ["84", "Linear Neural Networks for Regression", *body(3), "(continues on next page)"],
        ["85", "Linear Regression", "Minibatch Stochastic Gradient Descent", *body(4)],
        ["86", "Linear Neural Networks for Regression", *body(5)],
    ]


def test_running_titles_are_found_across_pages():
    running = running_lines(pages_like_a_book())
    assert {"linear regression", "linear neural networks for regression"} <= running


def test_clean_page_drops_page_numbers_markers_and_running_titles():
    pages = pages_like_a_book()
    running = running_lines(pages)
    heading, titles, lines = clean_page(pages[1], running)
    assert heading is None  # "import torch" is code, not a heading
    assert titles == ["Linear Regression"]
    assert lines == ["import torch", *body(2)]
    heading, _, lines = clean_page(pages[3], running)
    assert heading == "Minibatch Stochastic Gradient Descent" and lines == body(4)


def test_pdf_headings_follow_sections_not_running_headers(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from cdlp.extraction.parse import parse_pdf

    doc = pymupdf.open()
    for lines in pages_like_a_book():
        page = doc.new_page()
        page.insert_text((72, 72), "\n".join(lines), fontsize=9)
    path = tmp_path / "book.pdf"
    doc.save(path)
    headings = [c["heading"] for c in parse_pdf(path)]
    assert headings == [
        "Linear Regression",  # printed on page 1 under the chapter's running title
        "Linear Regression",  # page 2 continues it
        "Linear Regression",
        "Minibatch Stochastic Gradient Descent",  # a new heading printed on page 4
        "Minibatch Stochastic Gradient Descent",  # page 5 continues it
    ]
    for chunk in parse_pdf(path):
        assert not chunk["heading"].isdigit() and "continue" not in chunk["text"]


# ---- deduplication --------------------------------------------------------------------


class FakeEmbedder:
    def __init__(self, fail=False):
        self.fail = fail

    def encode(self, texts):
        if self.fail:
            raise RuntimeError("MPS backend out of memory")
        return [[float(len(t)), float(t.count("e")) + 1.0] for t in texts]


def chunk(i, text):
    return {"chunk_id": f"c{i}", "doc": "l.pdf", "page": i, "heading": "", "text": text}


CHUNKS = [chunk(1, "Binary Trees and Heaps."), chunk(2, "Graphs and binary trees.")]


@pytest.fixture
def no_llm(monkeypatch):
    calls = []

    def fake(c):
        calls.append(c["chunk_id"])
        return extract.fallback_extract(c)

    monkeypatch.setattr(extract, "extract_concepts_from_chunk", fake)
    return calls


def test_missing_embedder_fails_before_any_llm_call(monkeypatch, no_llm):
    monkeypatch.setattr(extract, "get_embedder", lambda: None)
    with pytest.raises(DedupError, match="--allow-tfidf"):
        extract_concepts_from_chunks(CHUNKS)
    assert no_llm == []  # nothing spent on LLM calls


def test_allowed_tfidf_warns_loudly_and_is_recorded(monkeypatch, no_llm, capsys):
    monkeypatch.setattr(extract, "get_embedder", lambda: None)
    result = extract_concepts_from_chunks(CHUNKS, allow_tfidf=True)
    assert (
        "WARNING: Concept deduplication cannot use sentence embeddings" in capsys.readouterr().err
    )
    assert result["dedup_method"] == fallback_method() and result["schema_version"] == "1.7"
    assert set(result["dedup_comparisons"]) <= {"tfidf", "jaccard"}
    assert check(result, "concepts") == []


def test_embedding_run_records_its_method(monkeypatch, no_llm, capsys):
    monkeypatch.setattr(extract, "get_embedder", lambda: FakeEmbedder())
    result = extract_concepts_from_chunks(CHUNKS)
    assert result["dedup_method"] == "embedding"
    assert result["dedup_comparisons"].get("embedding", 0) > 0
    assert "WARNING" not in capsys.readouterr().err
    assert check(result, "concepts") == []


def test_encode_failure_mid_run_is_not_silent(monkeypatch, no_llm, capsys):
    monkeypatch.setattr(extract, "get_embedder", lambda: FakeEmbedder(fail=True))
    with pytest.raises(DedupError, match="Embedding failed"):
        extract_concepts_from_chunks(CHUNKS)
    result = extract_concepts_from_chunks(CHUNKS, allow_tfidf=True)
    assert result["dedup_method"] == fallback_method()  # tfidf, or jaccard without sklearn
    assert result["dedup_comparisons"]["embedding_failed"] > 0
    assert "WARNING: Embedding failed" in capsys.readouterr().err


def test_dedup_method_names():
    from collections import Counter

    assert dedup_method(Counter(embedding=3), True) == "embedding"
    assert dedup_method(Counter(embedding=3, tfidf=1), True) == "mixed"
    assert dedup_method(Counter(), True) == "embedding"
    assert dedup_method(Counter(), False) == fallback_method()
    assert dedup_method(Counter(jaccard=2), False) == "jaccard"


def test_cli_exits_2_instead_of_writing_example_concepts(tmp_path, monkeypatch):
    pytest.importorskip("pymupdf")
    from cdlp.extraction import __main__ as cli

    monkeypatch.setattr(extract, "get_embedder", lambda: None)
    fixtures = "cdlp/extraction/tests/fixtures"
    monkeypatch.setattr(sys, "argv", ["x", "--input", fixtures, "--out-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 2
    assert not (tmp_path / "concepts.json").exists()  # no silent example fallback
