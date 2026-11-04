"""Course-file parsing and text chunking for the extraction module.

Reads PDF (PyMuPDF), PPTX (python-pptx), Markdown, plain text and DOCX (python-docx),
splits text into 300-500 word chunks, and outputs records conforming to
chunk.schema.json.

What `page` means per format (the chunk's source reference):
- PDF: the page number. PPTX: the slide number.
- Markdown and DOCX: the section number. A section starts at each heading (Markdown
  `#` ... `######`; DOCX paragraphs styled Title / Heading n), and `heading` is that
  section's title. Text before the first heading is section 1, titled after the file.
- TXT: the page number when the file has form feeds (\f) between pages, else 1.
Chunk ids for Markdown, TXT and DOCX include the extension (`ch_notes_md_p2_0`), so
`notes.md` and `notes.pdf` in one course never share chunk ids.
Files named README* are documentation, not course material, and are skipped.
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

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


# ---- running headers and footers (PDF) ----------------------------------------------
# Book PDFs repeat a header and footer on every page: page numbers, "§6.1", the chapter
# or section title, "(continued from previous page)". Those lines are never a chunk's
# heading and are removed from the top / bottom of each page's text.
HEADER_ZONE, FOOTER_ZONE = 4, 2  # lines checked at the top / bottom of a page
_PAGE_NOISE = re.compile(
    r"^(\d{1,4}|[ivxlcdm]{1,7}|§\s?\d+(\.\d+)*|chapter \d+"
    r"|\(continued from previous page\)|\(continues on next page\))$",
    re.IGNORECASE,
)
_NOT_HEADING = re.compile(r"^(fig\.|figure|table|algorithm|listing|example)\b", re.IGNORECASE)


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def running_lines(pages: list[list[str]], min_share: float = 0.2) -> set[str]:
    """Normalised lines in the header / footer zone of at least max(3, 20%) of pages."""
    counts: dict[str, int] = {}
    for lines in pages:
        zone = {_norm(x) for x in lines[:HEADER_ZONE] + lines[-FOOTER_ZONE:] if x.strip()}
        for line in zone:
            counts[line] = counts.get(line, 0) + 1
    need = max(3, math.ceil(min_share * len(pages)))
    return {line for line, n in counts.items() if n >= need}


def is_page_noise(line: str) -> bool:
    return bool(_PAGE_NOISE.match(line.strip()))


def looks_like_heading(line: str) -> bool:
    """A title, not prose, code, maths or a figure caption: short, title case or
    numbered ("12.3.2 Multivariate Gradient Descent"), no code or maths characters."""
    line = line.strip()
    letters = sum(ch.isalpha() for ch in line)
    return (
        3 <= len(line) <= 80
        and (line[0].isupper() or line[0].isdigit())
        and not line.endswith((".", ",", ";", ":"))
        and not _NOT_HEADING.match(line)
        and not any(ch in line for ch in "=()[]{}<>")
        and letters >= 3
        and letters / len(line) >= 0.6
        and len(line.split()) <= 12
        and not is_page_noise(line)
        and (_SECTION_NUMBER.match(line) is not None or _title_case(line))
    )


_SECTION_NUMBER = re.compile(r"^\d+(\.\d+)+\s+\S")


def _title_case(line: str) -> bool:
    """Most words of 4+ letters capitalised ("Graph Traversal"), unlike a wrapped prose
    line ("To find the block that contains a particular element, we proceed the")."""
    long = [w for w in re.findall(r"[^\W\d_][\w'-]*", line) if len(w) > 3]
    return not long or sum(w[0].isupper() for w in long) / len(long) >= 0.6


def clean_page(lines: list[str], running: set[str]) -> tuple[str | None, list[str], list[str]]:
    """(heading, running titles, body lines) of one page, headers and footers removed.

    heading: the first title-like line near the top that is not a running title (a
    section heading printed on this page), else None. running titles: the title-like
    running header lines of this page (chapter or section titles).
    """
    lines = [x for x in lines if x.strip()]
    top = len(lines[:HEADER_ZONE])
    keep, titles = [], []
    for i, line in enumerate(lines):
        in_zone = i < top or i >= len(lines) - FOOTER_ZONE
        if in_zone and is_page_noise(line):
            continue
        if in_zone and _norm(line) in running:
            if i < top and looks_like_heading(line):
                titles.append(line.strip())
            continue
        keep.append(line)
    heading = None
    for line in keep[:3]:
        if looks_like_heading(line):
            heading = line.strip()
            keep.remove(line)
            break
        if len(line.split()) > 12:  # prose has started: no heading further down
            break
    return heading, titles, keep


def parse_pdf(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a PDF with PyMuPDF; running headers / footers are removed.

    Heading per page: a section heading printed on the page; else a running title seen
    for the first time in this file (a new section started); else the previous page's
    heading when it was one of those two (the section continues); else this
    page's running title; else the previous heading; else "<file> Page n".
    """
    if fitz is None:
        return []
    doc = fitz.open(path)
    pages = [doc[i].get_text().splitlines() for i in range(len(doc))]
    doc.close()
    running = running_lines(pages)
    clean_stem = re.sub(r"[^a-zA-Z0-9_]", "_", path.stem).lower()
    chunks: list[dict[str, Any]] = []
    previous, previous_specific, seen_titles = None, False, set()
    for page_idx, lines in enumerate(pages):
        page_num = page_idx + 1
        found, titles, body_lines = clean_page(lines, running)
        new_titles = [t for t in titles if t not in seen_titles]
        seen_titles.update(titles)
        if found:
            heading, previous_specific = found, True
        elif new_titles:  # a running title not seen before in this file: a new section
            heading, previous_specific = new_titles[-1], True
        elif previous and previous_specific:
            heading = previous
        else:
            heading = (titles[-1] if titles else None) or previous
            heading, previous_specific = heading or f"{path.stem} Page {page_num}", False
        previous = heading
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        for chunk_idx, piece in enumerate(chunk_text(body)):
            chunks.append(
                {
                    "chunk_id": f"ch_{clean_stem}_p{page_num}_{chunk_idx}",
                    "course_id": course_id,
                    "doc": path.name,
                    "page": page_num,
                    "heading": heading,
                    "text": piece,
                }
            )
    return chunks


def parse_pptx(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a PPTX slide deck using python-pptx and return structured chunk dictionaries."""
    if Presentation is None:
        return []
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


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_FENCE = re.compile(r"^\s*(```|~~~)")


def strip_markdown(text: str) -> str:
    """Plain text from Markdown: no images, link targets, emphasis or HTML comments."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"(\*\*|\*|`)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # emphasis, code
    # _emphasis_ only at word edges, so snake_case names keep their underscores
    text = re.sub(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)  # block quotes
    text = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", text, flags=re.M)  # list markers
    return text


def markdown_sections(text: str, default_heading: str) -> list[tuple[str, str]]:
    """(heading, body) per section; fenced code blocks are dropped."""
    sections: list[tuple[str, list[str]]] = [(default_heading, [])]
    in_fence = False
    for line in text.splitlines():
        if _MD_FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _MD_HEADING.match(line)
        if match:
            sections.append((strip_markdown(match.group(2)).strip() or default_heading, []))
        else:
            sections[-1][1].append(line)
    return [(h, strip_markdown("\n".join(lines))) for h, lines in sections]


def docx_sections(path: Path, default_heading: str) -> list[tuple[str, str]]:
    """(heading, body) per section of a DOCX file, tables included as `a | b` rows."""
    import docx  # python-docx

    document = docx.Document(str(path))
    sections: list[tuple[str, list[str]]] = [(default_heading, [])]
    body = document.element.body
    paragraphs = {p._p: p for p in document.paragraphs}
    tables = {t._tbl: t for t in document.tables}
    for element in body.iterchildren():  # document order, so tables stay in their section
        if element in paragraphs:
            para = paragraphs[element]
            text = para.text.strip()
            style = (para.style.name if para.style is not None else "").lower()
            if text and style.startswith(("heading", "title")):
                sections.append((text, []))
            elif text:
                sections[-1][1].append(text)
        elif element in tables:
            for row in tables[element].rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    sections[-1][1].append(" | ".join(dict.fromkeys(cells)))
    return [(h, "\n\n".join(lines)) for h, lines in sections]


def _section_chunks(
    path: Path, sections: list[tuple[str, str]], course_id: str
) -> list[dict[str, Any]]:
    """Chunk records for numbered sections; empty sections keep their number."""
    stem = re.sub(r"[^a-zA-Z0-9_]", "_", f"{path.stem}_{path.suffix[1:]}").lower()
    chunks: list[dict[str, Any]] = []
    for number, (heading, body) in enumerate(sections, start=1):
        for index, piece in enumerate(chunk_text(body)):
            chunks.append(
                {
                    "chunk_id": f"ch_{stem}_p{number}_{index}",
                    "course_id": course_id,
                    "doc": path.name,
                    "page": number,
                    "heading": heading,
                    "text": piece,
                }
            )
    return chunks


def parse_markdown(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Markdown: one numbered section per heading (see the module docstring)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = markdown_sections(text, path.stem)
    if sections and not clean_text(sections[0][1]):
        sections = sections[1:]  # no text before the first heading: start at its section
    return _section_chunks(path, sections, course_id)


def parse_docx(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """DOCX: one numbered section per Title / Heading paragraph."""
    sections = docx_sections(path, path.stem)
    if sections and not clean_text(sections[0][1]):
        sections = sections[1:]
    return _section_chunks(path, sections, course_id)


def parse_txt(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Plain text: pages split at form feeds; headings found as for PDF pages."""
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = []
    for number, page in enumerate(text.split("\f"), start=1):
        sections.append(extract_heading_and_body(page, f"{path.stem} Page {number}"))
    return _section_chunks(path, sections, course_id)


PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".ppt": parse_pptx,
    ".md": parse_markdown,
    ".markdown": parse_markdown,
    ".txt": parse_txt,
    ".docx": parse_docx,
}
SUPPORTED_SUFFIXES = tuple(PARSERS)


def is_course_file(path: Path) -> bool:
    """A file extraction reads: a supported type and not a README."""
    return (
        path.is_file()
        and path.suffix.lower() in PARSERS
        and not path.name.lower().startswith("readme")
    )


def parse_file(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a single file of any supported type (others give no chunks)."""
    parser = PARSERS.get(path.suffix.lower())
    return parser(path, course_id=course_id) if parser else []


def parse_directory(input_dir: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse every supported course file in a directory (not its subfolders)."""
    all_chunks: list[dict[str, Any]] = []
    input_path = Path(input_dir)

    supported = sorted(p for p in input_path.iterdir() if is_course_file(p))

    for file_path in supported:
        chunks = parse_file(file_path, course_id=course_id)
        all_chunks.extend(chunks)

    return all_chunks


def apply_chunk_limit(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict | None]:
    """Apply CDLP_MAX_CHUNKS. Returns (chunks to use, what was cut, or None if nothing was).

    A cut run reads only part of the notes, so it warns and callers record the second value
    in their outputs (chunks_truncated): the cut can never pass unnoticed.
    """
    limit = int(os.environ.get("CDLP_MAX_CHUNKS", "0") or "0")
    if limit <= 0 or len(chunks) <= limit:
        return chunks, None
    print(
        f"WARNING: CDLP_MAX_CHUNKS={limit}: kept {limit} of {len(chunks)} chunks. "
        "This run read only part of the notes.",
        file=sys.stderr,
        flush=True,
    )
    return chunks[:limit], {"kept": limit, "total": len(chunks), "limit_from": "CDLP_MAX_CHUNKS"}


def parse_and_save(
    input_dir: Path, out_file: Path, course_id: str = "ds101"
) -> list[dict[str, Any]]:
    """Parse all files and write chunks.jsonl."""
    chunks, _ = apply_chunk_limit(parse_directory(input_dir, course_id=course_id))
    write_jsonl(out_file, chunks)
    return chunks
