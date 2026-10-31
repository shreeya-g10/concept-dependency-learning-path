"""benchmarks — public prerequisite dataset -> concepts.json + gold_edges.csv

    python -m cdlp.benchmarks --dataset al_cpl --raw data/benchmarks/al_cpl \
        --out-dir outputs/benchmarks/al_cpl
"""

import argparse
import csv
from pathlib import Path

from cdlp.shared.io import EXAMPLES, read_json, write_json

DATASETS = ["al_cpl", "university_course", "lecturebank"]
# Same columns as data/gold/gold_edges.csv; label is hard / soft / none.
GOLD_COLUMNS = ["source", "target", "label", "agreement", "note"]


def write_gold_edges(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GOLD_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument("--raw", type=Path, required=True, help="downloaded dataset folder")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    # TODO(Shreeya): one converter per dataset: read args.raw, map concepts to stable
    # slugs (course_id = dataset name) and labelled pairs to hard / soft / none.
    write_json(args.out_dir / "concepts.json", read_json(EXAMPLES / "concepts.json"))
    graph = read_json(EXAMPLES / "validated_graph.json")
    write_gold_edges(
        args.out_dir / "gold_edges.csv",
        [
            {"source": e["source"], "target": e["target"], "label": e["strength"], "note": "stub"}
            for e in graph["edges"]
            if e["decision"] == "ACCEPT"
        ],
    )


if __name__ == "__main__":
    main()
