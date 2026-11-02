"""extraction — course files -> chunks.jsonl + concepts.json

Owner: Vaidehi.
Usage:
    python -m cdlp.extraction --input data/raw --out-dir outputs
"""

import argparse
import sys
from pathlib import Path

from cdlp.extraction.extract import ExtractionError, extract_concepts_from_chunks
from cdlp.extraction.parse import parse_directory
from cdlp.shared.io import EXAMPLES, read_json, read_jsonl, write_json, write_jsonl

COURSE_SUFFIXES = (".pdf", ".pptx", ".ppt")  # what cdlp.extraction.parse reads


def fail(message: str, code: int = 1) -> None:
    print(f"extraction failed: {message}", file=sys.stderr)
    sys.exit(code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="folder of PDF/PPTX files")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--course-id", "--course", dest="course_id", type=str, default=None)
    parser.add_argument(
        "--allow-tfidf",
        action="store_true",
        help="deduplicate with TF-IDF when the embedding model is unavailable (loud warning; "
        "recorded as dedup_method in concepts.json). Default: fail.",
    )
    parser.add_argument(
        "--allow-rule-based",
        action="store_true",
        help="use the keyword catalog when the LLM is unreachable or fails for many chunks "
        "(loud warning; recorded as extraction_method). Default: fail.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Infer course_id if not explicitly provided
    course_id = args.course_id
    if not course_id:
        if input_dir.name in ("ds101", "ml101"):
            course_id = input_dir.name
        elif out_dir.name in ("ds101", "ml101"):
            course_id = out_dir.name
        else:
            course_id = "ds101"

    # Course files present: every failure is reported (exit 1 / 2), never replaced by the
    # shared examples. The examples are used only when the folder has no course file
    # (e.g. the contract test runs on data/raw/, which holds only a README).
    course_files = input_dir.is_dir() and any(
        p.is_file()
        and p.suffix.lower() in COURSE_SUFFIXES
        and not p.name.lower().startswith("readme")
        for p in input_dir.iterdir()
    )
    if not course_files:
        print(f"note: no course files in {input_dir}; writing the shared example files")
        write_jsonl(out_dir / "chunks.jsonl", read_jsonl(EXAMPLES / "chunks.jsonl"))
        write_json(out_dir / "concepts.json", read_json(EXAMPLES / "concepts.json"))
        return

    # 1. Parsing & Chunking
    try:
        chunks = parse_directory(input_dir, course_id=course_id)
    except Exception as exc:
        fail(f"parsing {input_dir} failed: {exc!r}")
    if not chunks:
        fail(f"{input_dir} has course files but no text was extracted (is PyMuPDF installed?)")
    write_jsonl(out_dir / "chunks.jsonl", chunks)

    # 2. Concept Extraction, Canonicalization, and Filtering
    try:
        concepts_data = extract_concepts_from_chunks(
            chunks,
            course_id=course_id,
            allow_tfidf=args.allow_tfidf,
            allow_rule_based=args.allow_rule_based,
        )
    except ExtractionError as exc:  # LLM or embedding unavailable and not allowed
        fail(str(exc), code=2)
    except Exception as exc:
        fail(f"concept extraction failed: {exc!r}")
    if not concepts_data.get("concepts"):
        fail("concept extraction found no concepts")

    concepts_file = out_dir / "concepts.json"
    write_json(concepts_file, concepts_data)

    print(f"Extraction complete: {len(chunks)} chunks, {len(concepts_data['concepts'])} concepts.")


if __name__ == "__main__":
    main()
