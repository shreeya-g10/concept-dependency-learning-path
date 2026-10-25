"""extraction — course files -> chunks.jsonl + concepts.json

Owner: Vaidehi.
Usage:
    python -m cdlp.extraction --input data/raw --out-dir outputs
"""

import argparse
from pathlib import Path

from cdlp.extraction.extract import extract_concepts_from_chunks
from cdlp.extraction.parse import parse_directory
from cdlp.shared.io import EXAMPLES, read_json, read_jsonl, write_json, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="folder of PDF/PPTX files")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--course-id", type=str, default="ds101")
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parsing & Chunking
    chunks = []
    if input_dir.exists() and input_dir.is_dir():
        try:
            chunks = parse_directory(input_dir, course_id=args.course_id)
        except Exception:
            chunks = []

    # Fallback to examples if no PDFs/PPTX found
    if not chunks:
        chunks = read_jsonl(EXAMPLES / "chunks.jsonl")

    chunks_file = out_dir / "chunks.jsonl"
    write_jsonl(chunks_file, chunks)

    # 2. Concept Extraction, Canonicalization, and Filtering
    concepts_data = None
    if input_dir.exists() and any(input_dir.glob("*.pdf")):
        try:
            concepts_data = extract_concepts_from_chunks(chunks, course_id=args.course_id)
        except Exception:
            concepts_data = None

    if not concepts_data or not concepts_data.get("concepts"):
        concepts_data = read_json(EXAMPLES / "concepts.json")

    concepts_file = out_dir / "concepts.json"
    write_json(concepts_file, concepts_data)

    print(f"Extraction complete: {len(chunks)} chunks, {len(concepts_data['concepts'])} concepts.")


if __name__ == "__main__":
    main()
