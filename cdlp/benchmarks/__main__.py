"""benchmarks: public prerequisite dataset -> concepts.json + gold_edges.csv per graph

    python -m cdlp.benchmarks --dataset al_cpl            # raw: data/benchmarks/al_cpl/
    python -m cdlp.benchmarks --dataset university_course
    python -m cdlp.benchmarks --dataset lecturebank

Writes <out-dir>/<course_id>/concepts.json and gold_edges.csv for every graph in the
dataset (AL-CPL has four domains, the others one). Default out-dir is
outputs/benchmarks/; both data/benchmarks/ and outputs/ stay out of git.
See cdlp/benchmarks/README.md for download steps, versions and licences.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cdlp.benchmarks import al_cpl, lecturebank, university_course
from cdlp.benchmarks.common import GOLD_COLUMNS, write_gold_edges  # noqa: F401 (re-export)

LOADERS = {
    "al_cpl": al_cpl.load,
    "university_course": university_course.load,
    "lecturebank": lecturebank.load,
}
DATASETS = list(LOADERS)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument(
        "--raw", type=Path, help="downloaded folder (default data/benchmarks/<dataset>)"
    )
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/benchmarks"))
    args = parser.parse_args(argv)

    raw = args.raw or Path("data/benchmarks") / args.dataset
    for course in LOADERS[args.dataset](raw):
        folder = course.write(args.out_dir)
        s = course.stats()
        print(
            f"{s['course_id']}: {s['concepts']} concepts, {s['pairs']} pairs "
            f"({s['positive']} positive, {s['none']} none), "
            f"{s['slug_collisions']} slug collisions -> {folder}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
