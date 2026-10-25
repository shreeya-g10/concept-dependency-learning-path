"""PDF and PPTX parsing and text chunking for the extraction module.

Owner: Vaidehi.
Reads PDFs (PyMuPDF) and PPTX (python-pptx), splits text into 300-500 word
chunks, and outputs structured records conforming to chunk.schema.json.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf as fitz  # PyMuPDF
from pptx import Presentation

from cdlp.shared.io import write_jsonl


def clean_text(text: str) -> str:
    """Normalize whitespace and strip excess blank lines."""
    text = re.sub(r"\r\n|\r", "\n", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    output: list[str] = []
    blank = False
    for line in lines:
        if line:
            output.append(line)
            blank = False
        elif not blank:
            output.append("")
            blank = True
    return "\n".join(output).strip()


def extract_heading_and_body(raw_text: str, default_heading: str) -> tuple[str, str]:
    """Extract a heading from text if present, otherwise return default."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return default_heading, ""

    first_line = lines[0]
    if first_line.lower().startswith("heading:"):
        heading = first_line.split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()
        return heading or default_heading, body

    if len(first_line) < 80 and not first_line.endswith((".", ";", ":")):
        heading = first_line
        body = "\n".join(lines[1:]).strip()
        return heading, body

    return default_heading, raw_text.strip()


def chunk_text(
    text: str,
    target_words: int = 400,
    max_words: int = 500,
) -> list[str]:
    """Split text into chunks of approximately 300-500 words.

    If text has fewer than max_words, returns a single chunk.
    Otherwise splits along paragraph or sentence boundaries.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    words = cleaned.split()
    if len(words) <= max_words:
        return [cleaned]

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_word_count = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_word_count + para_words > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_word_count = para_words
        else:
            current_chunk.append(para)
            current_word_count += para_words

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def parse_pdf(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a PDF document using PyMuPDF and return structured chunk dictionaries."""
    doc = fitz.open(path)
    chunks: list[dict[str, Any]] = []

    clean_stem = re.sub(r"[^a-zA-Z0-9_]", "_", path.stem).lower()

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        raw_text = page.get_text()
        default_heading = f"{path.stem} Page {page_num}"
        heading, body = extract_heading_and_body(raw_text, default_heading)

        if not body:
            continue

        text_pieces = chunk_text(body)
        for chunk_idx, piece in enumerate(text_pieces):
            chunk_id = f"ch_{clean_stem}_p{page_num}_{chunk_idx}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "course_id": course_id,
                    "doc": path.name,
                    "page": page_num,
                    "heading": heading,
                    "text": piece,
                }
            )

    doc.close()
    return chunks


def parse_pptx(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a PPTX slide deck using python-pptx and return structured chunk dictionaries."""
    prs = Presentation(path)
    chunks: list[dict[str, Any]] = []
    clean_stem = re.sub(r"[^a-zA-Z0-9_]", "_", path.stem).lower()

    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        title_text = ""
        body_parts: list[str] = []

        if slide.shapes.title and slide.shapes.title.text:
            title_text = slide.shapes.title.text.strip()

        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    line = paragraph.text.strip()
                    if line:
                        body_parts.append(line)

        raw_body = "\n".join(body_parts).strip()
        default_heading = title_text or f"{path.stem} Slide {slide_num}"
        heading, body = extract_heading_and_body(raw_body, default_heading)

        full_content = body if body else title_text
        if not full_content:
            continue

        text_pieces = chunk_text(full_content)
        for chunk_idx, piece in enumerate(text_pieces):
            chunk_id = f"ch_{clean_stem}_p{slide_num}_{chunk_idx}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "course_id": course_id,
                    "doc": path.name,
                    "page": slide_num,
                    "heading": heading,
                    "text": piece,
                }
            )

    return chunks


def parse_file(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a single file (PDF or PPTX)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, course_id=course_id)
    if suffix in (".pptx", ".ppt"):
        return parse_pptx(path, course_id=course_id)
    return []


def parse_directory(input_dir: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse all supported PDF and PPTX files in a directory."""
    all_chunks: list[dict[str, Any]] = []
    input_path = Path(input_dir)

    supported = sorted(
        [
            p
            for p in input_path.iterdir()
            if p.is_file() and p.suffix.lower() in (".pdf", ".pptx", ".ppt")
        ]
    )

    for file_path in supported:
        chunks = parse_file(file_path, course_id=course_id)
        all_chunks.extend(chunks)

    return all_chunks


def parse_and_save(
    input_dir: Path, out_file: Path, course_id: str = "ds101"
) -> list[dict[str, Any]]:
    """Parse all files and write chunks.jsonl."""
    chunks = parse_directory(input_dir, course_id=course_id)
    write_jsonl(out_file, chunks)
    return chunks
