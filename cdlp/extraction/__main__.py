"""extraction — course files -> chunks.jsonl + concepts.json

python -m cdlp.extraction --input data/raw --out-dir outputs
"""

import argparse
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, read_jsonl, write_json, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="folder of PDF/PPTX files")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Vaidehi): replace with real parsing, chunking, extraction and dedup.
    # Until then the stub copies the shared example so everyone downstream can run.
    write_jsonl(args.out_dir / "chunks.jsonl", read_jsonl(EXAMPLES / "chunks.jsonl"))
    write_json(args.out_dir / "concepts.json", read_json(EXAMPLES / "concepts.json"))


if __name__ == "__main__":
    main()
