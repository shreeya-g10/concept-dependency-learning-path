"""Rebuild the second-source Markdown files in data/raw/ (see data/raw/README.md).

    python scripts/fetch_second_sources.py           # download, verify, convert
    python scripts/fetch_second_sources.py --check   # also fail if a file would change

Downloads each pinned source (OpenDSA RST at a fixed commit; the IMS chapter page),
checks its SHA-256 against the value in data/raw/README.md, and converts it to Markdown:
headings and prose kept; directives, figures, code, R output, tables and exercises
removed. The IMS page is not pinned to a commit by its site, so a changed page fails the
hash check instead of silently changing the course material.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENDSA_COMMIT = "f900a7aa3d7fd4289b82a767e4958974eb3e9d17"
OPENDSA = f"https://raw.githubusercontent.com/OpenDSA/OpenDSA/{OPENDSA_COMMIT}/RST/en/"
OPENDSA_HEADER = (
    "<!-- Source: OpenDSA (opendsa.org), commit f900a7a, RST/en/{rel}.rst. MIT License, "
    "Copyright (c) 2011-2025 Ville Karavirta and Cliff Shaffer. Converted to Markdown; "
    "directives, figures, visualizations and code removed. See data/raw/README.md. -->"
)
IMS_URL = "https://openintrostat.github.io/ims/model-logistic.html"
IMS_HEADER = (
    "<!-- Source: Introduction to Modern Statistics, 2nd ed. (Cetinkaya-Rundel and Hardin), "
    f"chapter 9 Logistic regression, {IMS_URL}. CC BY-SA 3.0. Converted to Markdown; code, "
    "R output, figures, tables and exercises removed. See data/raw/README.md. -->"
)
# (source path, SHA-256 of the downloaded file, output file)
SOURCES = [
    (
        "RecurTutor/RecIntro",
        "ecf202c176ee3084ea4be8ac21bb474ecc20e27b4efcd5dae63278d5b59a862a",
        "ds101/opendsa_recursion_intro.md",
    ),
    (
        "RecurTutor/Write",
        "df67a98aae7f207eef544d70ab0831ebe50405a9f98e0ef6a48d517affdfa704",
        "ds101/opendsa_recursion_writing.md",
    ),
    (
        "RecurTutor/Trace",
        "3e6717db99d529ca9151a67e2a0d2729a2798e5cd9b9574e0acd7b0828131d14",
        "ds101/opendsa_recursion_tracing.md",
    ),
    (
        "General/GenTreeIntro",
        "1ebe8cf589c2cd67706755a19498d37f73a8a6765e1f22876a601a0879f1347b",
        "ds101/opendsa_general_trees.md",
    ),
    (
        "SearchStruct/BalancedTree",
        "504c6920779be7dea04773052d90d88aee3e041e438a972c5bb7f32e4beb9bea",
        "ds101/opendsa_balanced_trees.md",
    ),
    (
        "SearchStruct/AVL",
        "306f8d021fa6167b08124910ebb03f20bf68e5f789b907e01b600ce45dcbc6e4",
        "ds101/opendsa_avl_trees.md",
    ),
]
IMS_SHA256 = "de5535d073d230409a64812c31652e984910c6be1b4727c4a5cfe93c496dbbd0"
IMS_OUT = "ml101/ims_09_logistic_regression.md"


# ---- RST (OpenDSA) -> Markdown ---------------------------------------------------
KEEP_BODY = {"note", "topic", "admonition", "warning", "tip", "important", "hint"}
UNDER = re.compile(r"^([=\-~^*+#\"'`])\1{2,}\s*$")


def inline(t):
    t = re.sub(r"(Figures?|Tables?)?\s*:num:`[^`]*`", "the figure", t)
    t = re.sub(r"^(\(#\)|#\.)\s+", "- ", t)
    t = re.sub(r":(term|ref|doc|numref):`([^`<]+?)\s*<[^`>]*>`", r"\2", t)
    t = re.sub(r":[a-z]+:`([^`]*)`", r"\1", t)
    t = t.replace("``", "`")
    t = re.sub(r"\\([\\*_`|])", r"\1", t)
    return t


def convert(text, header):
    lines = text.splitlines()
    out, levels, i = [header, ""], [], 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\.\.\s+([\w-]+)::", line)
        if line.startswith(".."):
            keep = bool(m) and m.group(1) in KEEP_BODY
            i += 1
            body = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                body.append(lines[i])
                i += 1
            if keep:
                body = [b.strip() for b in body if not b.strip().startswith(":")]
                out.extend(inline(b) for b in body)
            continue
        if (
            i + 1 < len(lines)
            and line.strip()
            and UNDER.match(lines[i + 1])
            and len(lines[i + 1].strip()) >= len(line.strip())
        ):
            ch = lines[i + 1].strip()[0]
            if ch not in levels:
                levels.append(ch)
            out += ["", "#" * min(levels.index(ch) + 1, 6) + " " + inline(line.strip()), ""]
            i += 2
            continue
        if UNDER.match(line):  # overline of a title
            i += 1
            continue
        out.append(inline(line.strip()) if line.strip() else "")
        i += 1
    md = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


# ---- rendered Quarto HTML (IMS) -> Markdown --------------------------------------
SKIP_TAGS = {
    "script",
    "style",
    "pre",
    "figure",
    "nav",
    "footer",
    "header",
    "button",
    "svg",
    "table",
}
SKIP_CLASSES = ("cell-output", "sourceCode", "footnotes", "quarto-figure", "exercises")
BLOCK = {"p": "", "li": "", "h1": "#", "h2": "#", "h3": "##", "h4": "###", "h5": "####"}
VOID = {"img", "br", "hr", "meta", "link", "input", "source", "col", "wbr"}


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.main = False
        self.skip = None
        self.depth = 0
        self.cur = None
        self.buf = []
        self.out = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "main" and a.get("id") == "quarto-document-content":
            self.main = True
            return
        if not self.main or tag in VOID:
            return
        if self.skip:
            self.depth += tag == self.skip
            return
        cls = a.get("class") or ""
        if (
            tag in SKIP_TAGS
            or any(c in cls for c in SKIP_CLASSES)
            or a.get("id") in ("footnotes",)
            or (a.get("id") or "").startswith("sec-exercises")
        ):
            self.skip, self.depth = tag, 1
            return
        if tag in BLOCK:
            self.cur, self.buf = tag, []

    def handle_endtag(self, tag):
        if tag == "main" and self.main:
            self.main = False
            return
        if self.skip:
            if tag == self.skip:
                self.depth -= 1
                if self.depth == 0:
                    self.skip = None
            return
        if tag == self.cur:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if text:
                self.out.append(f"{BLOCK[tag]} {text}" if BLOCK[tag] else text)
            self.cur = None

    def handle_data(self, data):
        if self.main and not self.skip and self.cur:
            self.buf.append(data)


def html_to_markdown(text: str, header: str) -> str:
    parser = P()
    parser.feed(text)
    blocks = parser.out
    cut = next((i for i, b in enumerate(blocks) if re.match(r"^#+ [\d.]+ Exercises", b)), None)
    blocks = blocks[:cut]  # the exercises section is dropped, as for the ODS / D2L material
    return header + "\n\n" + "\n\n".join(blocks) + "\n"


def fetch(url: str, sha256: str) -> str:
    import requests  # certifi's CA bundle; urllib lacks one on python.org macOS builds

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.content
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise SystemExit(f"{url}: SHA-256 {digest} does not match the recorded {sha256}")
    return data.decode("utf-8")


def build() -> dict[str, str]:
    """{output path under data/raw/: Markdown}."""
    files = {}
    for rel, sha, out in SOURCES:
        files[out] = convert(fetch(f"{OPENDSA}{rel}.rst", sha), OPENDSA_HEADER.format(rel=rel))
    files[IMS_OUT] = html_to_markdown(fetch(IMS_URL, IMS_SHA256), IMS_HEADER)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if a file would change")
    args = parser.parse_args(argv)
    changed = []
    for out, text in build().items():
        path = ROOT / "data" / "raw" / out
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            changed.append(out)
            if not args.check:
                path.write_text(text, encoding="utf-8")
    print("changed: " + (", ".join(changed) or "nothing"))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
