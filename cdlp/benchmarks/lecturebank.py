"""LectureBank 1.0 prerequisite annotation (Li et al., AAAI 2019), from LB-Paper/.

Files in <raw>/LB-Paper/ (or <raw>/ directly), both without a header:
    208topics.csv                ID, Topic, Wiki_Page_URL
    prerequisite_annotation.csv  Source_Topic_ID, Target_Topic_ID, If_prerequisite (0/1)

The paper: "If concept A is a prerequisite of concept B, the edge direction goes from
concept vertex A to concept vertex B", and the released positives are the
intersection of two annotators' labels. So If_prerequisite = 1 becomes
Source -> Target, hard, agreement "2/2"; 0 becomes none with agreement left empty,
because 0 also covers pairs where exactly one annotator said yes. The README itself
does not state the direction; it is taken from the paper's convention and the
column names. Binary labels only, so every positive is hard.
"""

from __future__ import annotations

from pathlib import Path

from cdlp.benchmarks.common import Course, read_rows, require

COURSE_ID = "lecturebank"


def _data_dir(raw: Path) -> Path:
    return raw / "LB-Paper" if (raw / "LB-Paper").is_dir() else raw


def load(raw: Path) -> list[Course]:
    data = _data_dir(Path(raw))
    topics_file = require(data / "208topics.csv")
    annotation_file = require(data / "prerequisite_annotation.csv")
    course = Course(course_id=COURSE_ID)

    by_id: dict[str, str] = {}
    lines = topics_file.read_text(encoding="utf-8").splitlines()
    for line, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        # a topic name may itself contain a comma: ID before the first comma, URL after
        # the last one, name (kept exactly) in between
        topic_id, sep, rest = text.partition(",")
        if not sep or not rest.strip():
            raise ValueError(f"{topics_file.name} line {line}: expected ID, Topic, URL")
        name, _, url = rest.rpartition(",")
        if not url.strip().startswith("http"):
            name, url = rest, ""
        by_id[topic_id.strip()] = course.concept(
            name.strip(), topics_file.name, line, description=url.strip()
        )

    for line, row in enumerate(read_rows(annotation_file), start=1):
        if not any(row):
            continue
        if len(row) != 3:
            raise ValueError(f"{annotation_file.name} line {line}: expected 3 columns")
        src_id, tgt_id, flag = row
        if src_id not in by_id or tgt_id not in by_id:
            raise ValueError(f"{annotation_file.name} line {line}: unknown topic id")
        if flag == "1":
            course.edge(by_id[src_id], by_id[tgt_id], "hard", "2/2", "both annotators")
        elif flag == "0":
            course.edge(by_id[src_id], by_id[tgt_id], "none", "", "not in both annotators")
        else:
            raise ValueError(f"{annotation_file.name} line {line}: If_prerequisite {flag!r}")
    return [course]
