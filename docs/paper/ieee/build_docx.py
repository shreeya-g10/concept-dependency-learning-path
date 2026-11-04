"""Builds paper_ieee.docx, the editable IEEE-format paper. Run with the project venv.

Every number here comes from a results file; docs/paper/results/tables.md and
cdlp/*/results/ are the sources. RQ1 and RQ3 have no results yet, so the paper says so.
"""

# ruff: noqa: E501
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

HERE = Path(__file__).parent
OUT = HERE / "paper_ieee.docx"
FONT = "Times New Roman"
TOKEN = re.compile(r"(</?(?:i|b|sub|sup)>)")
M = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'


def set_font(style, size, *, bold=None, italic=None, small_caps=None):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    style.font.small_caps = small_caps
    style.font.color.rgb = None
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(key), FONT)
    for key in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if fonts.get(qn(key)) is not None:
            del fonts.attrib[qn(key)]


def spacing(style, before=0, after=0, line=1.0):
    fmt = style.paragraph_format
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE if line == 1.0 else WD_LINE_SPACING.MULTIPLE


def setup() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1.0)
    sec.left_margin, sec.right_margin = Inches(0.625), Inches(0.625)
    st = doc.styles
    set_font(st["Normal"], 10)
    spacing(st["Normal"], after=3)
    st["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    st["Normal"].paragraph_format.first_line_indent = Inches(0.14)
    set_font(st["Title"], 24)
    spacing(st["Title"], after=10)
    st["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    st["Title"].paragraph_format.first_line_indent = Inches(0)
    border = st["Title"].element.get_or_add_pPr().find(qn("w:pBdr"))
    if border is not None:
        st["Title"].element.get_or_add_pPr().remove(border)
    set_font(st["Heading 1"], 10, bold=False, small_caps=True)
    spacing(st["Heading 1"], before=8, after=4)
    st["Heading 1"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    st["Heading 1"].paragraph_format.first_line_indent = Inches(0)
    st["Heading 1"].paragraph_format.keep_with_next = True
    set_font(st["Heading 2"], 10, bold=False, italic=True)
    spacing(st["Heading 2"], before=6, after=3)
    st["Heading 2"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    st["Heading 2"].paragraph_format.first_line_indent = Inches(0)
    st["Heading 2"].paragraph_format.keep_with_next = True
    for name in ("List Bullet", "List Number"):
        set_font(st[name], 10)
        spacing(st[name], after=2)
        st[name].paragraph_format.first_line_indent = Inches(-0.18)
        st[name].paragraph_format.left_indent = Inches(0.18)
        st[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_font(st["Caption"], 8, bold=False, italic=False)
    spacing(st["Caption"], before=4, after=4)
    st["Caption"].paragraph_format.first_line_indent = Inches(0)
    st["Caption"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return doc


def runs(par, text, size=None, *, bold=False, italic=False):
    states = {"i": italic, "b": bold, "sub": False, "sup": False}
    for part in TOKEN.split(text):
        tag = TOKEN.fullmatch(part)
        if tag:
            name = part.strip("</>")
            states[name] = not part.startswith("</")
            if name == "i" and part.startswith("</"):
                states["i"] = italic
            if name == "b" and part.startswith("</"):
                states["b"] = bold
            continue
        if not part:
            continue
        run = par.add_run(part)
        run.italic = states["i"] or None
        run.bold = states["b"] or None
        if states["sub"]:
            run.font.subscript = True
        if states["sup"]:
            run.font.superscript = True
        if size:
            run.font.size = Pt(size)
    return par


def mi(text, plain=False):
    style = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""
    return f'<m:r>{style}<m:t xml:space="preserve">{text}</m:t></m:r>'


def msub(base, sub):
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def msup(base, sup):
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"


def delim(inner, left="(", right=")"):
    return (
        f'<m:d><m:dPr><m:begChr m:val="{left}"/><m:endChr m:val="{right}"/></m:dPr>'
        f"<m:e>{inner}</m:e></m:d>"
    )


def equation(doc, omml, number):
    """A native, editable Word equation with its number at the right edge of the column."""
    par = doc.add_paragraph()
    par.paragraph_format.first_line_indent = Inches(0)
    par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    par.paragraph_format.space_before = Pt(3)
    par.paragraph_format.tab_stops.add_tab_stop(Inches(3.5), alignment=2)
    par._p.append(parse_xml(f"<m:oMath {M}>{omml}</m:oMath>"))
    par.add_run(f"\t({number})")


class Paper:
    def __init__(self):
        self.doc = setup()
        self.tables = 0
        self.figures = 0

    def h1(self, text):
        self.doc.add_heading(text, 1)

    def h2(self, text):
        self.doc.add_heading(text, 2)

    def p(self, text, *, indent=True):
        par = self.doc.add_paragraph()
        if not indent:
            par.paragraph_format.first_line_indent = Inches(0)
        return runs(par, text)

    def bullets(self, items, style="List Bullet"):
        for item in items:
            runs(self.doc.add_paragraph(style=style), item)

    def caption_table(self, roman, title):
        par = self.doc.add_paragraph(style="Caption")
        par.paragraph_format.keep_with_next = True
        run = par.add_run(f"TABLE {roman}")
        run.add_break()
        title_run = par.add_run(title)
        title_run.font.small_caps = True

    def table(
        self, roman, title, rows, widths, *, note=None, left_cols=1, bold_rows=(), flow=False
    ):
        self.caption_table(roman, title)
        tbl = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        ieee_rules(tbl, widths)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = tbl.cell(r, c)
                cell.width = Inches(widths[c])
                par = cell.paragraphs[0]
                par.paragraph_format.first_line_indent = Inches(0)
                par.paragraph_format.space_before = Pt(1)
                par.paragraph_format.space_after = Pt(1)
                par.paragraph_format.keep_with_next = not flow and (r < len(rows) - 1 or bool(note))
                par.paragraph_format.alignment = (
                    WD_ALIGN_PARAGRAPH.LEFT if c < left_cols else WD_ALIGN_PARAGRAPH.CENTER
                )
                runs(par, str(value), 8, bold=r == 0 or r in bold_rows)
        header = tbl.rows[0]._tr.get_or_add_trPr()
        header.append(OxmlElement("w:tblHeader"))
        for row in tbl.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        after = self.doc.add_paragraph()
        after.paragraph_format.first_line_indent = Inches(0)
        after.paragraph_format.space_before = Pt(2 if note else 0)
        after.paragraph_format.space_after = Pt(5 if note else 2)
        if note:
            runs(after, note, 8)
        else:
            after.add_run(" ").font.size = Pt(3)

    def figure(self, path, width, caption, alt):
        self.figures += 1
        par = self.doc.add_paragraph()
        par.paragraph_format.first_line_indent = Inches(0)
        par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(path), width=Inches(width))
        par._p.xpath(".//wp:docPr")[0].set("descr", alt)
        cap = self.doc.add_paragraph(style="Caption")
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        cap.add_run(f"Fig. {self.figures}. {caption}")


def border(parent, edge, size):
    item = OxmlElement(f"w:{edge}")
    item.set(qn("w:val"), "single" if size else "nil")
    item.set(qn("w:sz"), str(size))
    item.set(qn("w:space"), "0")
    item.set(qn("w:color"), "000000")
    parent.append(item)


def ieee_rules(tbl, widths):
    """Horizontal rules only: above the table, under the head row and below the table."""
    pr = tbl._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge, size in (
        ("top", 8),
        ("left", 0),
        ("bottom", 8),
        ("right", 0),
        ("insideH", 0),
        ("insideV", 0),
    ):
        border(borders, edge, size)
    pr.append(borders)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    pr.append(layout)
    for column, width in zip(tbl.columns, widths, strict=True):
        column.width = Inches(width)
    for cell in tbl.rows[0].cells:
        cell_borders = OxmlElement("w:tcBorders")
        border(cell_borders, "bottom", 4)
        cell._tc.get_or_add_tcPr().append(cell_borders)


def two_columns(section):
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), "2")
    cols.set(qn("w:space"), "360")


AUTHORS = [
    ("Shreeya Kiran Khairnar", "shreeyakiran04@gmail.com"),
    ("Vaidehi Kumawat", "vaidehikumawat2020@gmail.com"),
    ("Sneha Debnath", "snehadebnath2608@gmail.com"),
    ("Shrestha Sunil", "shrestha.sunil051@gmail.com"),
    ("Sangeetha J", ""),
]


def front_matter(paper):
    doc = paper.doc
    doc.add_paragraph(
        "Verify, Diagnose, Adapt: Agent-Validated Prerequisite Graphs for Student-Adaptive "
        "Learning Paths",
        style="Title",
    )
    tbl = doc.add_table(rows=2, cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cells = [tbl.cell(0, 0), tbl.cell(0, 1), tbl.cell(0, 2), tbl.cell(1, 0), tbl.cell(1, 1)]
    for cell, (name, mail) in zip(cells, AUTHORS, strict=True):
        cell.width = Inches(2.4)
        lines = [
            (name, 11, False),
            ("Dept. of Computer Science & Engg.", 10, True),
            ("M S Ramaiah Institute of Technology", 10, True),
            ("Bengaluru, India", 10, False),
        ]
        if mail:
            lines.append((mail, 10, False))
        for i, (text, size, italic) in enumerate(lines):
            par = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
            par.paragraph_format.first_line_indent = Inches(0)
            par.paragraph_format.space_after = Pt(0)
            par.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = par.add_run(text)
            run.font.size = Pt(size)
            run.italic = italic or None
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)
    two_columns(doc.add_section(WD_SECTION.CONTINUOUS))


def label_par(paper, label, text):
    par = paper.doc.add_paragraph()
    par.paragraph_format.first_line_indent = Inches(0.14)
    par.paragraph_format.space_after = Pt(6)
    run = par.add_run(label)
    run.bold, run.italic = True, True
    run.font.size = Pt(9)
    runs(par, text, 9, bold=True)


def body(paper):
    doc = paper.doc
    label_par(
        paper,
        "Abstract—",
        "Students often struggle with an advanced topic because they missed a concept it "
        "depends on, yet course material rarely states which concepts depend on which, or which "
        "gap a particular student has. Large language models (LLMs) can propose prerequisite "
        "relations cheaply, but they also propose relations that sound right without being "
        "needed. We present an end-to-end system that turns course files into a personalized, "
        "explainable learning path. An LLM proposes prerequisite edges, and an independent "
        "validation agent checks each one against course text with verified quotes, a judgment "
        "from a second model, and exact graph rules, then accepts it, rejects it, or sends it "
        "for human review. An adaptive quiz over the validated graph estimates what a student "
        "knows, and the student receives a path with cited sources. Early runs exposed three "
        "findings. A counterfactual “necessity test” was unstable on three example "
        "edges, so it does not influence decisions. On a real textbook, 12 of the 13 sampled "
        "concept pairs that received a link changed when the two concepts were swapped in the "
        "prompt, so course runs now ask both orders. On 500 simulated students over a "
        "five-concept graph, adaptive diagnosis used 14.4% fewer questions than asking every "
        "concept at similar accuracy (0.866 vs. 0.870), but only when knowledge followed the "
        "graph. This is work in progress: the main evaluation of edge validation on public "
        "benchmarks and full courses is pending, and all numbers are preliminary.",
    )
    label_par(
        paper,
        "Index Terms—",
        "prerequisite relation discovery, educational knowledge graph, large language models, "
        "LLM validation, adaptive diagnosis, personalized learning paths",
    )

    paper.h1("I. Introduction")
    paper.p(
        "Learning is cumulative. A student who says “I don’t understand AVL trees” "
        "may have no trouble with balancing at all; they may never have understood the ordering "
        "rule of binary search trees (BSTs). Telling them to revise AVL trees does not find that "
        "gap. A useful answer depends on two things: the dependency structure of the course, and "
        "where in that structure this student’s knowledge stops."
    )
    paper.p(
        "An instructor could draw a prerequisite map by hand, but this is slow for a course with "
        "hundreds of concepts, since the number of candidate concept pairs grows quadratically. "
        "LLMs can propose such maps at low cost [1], but they also generate plausible errors "
        "[2]. In a graph, one wrong edge adds an unnecessary branch to every learning path that "
        "passes through it, and a cycle destroys the ordering needed to produce a path at all."
    )
    paper.p(
        "We ask two linked questions. Can LLM-proposed prerequisite edges be checked, so that "
        "only supported edges enter the course graph? And can one validated course graph give "
        "each student a different path, based on what that student already knows?"
    )
    paper.p("We do not claim that prerequisite discovery is new. Our contributions are:")
    paper.bullets(
        [
            "An independent validation agent that combines course-text evidence with verified "
            "quotes, a semantic judgment from a different model, and graph-consistency rules, "
            "with three outcomes: accept, reject, or human review.",
            "A measurement of how LLM proposals depend on question order, and a discovery rule "
            "that asks both orders and keeps the disagreement visible.",
            "A study of a counterfactual necessity test, in which an LLM simulates a learner who "
            "lacks a concept. We report that it was unstable in our runs.",
            "Graph-guided adaptive diagnosis, which uses the validated graph to choose the next "
            "quiz question and to infer knowledge of related concepts.",
            "Root-cause tracing, which reads the option a student chose and ranks which concept "
            "in the prerequisite chain most likely caused the error.",
            "Personalized, explainable paths and impact-ranked human review: one course graph, a "
            "different path per student, with uncertain edges ranked by how many student paths "
            "they would change.",
        ],
        "List Number",
    )
    paper.p(
        "The system is implemented end to end, including a website that takes uploaded course "
        "files."
    )

    paper.h1("II. Related Work")
    paper.h2("A. Prerequisite Relation Learning")
    paper.p(
        "Early work used Wikipedia links and crowdsourced judgments [3]. RefD measures asymmetry "
        "in links between related pages [4]. Others learned from MOOC features [5], university "
        "course dependencies [6] and active learning [7]. PREREQ [8] and LectureBank [9] moved "
        "toward learned representations. More recently, PCPL applies prompt learning [10], LCPRE "
        "uses learning-path information [11], and GKROM optimizes relations globally [12]. Most "
        "of this work measures pairwise accuracy on curated benchmarks. We treat discovery as an "
        "input and focus on what happens after an LLM proposes an edge."
    )
    paper.h2("B. Educational Knowledge Graphs and Paths")
    paper.p(
        "ACE combines machine learning with expert input to reduce the effort of building "
        "prerequisite graphs [13]. InstructKG builds graphs from lecture material and reports "
        "that LLM extraction without instructor-grounded signals yields inaccurate pedagogical "
        "graphs [14], which matches what we observed. Prerequisite information has also been used "
        "to recommend learning objects [15]. Our paths differ per student, and each step keeps "
        "its evidence."
    )
    paper.h2("C. Student Modeling")
    paper.p(
        "Knowledge Space Theory models feasible knowledge states under a prerequisite relation, "
        "so a few questions can place a learner in a state [16]. Our diagnosis uses the same "
        "idea, but the relation is proposed by an LLM and checked automatically instead of being "
        "elicited from experts. Knowledge tracing estimates mastery over time from many "
        "interactions [17], [18]. A new course has no such logs, whereas our approach starts from "
        "course material alone."
    )
    paper.h2("D. Verification of LLM Outputs")
    paper.p(
        "Common countermeasures include grounding in retrieved text [19], sampling and majority "
        "voting [20], and using one model to judge another [21]. We apply these ideas to a "
        "structured output, a graph edge, where some constraints such as acyclicity can be "
        "checked exactly."
    )

    paper.h1("III. Problem Formulation")
    paper.p(
        "A course is a set of documents <i>D</i> split into chunks <i>K</i>, each keeping its "
        "source document and page. Extraction gives a set of concepts <i>C</i>. A concept "
        "<i>A</i> is a <i>hard</i> prerequisite of <i>B</i> if <i>B</i> cannot be understood "
        "without <i>A</i>, and a <i>soft</i> prerequisite if <i>A</i> clearly helps but is not "
        "required. The course graph <i>G</i> = (<i>C</i>, <i>E</i>) is a directed acyclic graph "
        "(DAG) of validated edges, shared by all students. Fig. 1 shows the system."
    )
    paper.p(
        "What differs per student <i>s</i> is a knowledge state <i>m</i><sub>s</sub> ∈ "
        "[0, 1]<sup>|C|</sup>, a mastery value for each concept. A concept counts as mastered "
        "when <i>m</i><sub>s,c</sub> > τ = 0.8. For a target <i>t</i>, the personalized path "
        "is the target and its ancestors minus the mastered concepts, in topological order:"
    )
    anc = msub(mi("Anc", True), mi("G")) + delim(mi("t"))
    mastered = delim(
        mi("c:") + msub(mi("m"), mi("s,c")) + mi(">τ"),
        "{",
        "}",
    )
    equation(
        doc,
        mi("π")
        + delim(mi("s,t"))
        + mi("=")
        + mi("TopSort", True)
        + delim(delim(delim(mi("t"), "{", "}") + mi("∪") + anc) + mi("∖") + mastered),
        1,
    )

    paper.figure(
        HERE / "figures" / "pipeline.png",
        3.0,
        "System overview. The course level runs once per course and the student level runs per "
        "student. Every stage exchanges schema-validated JSON files.",
        "Flow from course files through extraction, discovery, the validation agent and the "
        "validated graph, then to the adaptive quiz, root-cause tracing and the personalized "
        "path.",
    )
    paper.h1("IV. Proposed System")
    paper.h2("A. Extraction")
    paper.p(
        "PDF, PPTX, Markdown, TXT and DOCX files are split into chunks of at most 500 words that "
        "keep their source. An LLM lists the concepts in each chunk, and near-duplicate names are "
        "merged by embedding similarity (all-MiniLM-L6-v2 [22]), with aliases kept. An evidence "
        "filter then keeps a concept only if it appears in a section heading or has enough "
        "mentions or source chunks outside exercise and summary sections. Extraction stops with "
        "an error instead of silently falling back if the LLM or the embedding model is "
        "unavailable, and the method used is recorded in the output."
    )
    paper.h2("B. Dependency Discovery")
    paper.p(
        "Sending every concept pair to an LLM is too expensive, so a pair is kept only if there "
        "is a signal: the concepts share a chunk, one is named in the other’s definition or "
        "source text, or their embeddings are similar. The proposer (qwen2.5:7b-instruct) "
        "receives up to four excerpts and answers one neutral question: <i>A</i> before <i>B</i>, "
        "<i>B</i> before <i>A</i>, or neither, with a strength and a confidence. Which concept is "
        "called <i>A</i> comes from a hash of the pair, so position carries no information about "
        "the true direction (prompt version v3.1)."
    )
    paper.p(
        "Because the answers depend on that position (Section VI-B), course runs ask every pair "
        "in both orders under a rule written down before any full run. The same direction twice "
        "gives a <i>stable</i> edge. A link in one order and “neither” in the other "
        "gives an <i>unstable</i> edge. Opposite directions give a <i>reversed</i> pair, and both "
        "edges go to the validator. No link in either order gives no edge. Benchmark runs keep "
        "the standard protocol and ask each pair once, in the dataset’s own orientation, so "
        "they cannot show this effect."
    )
    paper.h2("C. Validation Agent")
    paper.p(
        "Every proposed edge is treated as a claim. The agent uses a different model "
        "(llama3.1:8b) and its own prompts, because a model that finds an edge plausible once "
        "will tend to do so again. All calls use a fixed seed and are cached, with the model, "
        "prompt version and temperature recorded."
    )
    paper.p(
        "<i>Graph check (no LLM).</i> Each edge is labelled self-loop, duplicate, contradiction "
        "(both directions proposed), cycle, redundant (implied by a longer path) or ok."
    )
    paper.p(
        "<i>Evidence check.</i> The agent gathers the chunks discovery cited plus the top three "
        "retrieved by embedding similarity. The model grades whether the excerpts support "
        "learning <i>A</i> before <i>B</i> as strong, medium, weak or none, and it must quote the "
        "text. A quote is kept only if it appears verbatim in the cited chunk, and a strong or "
        "medium grade with no verifiable quote is capped at weak. Every displayed quote is "
        "therefore traceable to a document and page."
    )
    paper.p(
        "<i>Semantic check.</i> The model grades the edge from concept names and descriptions "
        "only, so it does not share the evidence check’s input. Used alone, it is also our "
        "single-judge baseline."
    )
    paper.p(
        "<i>Necessity test.</i> A question writer creates questions on <i>B</i> without naming "
        "<i>A</i>. A simulated learner answers them with <i>A</i> forbidden. A control run uses "
        "the same prompt with an unrelated concept forbidden instead, which absorbs the penalty "
        "of being told “you never learned X”. A separate grader, blind to the run, "
        "scores both. The necessity gap is the control score minus the without-<i>A</i> score. "
        "Because of the instability reported in Section VI-D, this test is report-only in the current agent: it "
        "has weight 0 and never changes a decision."
    )
    paper.p(
        "<i>Decision rule.</i> Self-loops and duplicates are rejected, and redundant edges are "
        "rejected with the reason “implied by ...”. Contradictory or bidirectional "
        "edges go to human review, and a cycle is never accepted. Otherwise grades map to points "
        "(1, 0.67, 0.33, 0), and the score is the mean over active checks. An edge is accepted if "
        "the score is at least 0.6 and no active check says none. It is rejected if the score is "
        "below 0.35, or if evidence and semantic are both weak or none. Otherwise it goes to "
        "review. These values are a first choice, not yet calibrated."
    )
    paper.h2("D. Impact-Ranked Human Review")
    paper.p(
        "For each edge <i>e</i> sent to review, we compare every simulated student’s path "
        "with and without the edge. Its impact is the share of paths that change,"
    )
    sum_part = (
        '<m:nary><m:naryPr><m:chr m:val="∑"/><m:supHide m:val="1"/></m:naryPr>'
        f"<m:sub>{mi('s∈S')}</m:sub><m:sup/><m:e>"
        + mi("I", True)
        + delim(
            msup(mi("π"), mi("+e"))
            + delim(mi("s,t"))
            + mi("≠")
            + msup(mi("π"), mi("−e"))
            + delim(mi("s,t")),
            "[",
            "]",
        )
        + "</m:e></m:nary>"
    )
    equation(
        doc,
        mi("Impact", True)
        + delim(mi("e"))
        + mi("=")
        + f"<m:f><m:num>{mi('1')}</m:num><m:den>{mi('|S|')}</m:den></m:f>"
        + sum_part,
        2,
    )
    paper.p(
        "and the queue is sorted by impact. Edges that would close a cycle are flagged as "
        "blocking and come first. On the website, a teacher accepts or rejects an edge, and an "
        "edge that would close a cycle is never added.",
        indent=False,
    )
    paper.h2("E. Adaptive Diagnosis and Personalized Path")
    paper.p(
        "Each concept starts at mastery 0.5. The next question targets a concept near the middle "
        "of the uncertain part of the target’s prerequisite chain (mastery between 0.2 and "
        "0.8). A correct answer sets that concept to 0.9 and its ancestors to at least 0.85. A "
        "wrong answer sets it to 0.1 and keeps its prerequisites in question. The latest direct "
        "answer on a concept always overrides inference. A quiz stops at 10 questions per target; "
        "if that limit is reached, concepts that were not asked stay on the path."
    )
    paper.p(
        "Quiz items are generated by an LLM from the course chunks, and each must carry a "
        "word-for-word quote from a cited chunk. Code checks then drop an item if the quote is "
        "absent, if the question names a concept its source does not mention, or if under half of "
        "the answer’s content words appear in the quote. A second model, not told the "
        "answer, judges each option from the excerpt and can veto the item. A topic left with "
        "fewer than two items gets one retry that states why its drafts failed."
    )
    paper.h2("F. Root-Cause Tracing")
    paper.p(
        "Given a wrong answer on concept <i>T</i>, the candidates are <i>T</i> and its ancestors "
        "over accepted edges. An LLM reads the question, the options, the chosen option and this "
        "chain, and ranks the candidates with a one-line explanation. Output is restricted to the "
        "chain. Two baselines also rank the chain: blame the target, and blame the nearest "
        "prerequisite (lowest mastery, then hard before soft, then concept ID)."
    )

    paper.h1("V. Experimental Setup")
    paper.h2("A. Datasets")
    paper.p(
        "Our courses use openly licensed material so the work can be reproduced (Table I): ds101 "
        "uses Open Data Structures [23] and OpenDSA modules [24] for AVL trees, general trees and "
        "recursion, and ml101 uses Dive into Deep Learning [25] and Introduction to Modern "
        "Statistics [26] for logistic regression."
    )
    paper.table(
        "I",
        "Our Course Corpora",
        [
            ["Course", "Files", "Chunks", "Concepts", "Gold rows"],
            ["ds101", 13, 149, "259 (85 after filter)", "9 (pilot)"],
            ["ml101", 10, 78, "pending", "4 (pilot)"],
        ],
        [0.6, 0.45, 0.55, 1.2, 0.7],
        note="Gold rows exclude 7 tied pairs awaiting adjudication. A larger gold set will be "
        "labelled on the real concepts.",
    )
    paper.p(
        "Public benchmarks are AL-CPL [7] and the University Course dataset [6] (Table II). "
        "Neither provides course text, so on these the agent uses only the semantic and graph "
        "checks. Their positives include many pairs implied by other positives, so we score the "
        "transitive closure of our predictions against them; our own gold labels are direct edges "
        "only. University Course contains 99 votes with a label its documentation does not define, "
        "and we drop them. LectureBank [9] is excluded because its repository and paper state no "
        "licence for its annotations."
    )
    paper.table(
        "II",
        "Public Benchmark Statistics",
        [
            ["Graph", "Concepts", "Pos.", "Neg.", "Implied"],
            ["AL-CPL data mining", 120, 292, 534, 180],
            ["AL-CPL geometry", 89, 524, 1157, 414],
            ["AL-CPL physics", 153, 487, 1475, 308],
            ["AL-CPL precalculus", 224, 699, 1361, 454],
            ["University Course", 521, 1007, 1821, 555],
        ],
        [1.2, 0.6, 0.45, 0.45, 0.7],
        note="Implied: positives already implied by a path of other positives.",
    )
    paper.h2("B. Research Questions and Baselines")
    paper.bullets(
        [
            "<b>RQ1:</b> Does the agent improve the precision of LLM-proposed edges, and at what "
            "cost to recall? Compared with a baseline prompt, discovery alone, a single judge, and "
            "a self-consistency judge (three samples at temperature 0.7), plus ablations removing "
            "each check. We also report the human-review rate and LLM calls per edge.",
            "<b>RQ2:</b> Does adaptive diagnosis need fewer questions than asking every concept, "
            "at similar accuracy? Also compared with random order at the same budget.",
            "<b>RQ3:</b> Does LLM tracing beat the two baselines? Measured by top-1 and top-3 "
            "accuracy on a 40-item test set, labelled by a different author from the one who wrote "
            "the prompt.",
            "<b>RQ4:</b> Are personalized paths shorter than generic paths while still covering "
            "real gaps? Measured by path length, gap coverage and order violations.",
        ]
    )
    paper.h2("C. Annotation and Sampling")
    paper.p(
        "Annotators label ordered pairs as hard, soft or none under written guidelines, each in "
        "their own file. We report Cohen’s κ [27] raw and after a mechanical shortcut "
        "rule, which turns a pair into none when that annotator’s own labels already give a "
        "path through another concept. Thresholds will be calibrated on a development split that "
        "is excluded from all reported scores. On benchmarks, each graph is scored on a seeded, "
        "label-stratified sample of 200 pairs, posed in the dataset’s own orientation, with "
        "a nested 100-pair subset for the self-consistency judge."
    )
    paper.h2("D. Simulated Students and Environment")
    paper.p(
        "Students are sampled from a learning frontier so that knowledge follows the graph, with "
        "slip (0.05–0.12) and guess (0.10–0.20) noise. A second condition ignores the "
        "graph, with each concept mastered independently at <i>p</i> = 0.5. Models run locally "
        "through Ollama, using only free tools, on an Apple M2 laptop with 8 GB of memory. Recent "
        "discovery calls averaged 8.4 s with qwen; evidence and semantic calls took medians of "
        "26 s and 8.5 s with llama."
    )

    paper.h1("VI. Preliminary Results")
    paper.p(
        "The scoring harness, baselines, ablation flags and benchmark sampler for RQ1 are "
        "implemented, but no RQ1 run is complete, so we report no precision, recall or F1. RQ3 has "
        "only a development set. The findings below are preliminary, and none is a final "
        "evaluation."
    )
    paper.h2("A. Discovery on a Real Textbook")
    paper.p(
        "All 259 extracted ds101 concepts produced 6,088 candidate pairs out of 33,411, too many "
        "for our hardware. Many concepts were too fine-grained, such as \u201cadd(i, x)\u201d. We "
        "therefore tried a subset of 30 core concepts, which gave 233 candidates out of 435 pairs "
        "and 82 proposed edges."
    )
    paper.p(
        "Those 82 edges were poor. Our key chain, binary tree \u2192 BST \u2192 AVL tree, was "
        "missing, while 19 edges pointed into \u201cheap\u201d and 17 into \u201cgeneral "
        "tree\u201d, and every edge had confidence 0.9. Ollama had truncated the prompt in 200 of "
        "237 calls, which removed the question: only 36 of 233 matched replies named the pair they "
        "were asked about. Direction also came from the order of concepts in the files, and the "
        "reverse direction was never asked. A run with a GPU out-of-memory error during embedding "
        "also kept all 435 pairs, so such runs are now discarded."
    )
    paper.p(
        "Prompt v3 asked one neutral question with limited excerpts and the question last. On the "
        "same candidates it proposed 64 edges, with \u201cbinary tree\u201d now the most common "
        "target, but its answers were lopsided: 59 \u201c<i>B</i> before <i>A</i>\u201d against 5 "
        "\u201c<i>A</i> before <i>B</i>\u201d, while <i>A</i> was always the lower concept ID. "
        "General tree \u2192 binary tree and binary tree \u2192 BST were still not proposed."
    )
    paper.h2("B. Sensitivity to Question Order")
    paper.p(
        "To test that imbalance, we asked 35 pairs from the 85 filtered ds101 concepts in both "
        "orders with v3.1: the 5 positive gold pairs and a seeded sample of 30 other candidates. "
        "Table III gives the outcome. Of the 13 pairs where either order proposed a link, 12 changed "
        "when <i>A</i> and <i>B</i> were swapped. For BST and AVL tree the direction itself "
        "reversed, so the model followed the position rather than the concepts. Across all 70 asks "
        "the answers were 14 \u201c<i>B</i> before <i>A</i>\u201d, 4 \u201c<i>A</i> before "
        "<i>B</i>\u201d and 52 neither; these are paired questions on one course, so we read the "
        "preference as a pattern, not a rate."
    )
    paper.table(
        "III",
        "Result When the Two Concepts Are Swapped",
        [
            ["Result across both orders", "Gold", "Sample", "All"],
            ["Same answer (22 of 23: neither twice)", 2, 21, 23],
            ["Direction reversed", 2, 2, 4],
            ["One order neither, the other a link", 1, 7, 8],
        ],
        [2.0, 0.45, 0.55, 0.5],
        note="Two gold IDs were mapped to the filtered concepts for this test: trees to general "
        "tree, and graphs to graph.",
    )
    paper.p(
        "The hash stops position from lining up with the true direction, but the answers stay "
        "unstable, which motivates the both-order rule. Its reasoning comes from the 30 non-gold "
        "pairs, but the 5 gold pairs were also visible when it was chosen."
    )
    paper.p(
        "To check that the stages work together, we ran the validator on 28 of the 64 v3 edges, "
        "chosen by a written rule that favored tree-related edges and edges that looked likely to "
        "be wrong. It accepted 6, rejected 16 and sent 6 to review, with no prompt truncation. "
        "Because the selection was deliberate, these counts are not a performance measure."
    )
    paper.h2("C. Checks on Example Edges")
    paper.p(
        "We ran the evidence check and semantic prompts once on six example edges (llama3.1:8b, "
        "temperature 0, seed 42). These edges overlap the gold labels, so this shows behavior and "
        "is not an evaluation. Both the evidence check and semantic v2 graded the unrelated edge, "
        "graphs \u2192 AVL tree, as none. Moving from semantic v1 to v2 raised binary tree \u2192 "
        "BST from weak to strong, as intended, but also over-graded the soft edge recursion "
        "\u2192 binary tree as strong. The evidence check graded binary tree \u2192 BST only weak."
    )
    paper.h2("D. Necessity Test Stability")
    paper.p(
        "We expected the gap to follow binary tree \u2192 BST > recursion \u2192 binary tree > "
        "graphs \u2192 AVL \u2248 0. No setting reproduced this order (Fig. 2). Open questions at "
        "<i>n</i> = 3 gave every edge the smallest possible step, so they could not rank. "
        "Multiple-choice runs mostly gave identical control and without-<i>A</i> scores, including "
        "a zero gap for the hard edge. At <i>n</i> = 5 with sampled questions, the unrelated edge "
        "scored above the hard one. One question there named <i>A</i>, which we now prevent. At "
        "temperature 0, seeds repeat the same output, so an SD of 0 reflects repetition, not "
        "stability."
    )
    paper.figure(
        HERE / "figures" / "fig_necessity.png",
        3.4,
        "Necessity gap by setting and edge. Error bars show SD across three seeds. *One seed, "
        "questions written at temperature 0.7.",
        "Grouped coloured bars of the necessity gap for three edges in five settings. No setting "
        "ranks the hard edge above the soft edge and the soft edge above the unrelated edge.",
    )
    paper.p(
        "A plausible explanation is that a small LLM cannot reliably simulate not knowing a "
        "concept, since it answers partly from its own knowledge. We have not tested this directly. "
        "Three edges cannot support a general conclusion, so RQ1 includes a setting that gives the "
        "test weight, to measure its effect on real data."
    )
    paper.h2("E. RQ2 and RQ4: Simulated Students")
    paper.p(
        "We simulated 500 students per condition on a five-concept example graph, target AVL tree "
        "(Fig. 3). When knowledge follows the graph, adaptive diagnosis saved 14.4% of questions at "
        "nearly the accuracy of asking everything, and beat random order at the same budget. When "
        "knowledge ignores the graph, it saved 27.2% of questions but lost about 10 accuracy points, "
        "so its advantage depends on the graph being a good model of the student."
    )
    paper.figure(
        HERE / "figures" / "fig_rq2.png",
        3.4,
        "Diagnosis accuracy by strategy and student condition (RQ2). Each bar states the average "
        "questions asked.",
        "Grouped coloured bars. When knowledge follows the graph, accuracy is 0.866 for adaptive, "
        "0.870 for asking every concept and 0.824 for random. When it ignores the graph, accuracy is "
        "0.775, 0.874 and 0.759.",
    )
    paper.p(
        "Personalized paths averaged 2.35 concepts (follow graph) and 1.77 (ignore graph) against a "
        "generic path of 5, a reduction of 52.9% and 64.6% (RQ4). They do not cover every gap, "
        "because diagnosis makes errors: gap coverage was 0.81 and 0.59, so the shorter path comes "
        "with far lower coverage. Order violations were 0, but that follows from topological "
        "sorting of the same graph, so it says little by itself."
    )
    paper.h2("F. Quiz Item Checks")
    paper.p(
        "We replayed 32 real draft items for 8 ds101 topics through the checks in Section IV-E. Code "
        "checks stopped 20 of them, 12 reached the second model, and 8 were kept. An "
        "author\u2019s reading was mixed: the checks removed clear errors, such as questions naming "
        "a red-black tree with a quote about AVL trees, but also dropped items that read well, and "
        "some weak items survived. These items shaped the checks, so this gives no accuracy figure, "
        "but it suggests automatic checks need a teacher review step."
    )
    paper.h2("G. Root-Cause Tracing (Development Set)")
    paper.p(
        "On a 10-item development set with no mastery information, the LLM tracer tied the "
        "blame-the-target baseline (top-1 0.5, top-3 0.8), and blame-the-nearest reached top-1 0.4, "
        "top-3 0.8. Ten items cannot separate these methods. The tracer is now frozen, and it will "
        "be evaluated once on the 40-item test set, which shares no quiz items with the "
        "development set."
    )
    paper.h2("H. Inter-Annotator Agreement (Pilot)")
    paper.p(
        "Two authors labelled 20 pilot pairs, chosen before the real concept list existed (Fig. 4). "
        "The rule changed four labels of one annotator and none of the other\u2019s, because the "
        "second annotator\u2019s labels had already had the rule applied during labelling, so raw "
        "\u03ba partly reflects that difference. Seven pairs are ties awaiting adjudication."
    )
    paper.figure(
        HERE / "figures" / "fig_kappa.png",
        3.4,
        "Cohen\u2019s \u03ba between two annotators, raw and after the shortcut rule, before any "
        "adjudication.",
        "Coloured bars of kappa: all pairs 0.49 raw and 0.77 after the rule, ds101 0.85 and 1.00, "
        "ml101 0.17 and 0.55.",
    )

    paper.h1("VII. Limitations")
    paper.bullets(
        [
            "<b>Example graph.</b> RQ2 and RQ4 use five concepts, not a real course.",
            "<b>Simulated students share the graph they evaluate.</b> The first condition shows "
            "performance given a correct graph, not that real students behave this way.",
            "<b>One right answer can be a guess.</b> Diagnosis usually asks one question per "
            "concept, so a lucky guess can mark a concept as known.",
            "<b>Small pilot gold.</b> Twenty pairs by two student annotators cannot support strong "
            "conclusions, and only 5 positive edges back ds101.",
            "<b>Benchmarks test only part of the agent.</b> They ask one fixed order, so they cannot "
            "reveal order sensitivity, and they use a different discovery prompt (v2) from our "
            "courses (v3.1). Both come from the same group.",
            "<b>One prompt change on pilot edges.</b> Semantic prompt v2 was changed once after we "
            "saw example edges that overlap the pilot gold, so those pairs must be excluded from "
            "final scores.",
            "<b>Discovery is not yet good enough.</b> The both-order rule exposes order sensitivity "
            "rather than removing it and has not been run at scale, so its effect on edge quality "
            "is unknown. The concept filter lost none of the 4 gold concepts with an exact ID match, "
            "but a 6-concept list is too small to judge it, and it is untested on ml101.",
            "<b>Hardware.</b> Two models do not fit together in 8 GB of memory, which limited how "
            "much we could run.",
        ]
    )

    paper.h1("VIII. Future Work")
    paper.p(
        "The immediate work is to complete the evaluation: run both-order discovery and validation "
        "on the filtered courses, run RQ1 on the benchmarks and full courses, label a larger gold "
        "set of real concepts, calibrate and freeze thresholds, then run RQ3 once and repeat RQ2 and RQ4 on real graphs. A small pre/post study with real students is planned."
    )

    paper.h1("IX. Conclusion")
    paper.p(
        "We built an end-to-end system in which LLM-proposed prerequisites are treated as claims to "
        "check. Validated edges then support an adaptive quiz and a personal learning path. Our "
        "early findings are mixed and useful. Simulating a learner’s missing knowledge was "
        "unstable, a real textbook exposed silent failures in discovery, proposed links depended "
        "heavily on question order, and adaptive diagnosis saves questions mainly when knowledge "
        "follows the graph. Whether the agent improves edge quality remains to be measured, and "
        "that is the next step."
    )

    head = doc.add_heading("Acknowledgment", 1)
    head.paragraph_format.first_line_indent = Inches(0)
    paper.p(
        "The authors thank the Department of Computer Science & Engineering, M S Ramaiah Institute "
        "of Technology. Parts of the software and of this manuscript’s text were drafted with "
        "an AI coding assistant (Anthropic’s Claude, through Claude Code), including the "
        "mechanical application of the shortcut rule to one annotator’s answers. The authors "
        "directed this work and remain responsible for it."
    )

    doc.add_heading("References", 1)
    for number, ref in enumerate(REFERENCES, start=1):
        par = doc.add_paragraph()
        par.paragraph_format.left_indent = Inches(0.25)
        par.paragraph_format.first_line_indent = Inches(-0.25)
        par.paragraph_format.space_after = Pt(0)
        par.paragraph_format.tab_stops.add_tab_stop(Inches(0.25))
        runs(par, f"[{number}]\t{ref}", 8)


REFERENCES = [
    "S. Pan, L. Luo, Y. Wang, C. Chen, J. Wang, and X. Wu, “Unifying large language models "
    "and knowledge graphs: A roadmap,” <i>IEEE Trans. Knowl. Data Eng.</i>, vol. 36, no. 7, "
    "pp. 3580–3599, 2024.",
    "Z. Ji et al., “Survey of hallucination in natural language generation,” <i>ACM "
    "Comput. Surv.</i>, vol. 55, no. 12, pp. 1–38, 2023.",
    "P. P. Talukdar and W. W. Cohen, “Crowdsourced comprehension: Predicting prerequisite "
    "structure in Wikipedia,” in <i>Proc. 7th Workshop Building Educ. Appl. Using NLP</i>, "
    "2012, pp. 307–315.",
    "C. Liang, Z. Wu, W. Huang, and C. L. Giles, “Measuring prerequisite relations among "
    "concepts,” in <i>Proc. EMNLP</i>, 2015, pp. 1668–1674.",
    "L. Pan, C. Li, J. Li, and J. Tang, “Prerequisite relation learning for concepts in "
    "MOOCs,” in <i>Proc. ACL</i>, 2017, pp. 1447–1456.",
    "C. Liang, J. Ye, Z. Wu, B. Pursel, and C. L. Giles, “Recovering concept prerequisite "
    "relations from university course dependencies,” in <i>Proc. AAAI</i>, 2017, pp. "
    "4786–4791.",
    "C. Liang, J. Ye, S. Wang, B. Pursel, and C. L. Giles, “Investigating active learning for "
    "concept prerequisite learning,” in <i>Proc. AAAI (EAAI)</i>, 2018, pp. 7913–7919.",
    "S. Roy, M. Madhyastha, S. Lawrence, and V. Rajan, “Inferring concept prerequisite "
    "relations from online educational resources,” in <i>Proc. AAAI</i>, vol. 33, 2019, pp. "
    "9589–9594.",
    "I. Li, A. R. Fabbri, R. R. Tung, and D. R. Radev, “What should I learn first: Introducing "
    "LectureBank for NLP education and prerequisite chain learning,” in <i>Proc. AAAI</i>, "
    "vol. 33, 2019, pp. 6674–6681.",
    "F. Du, W. Hu, C. Qin, and Z. Xiao, “A prompt-based approach for discovering prerequisite "
    "relations among concepts,” in <i>Proc. ITEI 2023</i>, Zhengzhou, China, EAI, 2024, doi: "
    "10.4108/eai.24-11-2023.2343577.",
    "J. Sun, Y. He, Y. Xu, J. Sun, and G. Sun, “A learning-path based supervised method for "
    "concept prerequisite relations extraction in educational data,” in <i>Proc. CIKM</i>, "
    "2024, pp. 2168–2177.",
    "M. Zhang, J. Wang, K. Xiao, S. Wang, Y. Zhang, H. Chen, and Z. Li, “Learning concept "
    "prerequisite relation via global knowledge relation optimization,” in <i>Proc. AAAI</i>, "
    "vol. 39, no. 2, 2025, pp. 1638–1646.",
    "M. C. Aytekin and Y. Saygın, “ACE: AI-assisted construction of educational knowledge "
    "graphs with prerequisite relations,” <i>J. Educ. Data Mining</i>, vol. 16, no. 2, pp. "
    "85–114, 2024.",
    "A. AlRabah, P. Kargupta, J. Han, and A. Alawini, “Instructor-aligned knowledge graphs for "
    "personalized learning,” arXiv:2602.17111, 2026.",
    "A. Chanaa and N. El Faddouli, “Prerequisites-based course recommendation: Recommending "
    "learning objects using concept prerequisites and metadata matching,” <i>Smart Learn. "
    "Environ.</i>, vol. 11, art. 16, 2024.",
    "J.-P. Doignon and J.-C. Falmagne, “Spaces for the assessment of knowledge,” <i>Int. "
    "J. Man-Machine Studies</i>, vol. 23, no. 2, pp. 175–196, 1985.",
    "A. T. Corbett and J. R. Anderson, “Knowledge tracing: Modeling the acquisition of "
    "procedural knowledge,” <i>User Model. User-Adapt. Interact.</i>, vol. 4, no. 4, pp. "
    "253–278, 1994.",
    "C. Piech et al., “Deep knowledge tracing,” in <i>Adv. Neural Inf. Process. Syst.</i>, "
    "vol. 28, 2015, pp. 505–513.",
    "P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP tasks,” "
    "in <i>Adv. Neural Inf. Process. Syst.</i>, vol. 33, 2020, pp. 9459–9474.",
    "X. Wang et al., “Self-consistency improves chain of thought reasoning in language "
    "models,” in <i>Proc. ICLR</i>, 2023.",
    "L. Zheng et al., “Judging LLM-as-a-judge with MT-Bench and Chatbot Arena,” in <i>Adv. "
    "Neural Inf. Process. Syst. Datasets and Benchmarks Track</i>, 2023.",
    "N. Reimers and I. Gurevych, “Sentence-BERT: Sentence embeddings using Siamese "
    "BERT-networks,” in <i>Proc. EMNLP-IJCNLP</i>, 2019, pp. 3982–3992.",
    "P. Morin, <i>Open Data Structures (in pseudocode)</i>, Edition 0.1Gβ. [Online]. Available: "
    "https://opendatastructures.org/",
    "OpenDSA Project, “OpenDSA modules,” GitHub repository, commit f900a7a. [Online]. Available: "
    "https://github.com/OpenDSA/OpenDSA",
    "A. Zhang, Z. C. Lipton, M. Li, and A. J. Smola, <i>Dive into Deep Learning</i>, release 1.0.3. "
    "[Online]. Available: https://d2l.ai/",
    "M. Çetinkaya-Rundel and J. Hardin, <i>Introduction to Modern Statistics</i>, 2nd ed., "
    "OpenIntro, 2024. [Online]. Available: https://openintrostat.github.io/ims/",
    "J. Cohen, “A coefficient of agreement for nominal scales,” <i>Educ. Psychol. Meas.</i>, "
    "vol. 20, no. 1, pp. 37–46, 1960.",
]


def main():
    paper = Paper()
    front_matter(paper)
    body(paper)
    # A final continuous section balances the two columns on the last page.
    final = paper.doc.add_section(WD_SECTION.CONTINUOUS)
    two_columns(final)
    paper.doc.core_properties.title = (
        "Verify, Diagnose, Adapt: Agent-Validated Prerequisite Graphs for Student-Adaptive "
        "Learning Paths"
    )
    paper.doc.core_properties.author = "Shreeya Kiran Khairnar"
    paper.doc.core_properties.comments = ""
    paper.doc.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
