"""University Course dataset (Liang et al. 2017, "CPR-Recover", Release 1).

Files in <raw>/:
    cs_annotations.tsv  header Concept_A, Concept_B, Annotator_1..Annotator_13;
                        3 annotators per pair, empty cells otherwise. Labels:
                        1 = B is a prerequisite of A, 2 = A is a prerequisite of B,
                        3 = no prerequisite relation.
                        The released file also holds label 4 (99 votes), which the
                        dataset README does not define. Those votes are DROPPED: they
                        count neither for nor against a direction, and are left out of
                        the k/n agreement shares. Any other unknown label is an error.
    cs_preqs.csv        the authors' majority-vote positives "A,B" (B is a prerequisite of A)

cs_preqs.csv is the official gold: each pair in it becomes B -> A, hard, with
agreement "k/n" = annotators who chose that direction / annotators of the pair.
An annotated pair absent from cs_preqs.csv (in either order) becomes none; its row
is written B -> A (the direction the dataset asks about) with the share of "3" votes.
The dataset does not distinguish hard from soft, so every positive is hard.
"""

from __future__ import annotations

from pathlib import Path

from cdlp.benchmarks.common import Course, read_rows, require

COURSE_ID = "university_course"
LABEL_B_BEFORE_A, LABEL_A_BEFORE_B, LABEL_NONE = "1", "2", "3"
LABEL_UNDEFINED = "4"  # in the data, not in the dataset README: dropped


def load(raw: Path) -> list[Course]:
    raw = Path(raw)
    annotations_file = require(raw / "cs_annotations.tsv")
    preqs_file = require(raw / "cs_preqs.csv")
    course = Course(course_id=COURSE_ID)

    rows = read_rows(annotations_file, delimiter="\t")
    header = rows[0]
    if header[:2] != ["Concept_A", "Concept_B"]:
        raise ValueError(f"{annotations_file.name}: unexpected header {header[:3]}")
    votes: dict[frozenset, list[tuple[str, str, str]]] = {}  # pair -> [(A, B, label)]
    first_line: dict[frozenset, tuple[int, str, str]] = {}
    for line, row in enumerate(rows[1:], start=2):
        if not any(row):
            continue
        a, b, *labels = row
        labels = [label for label in labels if label and label != LABEL_UNDEFINED]
        bad = set(labels) - {LABEL_B_BEFORE_A, LABEL_A_BEFORE_B, LABEL_NONE}
        if bad:
            raise ValueError(f"{annotations_file.name} line {line}: unknown labels {sorted(bad)}")
        key = frozenset((a, b))
        votes.setdefault(key, []).extend((a, b, label) for label in labels)
        first_line.setdefault(key, (line, a, b))
        course.concept(a, annotations_file.name, line)
        course.concept(b, annotations_file.name, line)

    def support(prereq: str, dependent: str, key: frozenset) -> str:
        """Share of this pair's votes saying prereq comes before dependent."""
        cast = votes.get(key, [])
        agree = sum(
            (label == LABEL_B_BEFORE_A and (b, a) == (prereq, dependent))
            or (label == LABEL_A_BEFORE_B and (a, b) == (prereq, dependent))
            for a, b, label in cast
        )
        return f"{agree}/{len(cast)}" if cast else ""

    positive_pairs = set()
    for line, row in enumerate(read_rows(preqs_file), start=1):
        if not any(row):
            continue
        if len(row) != 2:
            raise ValueError(f"{preqs_file.name} line {line}: expected 2 columns, got {len(row)}")
        a, b = row  # b is a prerequisite of a
        key = frozenset((a, b))
        positive_pairs.add(key)
        src = course.concept(b, preqs_file.name, line)
        tgt = course.concept(a, preqs_file.name, line)
        course.edge(src, tgt, "hard", support(b, a, key), "majority vote (cs_preqs.csv)")

    for key, (_, a, b) in first_line.items():
        if key in positive_pairs:
            continue
        cast = votes[key]
        none_votes = sum(label == LABEL_NONE for _, _, label in cast)
        course.edge(
            course.slug(b),
            course.slug(a),
            "none",
            f"{none_votes}/{len(cast)}",
            "not in cs_preqs.csv",
        )
    return [course]
