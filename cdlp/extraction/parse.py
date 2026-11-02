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

import re
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


def parse_pdf(path: Path, course_id: str = "ds101") -> list[dict[str, Any]]:
    """Parse a PDF document using PyMuPDF and return structured chunk dictionaries."""
    if fitz is None:
        return []
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


def parse_and_save(
    input_dir: Path, out_file: Path, course_id: str = "ds101"
) -> list[dict[str, Any]]:
    """Parse all files and write chunks.jsonl."""
    chunks = parse_directory(input_dir, course_id=course_id)
    write_jsonl(out_file, chunks)
    return chunks
