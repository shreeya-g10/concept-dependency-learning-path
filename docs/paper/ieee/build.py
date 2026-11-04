"""Build paper.pdf (reportlab) and paper.tex (IEEEtran, for Overleaf) from content.py."""

# ruff: noqa: E501

import re
from pathlib import Path

from content import ABSTRACT, ACK, AFFILIATION, AUTHORS, BODY, INDEX_TERMS, REFS, STATUS, TITLE
from reportlab.lib.colors import HexColor, black
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).parent
FONTS = Path("/System/Library/Fonts/Supplemental")
for name, file in [
    ("T", "Times New Roman"),
    ("T-B", "Times New Roman Bold"),
    ("T-I", "Times New Roman Italic"),
    ("T-BI", "Times New Roman Bold Italic"),
]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / f"{file}.ttf")))
pdfmetrics.registerFontFamily("T", normal="T", bold="T-B", italic="T-I", boldItalic="T-BI")

# Citation numbering, in first-cited order.
order = []


def _collect(text):
    for key in re.findall(r"\[@(\w+)\]", text):
        if key not in order:
            order.append(key)


for block in BODY:
    if block[0] in ("p",):
        _collect(block[1])
    elif block[0] in ("list", "num"):
        for item in block[1]:
            _collect(item)
assert set(order) <= set(REFS), set(order) - set(REFS)
num = {k: i + 1 for i, k in enumerate(order)}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
LETTER = "ABCDEFGHIJ"


def cite(text):
    return re.sub(r"\[@(\w+)\]", lambda m: f"[{num[m.group(1)]}]", text)


# ---------------------------------------------------------------- PDF
def S(name, **kw):
    base = dict(fontName="T", fontSize=9.6, leading=11.3, alignment=TA_JUSTIFY, textColor=black)
    base.update(kw)
    return ParagraphStyle(name, **base)


body = S("body", firstLineIndent=10, spaceAfter=2)
h1 = S("h1", fontSize=9.6, alignment=TA_CENTER, spaceBefore=9, spaceAfter=4, keepWithNext=1)
h2 = S("h2", fontName="T-I", alignment=TA_LEFT, spaceBefore=6, spaceAfter=3, keepWithNext=1)
item = S(
    "item", leftIndent=13, bulletIndent=2, spaceAfter=2, bulletFontName="T", bulletFontSize=9.6
)
cap = S("cap", fontSize=8, leading=9.4, alignment=TA_CENTER, spaceBefore=6, spaceAfter=3)
figcap = S("figcap", fontSize=8, leading=9.4, spaceBefore=3, spaceAfter=7)
note = S("note", fontSize=7.4, leading=8.8, spaceBefore=2, spaceAfter=7)
cell = S("cell", fontSize=8, leading=9.3, alignment=TA_LEFT)
ref = S(
    "ref",
    fontSize=8,
    leading=9.4,
    leftIndent=15,
    bulletIndent=0,
    spaceAfter=1.5,
    bulletFontName="T",
    bulletFontSize=8,
)
abst = S("abst", fontName="T-B", fontSize=8.6, leading=10.1, spaceAfter=4)

W, H = A4
LM, TM, BM, GAP = 0.62 * inch, 0.72 * inch, 0.8 * inch, 0.2 * inch
COL = (W - 2 * LM - GAP) / 2
HEAD_H = 2.0 * inch


def footer(c, doc):
    c.setFont("T-I", 7.5)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(
        W / 2, 0.45 * inch, "Work-in-progress draft: results marked pending have not been obtained."
    )


def build_pdf():
    doc = BaseDocTemplate(
        str(HERE / "paper.pdf"), pagesize=A4, title=TITLE, author=", ".join(a for a, _ in AUTHORS)
    )

    def cols(y0, h):
        return [Frame(LM, y0, COL, h, 0, 0, 0, 0), Frame(LM + COL + GAP, y0, COL, h, 0, 0, 0, 0)]

    first = [Frame(LM, H - TM - HEAD_H, W - 2 * LM, HEAD_H, 0, 0, 0, 0)] + cols(
        BM, H - TM - HEAD_H - BM - 8
    )
    doc.addPageTemplates(
        [
            PageTemplate("first", first, onPage=footer),
            PageTemplate("rest", cols(BM, H - TM - BM), onPage=footer),
        ]
    )
    s = [NextPageTemplate("rest")]
    s.append(Paragraph(TITLE, S("t", fontSize=20, leading=23, alignment=TA_CENTER, spaceAfter=9)))
    cw = (W - 2 * LM) / len(AUTHORS)
    a = S("a", fontSize=8.6, leading=10, alignment=TA_CENTER)
    ai = S("ai", fontName="T-I", fontSize=7.7, leading=9, alignment=TA_CENTER)
    row = []
    for name, mail in AUTHORS:
        cellv = [Paragraph(name, a)] + [Paragraph(x, ai) for x in AFFILIATION]
        if mail:
            cellv.append(Paragraph(mail.replace("@", "<br/>@"), ai))
        row.append(cellv)
    t = Table([row], colWidths=[cw] * len(AUTHORS))
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    s.append(t)
    s.append(FrameBreak())
    s.append(
        Paragraph(
            f"<i>{STATUS}</i>",
            S(
                "st",
                fontSize=8.2,
                leading=9.8,
                spaceAfter=5,
                borderColor=black,
                borderWidth=0.5,
                borderPadding=3,
            ),
        )
    )
    s.append(Spacer(1, 3))
    s.append(Paragraph("<i>Abstract</i>—" + ABSTRACT, abst))
    s.append(Paragraph("<i>Index Terms</i>—" + INDEX_TERMS, abst))

    secs, subs, tabs, figs = 0, 0, 0, 1
    for b in BODY:
        k = b[0]
        if k == "h1":
            secs += 1
            subs = 0
            s.append(Paragraph(f"{ROMAN[secs - 1]}. {b[1].upper()}", h1))
        elif k == "h2":
            subs += 1
            s.append(Paragraph(f"{LETTER[subs - 1]}. {b[1]}", h2))
        elif k == "p":
            s.append(Paragraph(cite(b[1]), body))
        elif k == "list":
            for x in b[1]:
                s.append(Paragraph(cite(x), item, bulletText="•"))
        elif k == "num":
            for i, x in enumerate(b[1], 1):
                s.append(Paragraph(cite(x), item, bulletText=f"{i})"))
        elif k == "table":
            tabs += 1
            _, title, widths, rows, nt = b
            data = [
                [Paragraph(f"<b>{c}</b>" if r == 0 else c, cell) for c in row]
                for r, row in enumerate(rows)
            ]
            tb = Table(data, colWidths=[f * COL for f in widths], repeatRows=1)
            tb.setStyle(
                TableStyle(
                    [
                        ("LINEABOVE", (0, 0), (-1, 0), 0.7, black),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.4, black),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.7, black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
                    ]
                )
            )
            group = [Paragraph(f"TABLE {ROMAN[tabs - 1]}<br/>{title.upper()}", cap), tb]
            group.append(Paragraph(nt, note) if nt else Spacer(1, 7))
            s.append(KeepTogether(group))
        elif k == "fig":
            _, f, c, frac = b
            path = HERE / "figures" / f
            iw, ih = ImageReader(str(path)).getSize()
            w = COL * frac
            s.append(
                KeepTogether(
                    [
                        Spacer(1, 4),
                        Image(str(path), width=w, height=w * ih / iw),
                        Paragraph(f"Fig. {figs}. {c}", figcap),
                    ]
                )
            )
            figs += 1

    s.append(Paragraph("ACKNOWLEDGMENT", h1))
    s.append(Paragraph(ACK, body))
    s.append(Paragraph("REFERENCES", h1))
    for k in order:
        s.append(Paragraph(REFS[k], ref, bulletText=f"[{num[k]}]"))
    doc.build(s)


# ---------------------------------------------------------------- LaTeX
def tex_escape(t):
    t = t.replace("\\", r"\textbackslash{}")
    for a, b in [
        ("&", r"\&"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("#", r"\#"),
        ("$", r"\$"),
        ("→", r"$\rightarrow$"),
        ("κ", r"$\kappa$"),
        ("±", r"$\pm$"),
        ("≈", r"$\approx$"),
        ("β", r"$\beta$"),
        ("ı", r"{\i}"),
        ("Ç", r"\c{C}"),
        ("…", r"\ldots{}"),
        ("“", "``"),
        ("”", "''"),
        ("’", "'"),
        ("–", "--"),
        ("—", "---"),
    ]:
        t = t.replace(a, b)
    return t


def tex(t):
    t = re.sub(r"\[@(\w+)\]", lambda m: f"@@CITE{m.group(1)}@@", t)
    t = (
        t.replace("<b>", "@@B@@")
        .replace("</b>", "@@E@@")
        .replace("<i>", "@@I@@")
        .replace("</i>", "@@E@@")
    )
    t = tex_escape(t)
    t = t.replace("@@B@@", r"\textbf{").replace("@@I@@", r"\emph{").replace("@@E@@", "}")
    return re.sub(r"@@CITE(\w+)@@", lambda m: r"\cite{" + m.group(1) + "}", t)


def build_tex():
    o = [
        r"\documentclass[conference]{IEEEtran}",
        r"\usepackage{graphicx,booktabs,array}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{url}",
        r"\graphicspath{{figures/}}",
        r"\begin{document}",
        r"\title{" + tex(TITLE) + "}",
    ]
    blocks = []
    for name, mail in AUTHORS:
        lines = [
            r"\IEEEauthorblockN{" + name + "}",
            r"\IEEEauthorblockA{"
            + r" \\ ".join(tex(x) for x in AFFILIATION)
            + ((r" \\ " + tex(mail)) if mail else "")
            + "}",
        ]
        blocks.append("\n".join(lines))
    o.append(r"\author{" + "\n\\and\n".join(blocks) + "}")
    o += [
        r"\maketitle",
        r"\noindent\fbox{\parbox{0.95\columnwidth}{\footnotesize\emph{" + tex(STATUS) + "}}}",
        r"\begin{abstract}",
        tex(ABSTRACT),
        r"\end{abstract}",
        r"\begin{IEEEkeywords}",
        tex(INDEX_TERMS),
        r"\end{IEEEkeywords}",
    ]
    for b in BODY:
        k = b[0]
        if k == "h1":
            o.append(r"\section{" + tex(b[1]) + "}")
        elif k == "h2":
            o.append(r"\subsection{" + tex(b[1]) + "}")
        elif k == "p":
            o.append(tex(b[1]) + "\n")
        elif k in ("list", "num"):
            env = "itemize" if k == "list" else "enumerate"
            o.append(r"\begin{" + env + "}")
            o += [r"\item " + tex(x) for x in b[1]]
            o.append(r"\end{" + env + "}")
        elif k == "table":
            _, title, widths, rows, nt = b
            spec = "".join(r"p{" + f"{f * 0.92:.3f}" + r"\columnwidth}" for f in widths)
            o += [
                r"\begin{table}[!t]",
                r"\caption{" + tex(title) + "}",
                r"\centering\footnotesize",
                r"\begin{tabular}{@{}" + spec + r"@{}}",
                r"\toprule",
            ]
            for r, row in enumerate(rows):
                vals = [(r"\textbf{" + tex(c) + "}") if r == 0 else tex(c) for c in row]
                o.append(" & ".join(vals) + r" \\" + (r" \midrule" if r == 0 else ""))
            o += [r"\bottomrule", r"\end{tabular}"]
            if nt:
                o.append(r"\\[2pt]\parbox{0.95\columnwidth}{\scriptsize " + tex(nt) + "}")
            o.append(r"\end{table}")
        elif k == "fig":
            _, f, c, _frac = b
            o += [
                r"\begin{figure}[!t]",
                r"\centering",
                r"\includegraphics[width=\columnwidth]{" + f + "}",
                r"\caption{" + tex(c) + "}",
                r"\end{figure}",
            ]
    o += [r"\section*{Acknowledgment}", tex(ACK), r"\begin{thebibliography}{99}"]
    o += [
        r"\bibitem{"
        + k
        + "} "
        + tex(REFS[k])
        .replace("https://opendatastructures.org/", r"\url{https://opendatastructures.org/}")
        .replace("https://d2l.ai/", r"\url{https://d2l.ai/}")
        for k in order
    ]
    o += [r"\end{thebibliography}", r"\end{document}"]
    (HERE / "paper.tex").write_text("\n".join(o), encoding="utf-8")


if __name__ == "__main__":
    build_pdf()
    build_tex()
    print("built", len(order), "references")
