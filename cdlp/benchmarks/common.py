"""Shared pieces of the benchmark loaders: slugs, concept records, outputs.

Every loader returns a list of Course objects (one per graph in the dataset), each
with concepts in our concepts.json shape and gold rows in our gold_edges.csv shape.

Benchmarks have no PDF pages, so a concept's `sources` entry points at the dataset
file it was first seen in, and `page` holds the 1-based LINE number in that file.
That keeps every concept traceable without inventing page numbers.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

# Same columns as data/gold/<course>/gold_edges.csv; label is hard / soft / none.
GOLD_COLUMNS = ["source", "target", "label", "agreement", "note"]
CONCEPTS_SCHEMA_VERSION = "1.0"


def slugify(name: str) -> str:
    """Wikipedia-style title -> stable slug.

    'Boosting_(machine_learning)' -> 'boosting_machine_learning'
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "concept"


class SlugMap:
    """Original name -> unique slug. Collisions get _2, _3 ... in first-seen order."""

    def __init__(self):
        self._by_name: dict[str, str] = {}
        self._taken: set[str] = set()
        self.collisions: list[tuple[str, str]] = []

    def __call__(self, name: str) -> str:
        if name not in self._by_name:
            base = slug = slugify(name)
            n = 2
            while slug in self._taken:
                slug = f"{base}_{n}"
                n += 1
            if slug != base:
                self.collisions.append((name, slug))
            self._by_name[name] = slug
            self._taken.add(slug)
        return self._by_name[name]


@dataclass
class Course:
    course_id: str
    slug: SlugMap = field(default_factory=SlugMap)
    concepts: dict[str, dict] = field(default_factory=dict)  # slug -> concept record
    rows: dict[tuple[str, str], dict] = field(default_factory=dict)  # (source, target) -> row

    def concept(self, name: str, doc: str, line: int, description: str = "") -> str:
        """Register a concept on first sight (keeps the first source) and return its slug."""
        cid = self.slug(name)
        if cid not in self.concepts:
            pretty = name.replace("_", " ").strip()
            record = {
                "id": cid,
                "name": pretty,
                "aliases": [name] if name != pretty else [],
                "sources": [{"doc": doc, "page": line}],
            }
            if description:
                record["description"] = description
            self.concepts[cid] = record
        return cid

    def edge(self, source: str, target: str, label: str, agreement: str = "", note: str = ""):
        """Add a gold row. A positive label wins over an earlier none for the same pair."""
        assert label in {"hard", "soft", "none"}, label
        if source == target:
            return
        key = (source, target)
        old = self.rows.get(key)
        if old is None or (old["label"] == "none" and label != "none"):
            self.rows[key] = {
                "source": source,
                "target": target,
                "label": label,
                "agreement": agreement,
                "note": note,
            }

    def stats(self) -> dict:
        labels = [r["label"] for r in self.rows.values()]
        return {
            "course_id": self.course_id,
            "concepts": len(self.concepts),
            "pairs": len(labels),
            "positive": sum(label != "none" for label in labels),
            "none": labels.count("none"),
            "slug_collisions": len(self.slug.collisions),
            # positives already implied by a path of other positives: > 0 means the
            # dataset labels shortcut pairs as prerequisites (see README conventions)
            "transitive_positives": len(implied_pairs(self.positive_pairs())),
        }

    def positive_pairs(self) -> set[tuple[str, str]]:
        return {k for k, r in self.rows.items() if r["label"] != "none"}

    def write(self, out_dir: Path) -> Path:
        from cdlp.shared.io import write_json

        folder = Path(out_dir) / self.course_id
        write_json(
            folder / "concepts.json",
            {
                "schema_version": CONCEPTS_SCHEMA_VERSION,
                "course_id": self.course_id,
                "concepts": sorted(self.concepts.values(), key=lambda c: c["id"]),
            },
        )
        write_gold_edges(folder / "gold_edges.csv", sorted(self.rows.values(), key=_row_key))
        return folder


def _successors(pairs) -> dict[str, set]:
    succ: dict[str, set] = {}
    for u, v in pairs:
        succ.setdefault(u, set()).add(v)
    return succ


def _reachable(succ: dict, start: str, skip: tuple | None = None) -> set:
    seen, stack = set(), [w for w in succ.get(start, ()) if (start, w) != skip]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(succ.get(node, ()))
    return seen


def transitive_closure(pairs) -> set[tuple[str, str]]:
    """All (u, w) with a directed path u -> ... -> w. Used to score our predicted edges
    against benchmarks whose positives include transitive pairs (README conventions)."""
    pairs = set(pairs)
    succ = _successors(pairs)
    return {(u, w) for u in succ for w in _reachable(succ, u) if u != w}


def implied_pairs(pairs) -> set[tuple[str, str]]:
    """Pairs that are also reachable through a path of the OTHER pairs (length >= 2)."""
    pairs = set(pairs)
    succ = _successors(pairs)
    return {(u, v) for u, v in pairs if v in _reachable(succ, u, skip=(u, v))}


def _row_key(row: dict) -> tuple:
    return (row["source"], row["target"])


def write_gold_edges(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GOLD_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path, delimiter: str = ",") -> list[list[str]]:
    """CSV/TSV rows with CRLF handled and blank lines dropped (line numbers kept 1-based)."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        return [[cell.strip() for cell in row] for row in csv.reader(f, delimiter=delimiter)]


def require(path: Path) -> Path:
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"{path} not found. Download the dataset first (see cdlp/benchmarks/README.md)."
        )
    return Path(path)
