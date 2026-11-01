"""AL-CPL (Liang et al. 2018): four domains of Wikipedia-concept pairs.

Files in <raw>/data/ (or <raw>/ directly):
    <domain>.pairs   every labelled pair "A,B" (positive and negative)
    <domain>.preqs   positive pairs only  "A,B"
In both, column 2 (B) is a prerequisite of column 1 (A). So a positive becomes the
gold row B -> A, hard; a pair only in .pairs becomes B -> A, none. The dataset has
one annotation per pair (expert-corrected) and no agreement figure, and it does not
distinguish hard from soft, so every positive is hard.

Caveat for evaluation: the authors added positives by transitivity, so AL-CPL marks
shortcut pairs as prerequisites, while our gold marks them none.
"""

from __future__ import annotations

from pathlib import Path

from cdlp.benchmarks.common import Course, read_rows, require

DOMAINS = ("data_mining", "geometry", "physics", "precalculus")


def _data_dir(raw: Path) -> Path:
    return raw / "data" if (raw / "data").is_dir() else raw


def _pairs(path: Path) -> list[tuple[int, str, str]]:
    out = []
    for line, row in enumerate(read_rows(path), start=1):
        if not any(row):
            continue
        if len(row) != 2:
            raise ValueError(f"{path.name} line {line}: expected 2 columns, got {len(row)}")
        out.append((line, row[0], row[1]))
    return out


def load(raw: Path, domains: tuple[str, ...] = DOMAINS) -> list[Course]:
    data = _data_dir(Path(raw))
    courses = []
    for domain in domains:
        course = Course(course_id=f"al_cpl_{domain}")
        pairs_file = require(data / f"{domain}.pairs")
        preqs_file = require(data / f"{domain}.preqs")
        positives = {(a, b) for _, a, b in _pairs(preqs_file)}

        for line, a, b in _pairs(pairs_file):
            src = course.concept(b, pairs_file.name, line)
            tgt = course.concept(a, pairs_file.name, line)
            if (a, b) in positives:
                course.edge(src, tgt, "hard", note="AL-CPL positive")
            else:
                course.edge(src, tgt, "none", note="AL-CPL negative")
        # positives missing from .pairs (should not happen, but never drop a label)
        for line, a, b in _pairs(preqs_file):
            src = course.concept(b, preqs_file.name, line)
            tgt = course.concept(a, preqs_file.name, line)
            course.edge(src, tgt, "hard", note="AL-CPL positive (only in .preqs)")
        courses.append(course)
    return courses
