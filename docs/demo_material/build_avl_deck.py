"""Builds avl_tree_course.pptx, a demo upload for the website. Run with the project venv.

Slide text sits in the title and body placeholders, which cdlp/extraction/parse.py reads.
Diagrams are grouped shapes, which it skips, so node labels never become concepts. The first
body line of every slide is a full sentence, or the parser would use it as the heading.

Written to make prerequisites clear, so it is demo material only: never use it as evaluation
data, and don't put it in data/raw/ds101/.
"""

# ruff: noqa: E501

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import MSO_THEME_COLOR as T
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

OUT = Path(__file__).with_name("avl_tree_course.pptx")
THEME = {
    "dk1": "1E1B3A", "lt1": "FFFFFF", "dk2": "2D2A6E", "lt2": "EDEAFB",
    "accent1": "4B3F8F", "accent2": "147D60", "accent3": "C2410C",
    "accent4": "A79FE0", "accent5": "5F5C7E", "accent6": "F2B705",
    "hlink": "4B3F8F", "folHlink": "5F5C7E",
}  # fmt: skip
INK, WHITE, NAVY, TINT = T.TEXT_1, T.BACKGROUND_1, T.TEXT_2, T.BACKGROUND_2
PURPLE, GREEN, RED, SOFT, MUTED = T.ACCENT_1, T.ACCENT_2, T.ACCENT_3, T.ACCENT_4, T.ACCENT_5
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def apply_theme(prs) -> None:
    part = prs.slide_master.part.part_related_by(RT.THEME)
    xml = part.blob.decode()
    for name, value in THEME.items():
        xml = re.sub(
            rf"(<a:{name}>).*?(</a:{name}>)", rf'\g<1><a:srgbClr val="{value}"/>\g<2>', xml,
            flags=re.S,
        )  # fmt: skip
    xml = re.sub(r'(<a:majorFont><a:latin typeface=")[^"]*', r"\g<1>Georgia", xml)
    xml = re.sub(r'(<a:minorFont><a:latin typeface=")[^"]*', r"\g<1>Arial", xml)
    xml = re.sub(r'(<a:theme [^>]*name=")[^"]*', r"\g<1>Road to AVL Trees", xml)
    part._blob = xml.encode()


def style_level(level, size: int, color: str, *, bold=False, after=0, bullet=None) -> None:
    for child in list(level):
        level.remove(child)
    level.set("algn", "l")
    if bullet is None:
        level.set("marL", "0")
        level.set("indent", "0")
    else:
        level.set("marL", "285750")
        level.set("indent", "-285750")
    before = etree.SubElement(level, f"{{{A}}}spcBef")
    etree.SubElement(before, f"{{{A}}}spcPts").set("val", "0")
    space = etree.SubElement(level, f"{{{A}}}spcAft")
    etree.SubElement(space, f"{{{A}}}spcPts").set("val", str(after * 100))
    if bullet is None:
        etree.SubElement(level, f"{{{A}}}buNone")
    else:
        etree.SubElement(level, f"{{{A}}}buChar").set("char", bullet)
    rpr = etree.SubElement(level, f"{{{A}}}defRPr")
    rpr.set("sz", str(size * 100))
    rpr.set("b", "1" if bold else "0")
    fill = etree.SubElement(rpr, f"{{{A}}}solidFill")
    etree.SubElement(fill, f"{{{A}}}schemeClr").set("val", color)
    font = "+mj-lt" if bold and size >= 30 else "+mn-lt"
    etree.SubElement(rpr, f"{{{A}}}latin").set("typeface", font)


def place(shape, x, y, w, h) -> None:
    shape.left, shape.top, shape.width, shape.height = Inches(x), Inches(y), Inches(w), Inches(h)


def setup() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    apply_theme(prs)
    layouts = prs.slide_layouts
    for layout in list(layouts)[2:]:
        layouts.remove(layout)
    master = prs.slide_master
    styles = master._element.find(qn("p:txStyles"))
    style_level(styles.find(qn("p:titleStyle")).find(qn("a:lvl1pPr")), 36, "tx2", bold=True)
    style_level(
        styles.find(qn("p:bodyStyle")).find(qn("a:lvl1pPr")), 20, "tx1", after=14, bullet="•"
    )
    for holder in (master, *layouts):
        for ph in list(holder.placeholders):
            kind = ph.placeholder_format.type
            if kind is not None and str(kind).split(" ")[0] in ("DATE", "FOOTER", "SLIDE_NUMBER"):
                ph._element.getparent().remove(ph._element)
    for holder in (master, layouts[1]):
        for ph in holder.placeholders:
            if ph.placeholder_format.idx == 0:
                place(ph, 0.6, 0.4, 12.13, 0.9)
                ph.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            else:
                place(ph, 0.6, 1.55, 6.0, 5.1)
    # Content layout: the slide number lives here, so the parser never reads it as slide text.
    number = etree.fromstring(
        f"""<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="{A}">
          <p:nvSpPr><p:cNvPr id="90" name="Slide number"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="{Inches(11.73)}" y="{Inches(6.9)}"/>
            <a:ext cx="{Inches(1.0)}" cy="{Inches(0.35)}"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
          <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:pPr algn="r"/>
            <a:fld id="{{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}}" type="slidenum">
              <a:rPr lang="en-US" sz="1200"><a:solidFill><a:schemeClr val="accent5"/></a:solidFill></a:rPr>
              <a:t>‹#›</a:t></a:fld></a:p></p:txBody></p:sp>"""
    )
    layouts[1].shapes._spTree.append(number)
    # Dark title layout, also used for the closing slide.
    cover = layouts[0]
    cover.background.fill.solid()
    cover.background.fill.fore_color.theme_color = NAVY
    for ph in cover.placeholders:
        body = ph._element.find(qn("p:txBody"))
        lst = body.find(qn("a:lstStyle"))
        level = etree.SubElement(lst, f"{{{A}}}lvl1pPr")
        if ph.placeholder_format.idx == 0:
            place(ph, 0.8, 2.0, 8.2, 1.9)
            ph.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
            style_level(level, 48, "bg1", bold=True)
        else:
            place(ph, 0.8, 4.1, 7.6, 2.4)
            style_level(level, 20, "bg2", after=10)
    return prs


class Diagram:
    """Native shapes inside one group: editable in PowerPoint and skipped by the parser."""

    def __init__(self, slide, alt: str):
        self.group = slide.shapes.add_group_shape()
        self.group.name = "Diagram"
        self.group._element.find(qn("p:nvGrpSpPr")).find(qn("p:cNvPr")).set("descr", alt)
        self.shapes = self.group.shapes

    def box(self, x, y, w, h, text="", fill=TINT, color=INK, size=14, bold=False,
            shape=MSO_SHAPE.ROUNDED_RECTANGLE, align=PP_ALIGN.CENTER, line=None):  # fmt: skip
        item = self.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            item.adjustments[0] = min(0.08 / min(w, h), 0.5)
        if fill is None:
            item.fill.background()
        else:
            item.fill.solid()
            item.fill.fore_color.theme_color = fill
        if line is None:
            item.line.fill.background()
        else:
            item.line.color.theme_color = line
            item.line.width = Pt(1.5)
        item.shadow.inherit = False
        frame = item.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        frame.margin_left = frame.margin_right = Inches(0.08)
        frame.margin_top = frame.margin_bottom = Inches(0.03)
        for i, line_text in enumerate(str(text).split("\n")):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            para.alignment = align
            run = para.add_run()
            run.text = line_text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.theme_color = color
        return item

    def label(self, x, y, w, h, text, size=14, color=INK, bold=False, align=PP_ALIGN.CENTER):
        return self.box(x, y, w, h, text, fill=None, color=color, size=size, bold=bold, align=align)

    def line(self, x1, y1, x2, y2, color=MUTED, arrow=False, width=1.75):
        item = self.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
        )
        item.line.color.theme_color = color
        item.line.width = Pt(width)
        if arrow:
            ln = item.line._get_or_add_ln()
            etree.SubElement(ln, f"{{{A}}}tailEnd").set("type", "triangle")
        return item

    def tree(self, spec, x, y, w, h, colors=None, r=0.27, size=14, notes=None):
        """Draw (label, left, right) with x from an in-order walk, so a BST reads left to right."""
        colors, notes = colors or {}, notes or {}
        order, spots = [], {}

        def walk(node, depth):
            if not node:
                return
            walk(node[1] if len(node) > 1 else None, depth + 1)
            order.append(node[0])
            spots[node[0]] = depth
            walk(node[2] if len(node) > 2 else None, depth + 1)

        walk(spec, 0)
        depth = max(spots.values())
        dx = (w - 2 * r) / max(len(order) - 1, 1)
        dy = (h - 2 * r) / max(depth, 1)
        at = {
            name: (x + r + i * dx if len(order) > 1 else x + w / 2, y + r + spots[name] * dy)
            for i, name in enumerate(order)
        }

        def edges(node):
            for child in node[1:]:
                if child:
                    self.line(*at[node[0]], *at[child[0]])
                    edges(child)

        edges(spec)
        for name, (cx, cy) in at.items():
            fill = colors.get(name, PURPLE)
            text = WHITE if fill in (PURPLE, GREEN, RED, NAVY) else INK
            kind = MSO_SHAPE.ROUNDED_RECTANGLE if str(name).startswith("T") else MSO_SHAPE.OVAL
            self.box(cx - r, cy - r, 2 * r, 2 * r, str(name), fill, text, size, True, kind)
            if name in notes:
                self.label(cx + r, cy - 0.2, 1.1, 0.4, notes[name], 13, MUTED, align=PP_ALIGN.LEFT)
        return at

    def cells(self, values, x, y, w, h=0.6, colors=None, size=15, index=False):
        colors = colors or {}
        each = w / len(values)
        for i, value in enumerate(values):
            fill = colors.get(i, TINT)
            text = WHITE if fill in (PURPLE, GREEN, RED, NAVY) else INK
            self.box(x + i * each + 0.03, y, each - 0.06, h, value, fill, text, size, True)
            if index:
                self.label(x + i * each, y + h, each, 0.32, i, 12, MUTED)

    def steps(self, items, x, y, w, h=0.82, gap=0.17, fill=TINT, size=15):
        """A numbered column of cards, each a circle with its number and a short phrase."""
        for i, text in enumerate(items):
            top = y + i * (h + gap)
            self.box(x, top, w, h, text, fill, INK, size, align=PP_ALIGN.LEFT).text_frame.margin_left = Inches(0.72)  # fmt: skip
            self.box(x + 0.14, top + h / 2 - 0.23, 0.46, 0.46, i + 1, PURPLE, WHITE, 14, True, MSO_SHAPE.OVAL)  # fmt: skip

    def part(self, text):
        self.label(0.6, 6.9, 7.0, 0.35, text, 12, MUTED, align=PP_ALIGN.LEFT)


class Deck:
    def __init__(self):
        self.prs = setup()
        self.part_name = ""

    def cover(self, title, lines):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[0])
        slide.shapes.title.text = title
        body = slide.placeholders[1].text_frame
        for i, line in enumerate(lines):
            (body.paragraphs[0] if i == 0 else body.add_paragraph()).text = line
        return Diagram(slide, "A small balanced tree of circles, the deck's motif.")

    def add(self, title, lines, *, width=6.0, left=0.6, top=1.55, height=None, alt=""):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[1])
        slide.shapes.title.text = title
        holder = slide.placeholders[1]
        place(holder, left, top, width, height or 6.65 - top)
        frame = holder.text_frame
        for i, line in enumerate(lines):
            assert line.endswith("."), line
            (frame.paragraphs[0] if i == 0 else frame.add_paragraph()).text = line
        art = Diagram(slide, alt)
        art.part(self.part_name)
        return art


deck = Deck()

# ---- cover and goal ----------------------------------------------------------------------
art = deck.cover(
    "From Trees to AVL Trees",
    ["A step-by-step course in data structures.", "Our goal is the AVL Tree, a tree that keeps itself balanced."],
)  # fmt: skip
art.tree(("d", ("b", ("a",), ("c",)), ("f", ("e",), ("g",))), 9.1, 2.2, 3.5, 3.0,
         {k: SOFT for k in "acegbf"} | {"d": GREEN}, size=14)  # fmt: skip

deck.part_name = "Our goal"
art = deck.add(
    "Where We Are Heading",
    [
        "An AVL Tree stores sorted data and keeps itself balanced after every change.",
        "Search, insertion and deletion in an AVL Tree all take O(log n) time, even in the worst case.",
        "With one million keys, the height of an AVL Tree stays at about 29 or less.",
        "This course builds up to the AVL Tree one idea at a time.",
    ],
    alt="A balanced tree with seven keys, showing that every key is close to the root.",
)
art.tree((40, (20, (10,), (30,)), (60, (50,), (70,))), 7.3, 1.8, 5.2, 3.3, {40: GREEN})
art.box(7.6, 5.5, 4.6, 0.85, "7 keys, only 3 levels: any key is found quickly", TINT, INK, 15, True)

# ---- part 1: foundations ------------------------------------------------------------------
deck.part_name = "Part 1: Foundations"
art = deck.add(
    "Time Complexity and Big-O",
    [
        "Time Complexity describes how the running time of an algorithm grows with the input size n.",
        "Big-O notation keeps only the fastest-growing term and ignores constant factors.",
        "We use Big-O to compare data structures without running them on a real computer.",
    ],
    alt="Bars comparing how many steps O(log n), O(n), O(n log n) and O(n squared) take.",
)
art.label(7.2, 1.6, 5.5, 0.45, "Steps needed when n = 1,024", 16, NAVY, True)
for i, (name, steps, bar, color) in enumerate(
    [("O(log n)", "10", 0.25, GREEN), ("O(n)", "1,024", 1.2, PURPLE),
     ("O(n log n)", "10,240", 2.0, SOFT), ("O(n²)", "1,048,576", 2.7, RED)]
):  # fmt: skip
    y = 2.25 + i * 1.02
    art.label(7.2, y, 1.3, 0.7, name, 15, INK, True, PP_ALIGN.LEFT)
    art.box(8.5, y + 0.08, bar, 0.54, "", color)
    art.label(8.55 + bar, y, 1.4, 0.7, steps, 14, INK, False, PP_ALIGN.LEFT)

art = deck.add(
    "Why Logarithmic Time Matters",
    [
        "An algorithm runs in O(log n) time when each step cuts the remaining work in half.",
        "Doubling the input of an O(log n) algorithm adds only one more step.",
        "Every efficient tree operation in this course relies on this halving idea.",
    ],
    alt="A row of shrinking bars: 16, 8, 4, 2, 1, halving at each step.",
)
for i, n in enumerate([16, 8, 4, 2, 1]):
    width = 5.2 * n / 16
    art.box(
        7.3, 1.75 + i * 0.92, max(width, 0.6), 0.66, n, PURPLE if n > 1 else GREEN, WHITE, 16, True
    )
art.label(9.6, 5.3, 3.1, 0.9, "4 halvings for 16 items", 16, NAVY, True, PP_ALIGN.LEFT)

art = deck.add(
    "Arrays",
    [
        "An Array stores elements side by side in memory, so each one has a numbered index.",
        "Reading any element by its index takes O(1) time.",
        "Inserting at the front takes O(n) time, because every other element must shift.",
    ],
    alt="An array of six cells with indexes 0 to 5.",
)
art.cells([12, 25, 31, 47, 58, 76], 7.1, 2.0, 5.6, index=True, colors={3: GREEN})
art.box(7.1, 3.35, 5.6, 0.85, "a[3] is found right away: 47", TINT, INK, 16, True)
art.box(7.1, 4.45, 5.6, 0.85, "Insert at the front: 6 elements move", TINT, RED, 16, True)

art = deck.add(
    "Linked Lists",
    [
        "A Linked List stores each element in a node that holds a value and a pointer to the next node.",
        "Inserting at the head takes O(1) time, because only one pointer changes.",
        "Reaching the k-th element takes O(k) time, because we must follow the pointers one by one.",
        "Tree nodes reuse this idea of nodes connected by pointers.",
    ],
    alt="Three nodes connected left to right by arrows, ending in null.",
)
for i, value in enumerate([7, 19, 33]):
    x = 7.1 + i * 1.75
    art.box(x, 2.8, 1.15, 0.8, value, PURPLE, WHITE, 18, True)
    art.line(x + 1.15, 3.2, x + 1.75, 3.2, arrow=True)
art.label(12.0, 2.95, 0.8, 0.5, "null", 14, MUTED)
art.label(7.1, 2.25, 1.15, 0.45, "head", 14, GREEN, True)

art = deck.add(
    "Queues",
    [
        "A Queue is a first-in, first-out collection: items leave in the order they arrived.",
        "New items join at the tail, and items are removed from the head.",
        "Both operations take O(1) time with a Linked List or a circular array.",
    ],
    alt="A queue of four cells, with an arrow in at the tail and out at the head.",
)
art.cells(["A", "B", "C", "D"], 8.3, 3.0, 3.2, 0.8, colors={0: GREEN}, size=18)
art.line(8.25, 3.4, 7.2, 3.4, arrow=True)
art.line(12.6, 3.4, 11.55, 3.4, arrow=True)
art.label(7.0, 3.6, 1.3, 0.5, "out (head)", 13, GREEN, True)
art.label(11.5, 3.6, 1.3, 0.5, "in (tail)", 13, MUTED, True)

art = deck.add(
    "Binary Search",
    [
        "Before this topic, you should be comfortable with Arrays and Time Complexity.",
        "Binary Search finds a key in a sorted Array by checking the middle element.",
        "If the key is smaller it continues on the left half, otherwise on the right half.",
        "Each comparison halves the search range, so it takes O(log n) time.",
    ],
    alt="Three rows showing binary search for 42 narrowing to the answer in three comparisons.",
)
art.label(7.0, 1.6, 5.8, 0.45, "Searching for 42", 16, NAVY, True)
keys = [3, 8, 15, 23, 42, 57, 71]
art.cells(keys, 7.0, 2.15, 5.8, colors={3: PURPLE})
art.label(7.0, 2.77, 5.8, 0.4, "Middle is 23, and 42 is larger: go right", 14)
art.cells(["", "", "", "", 42, 57, 71], 7.0, 3.35, 5.8, colors={5: PURPLE})
art.label(7.0, 3.97, 5.8, 0.4, "Middle is 57, and 42 is smaller: go left", 14)
art.cells(["", "", "", "", 42, "", ""], 7.0, 4.55, 5.8, colors={4: GREEN})
art.label(7.0, 5.17, 5.8, 0.4, "Found 42 after 3 comparisons", 14, GREEN, True)

art = deck.add(
    "Recursion",
    [
        "Recursion means a function solves a problem by calling itself on a smaller version of it.",
        "Every recursive function needs a base case, which stops the calls.",
        "Each active call waits on the call stack until the smaller call returns.",
    ],
    alt="Factorial of 3 expanding down to the base case and returning 6.",
)
for i, (call, back) in enumerate(
    [("fact(3) = 3 × fact(2)", "returns 6"), ("fact(2) = 2 × fact(1)", "returns 2"),
     ("fact(1) = 1", "base case")]
):  # fmt: skip
    y = 2.0 + i * 1.3
    art.box(
        7.1 + i * 0.3,
        y,
        3.6,
        0.85,
        call,
        GREEN if i == 2 else TINT,
        WHITE if i == 2 else INK,
        15,
        True,
    )
    art.label(10.8 + i * 0.3, y, 1.3, 0.85, back, 14, MUTED, False, PP_ALIGN.LEFT)
    if i < 2:
        art.line(8.9 + i * 0.3, y + 0.85, 9.2 + i * 0.3, y + 1.3, arrow=True)

# ---- part 2: trees ------------------------------------------------------------------------
deck.part_name = "Part 2: Trees"
art = deck.add(
    "Trees",
    [
        "Before this topic, you should be comfortable with Linked Lists, because tree nodes also use pointers.",
        "A Tree is a set of nodes connected by edges, with no cycles and a single root at the top.",
        "A node's children sit directly below it, and a node with no children is a leaf.",
    ],
    alt="A general tree with a root, internal nodes and leaves labelled.",
)
art.tree(("R", ("A", ("D",), ("E",)), ("C", ("F",))),
         7.2, 1.8, 4.3, 3.5, {"R": GREEN, "D": SOFT, "E": SOFT, "F": SOFT}, notes={"R": "root"})  # fmt: skip
art.box(7.2, 5.6, 2.5, 0.65, "Green: the root", GREEN, WHITE, 14, True)
art.box(9.9, 5.6, 2.5, 0.65, "Light: the leaves", SOFT, INK, 14, True)

art = deck.add(
    "Height and Depth",
    [
        "Before this topic, you should be comfortable with Trees.",
        "The depth of a node is the number of edges from the root down to it.",
        "The height of a node is the number of edges on the longest path down to a leaf.",
        "The height of a tree is the height of its root, and a single node has height 0.",
    ],
    alt="A tree with depth labels 0, 1 and 2 beside its levels.",
)
art.tree(("P", ("Q", ("S",), ("U",)), ("W",)), 7.2, 1.9, 3.9, 3.2, {"P": GREEN})
for i, text in enumerate(["depth 0", "depth 1", "depth 2"]):
    art.label(11.3, 1.95 + i * 1.33, 1.4, 0.45, text, 14, MUTED, True)
art.box(7.2, 5.5, 5.3, 0.75, "The height of this tree is 2", TINT, INK, 16, True)

art = deck.add(
    "Binary Trees",
    [
        "Before this topic, you should be comfortable with Trees.",
        "A Binary Tree is a Tree in which every node has at most two children.",
        "The two children are called the left child and the right child.",
        "Each child is itself the root of a smaller Binary Tree, called a subtree.",
    ],
    alt="A binary tree with the left subtree of the root highlighted.",
)
art.box(7.05, 3.05, 2.85, 2.35, "", TINT)
art.tree(
    ("A", ("B", ("D",), ("E",)), ("C", None, ("F",))),
    7.2,
    1.9,
    5.3,
    3.3,
    {"B": GREEN, "D": GREEN, "E": GREEN},
)
art.label(7.05, 5.5, 2.85, 0.5, "left subtree of A", 14, GREEN, True)

art = deck.add(
    "Shapes of Binary Trees",
    [
        "A full Binary Tree gives every node either zero or two children.",
        "A complete Binary Tree fills every level, except perhaps the last, from left to right.",
        "A skewed Binary Tree has one child per node, so it behaves like a Linked List.",
        "Height decides speed: a complete tree has height near log n, and a skewed tree has height n minus 1.",
    ],
    alt="Three small trees: full, complete and skewed.",
)
art.tree(("a", ("b", ("c",), ("d",)), ("e",)), 7.0, 1.8, 2.4, 2.1, r=0.2, size=12)
art.label(7.0, 3.95, 2.4, 0.4, "Full", 14, NAVY, True)
art.tree(("f", ("g", ("h",), ("i",)), ("j", ("k",))), 10.0, 1.8, 2.7, 2.1, r=0.2, size=12)
art.label(10.0, 3.95, 2.7, 0.4, "Complete", 14, NAVY, True)
art.tree(
    ("l", None, ("m", None, ("n",))),
    8.6,
    4.45,
    2.2,
    1.75,
    {"l": RED, "m": RED, "n": RED},
    r=0.2,
    size=12,
)
art.label(10.9, 5.05, 1.4, 0.4, "Skewed", 14, RED, True)

art = deck.add(
    "Tree Traversal",
    [
        "Before this topic, you should be comfortable with Binary Trees and Recursion.",
        "Tree Traversal visits every node exactly once, and it is naturally written with Recursion.",
        "Preorder visits the node first, Inorder visits it between its subtrees, and Postorder visits it last.",
    ],
    alt="A five-node tree with its preorder, inorder and postorder visiting sequences.",
)
art.tree(("A", ("B", ("D",), ("E",)), ("C",)), 7.9, 1.65, 3.9, 2.4)
for i, (name, seq) in enumerate(
    [("Preorder", "A  B  D  E  C"), ("Inorder", "D  B  E  A  C"), ("Postorder", "D  E  B  C  A")]
):
    y = 4.3 + i * 0.78
    art.box(7.2, y, 1.9, 0.64, name, PURPLE, WHITE, 15, True)
    art.box(9.2, y, 3.4, 0.64, seq, TINT, INK, 16, True)

art = deck.add(
    "Level-Order Traversal",
    [
        "Before this topic, you should be comfortable with Tree Traversal and Queues.",
        "Level-Order Traversal visits nodes level by level, from the root downward.",
        "It places the root in a Queue, then repeatedly removes a node and adds that node's children.",
    ],
    alt="A five-node tree with colored levels and the order A B C D E.",
)
art.tree(
    ("A", ("B", ("D",), ("E",)), ("C",)),
    7.7,
    1.75,
    4.2,
    2.8,
    {"A": GREEN, "B": PURPLE, "C": PURPLE, "D": SOFT, "E": SOFT},
)
art.box(7.2, 5.0, 5.3, 0.8, "Visit order:  A  B  C  D  E", TINT, INK, 17, True)

# ---- part 3: binary search trees ----------------------------------------------------------
deck.part_name = "Part 3: Binary Search Trees"
art = deck.add(
    "Binary Search Trees",
    [
        "Before this topic, you should be comfortable with Binary Trees and Binary Search.",
        "A Binary Search Tree is a Binary Tree with one ordering rule at every node.",
        "All keys in the left subtree are smaller than the node, and all keys in the right subtree are larger.",
        "BST is the common short name for a Binary Search Tree.",
    ],
    alt="A binary search tree with root 50, smaller keys to the left and larger keys to the right.",
)
art.tree((50, (30, (20,), (40,)), (70, (60,), (80,))), 7.2, 1.8, 5.3, 3.3, {50: GREEN})
art.box(7.2, 5.45, 2.55, 0.75, "Left of 50: smaller", TINT, INK, 14, True)
art.box(9.95, 5.45, 2.55, 0.75, "Right of 50: larger", TINT, INK, 14, True)

art = deck.add(
    "Searching a BST",
    [
        "Searching a Binary Search Tree works like Binary Search, but it follows pointers rather than indexes.",
        "At each node, a smaller key goes left and a larger key goes right.",
        "The search takes time proportional to the height of the tree.",
    ],
    alt="Search for 60 following the path 50, 70, 60 highlighted in green.",
)
art.label(7.2, 1.6, 5.3, 0.45, "Searching for 60", 16, NAVY, True)
art.tree(
    (50, (30, (20,), (40,)), (70, (60,), (80,))),
    7.2,
    2.1,
    5.3,
    3.0,
    {50: GREEN, 70: GREEN, 60: GREEN, 30: SOFT, 20: SOFT, 40: SOFT, 80: SOFT},
)
art.box(7.2, 5.4, 5.3, 0.75, "60 > 50, then 60 < 70, then found", TINT, INK, 15, True)

art = deck.add(
    "Inserting into a BST",
    [
        "To insert a key, search for it until the search reaches an empty position.",
        "Attach the new key there as a leaf, so existing nodes do not move.",
        "Insertion takes time proportional to the height of the tree.",
    ],
    alt="Tree before and after inserting 35 as the right child of 30.",
)
art.tree((50, (30,), (70,)), 7.0, 2.2, 2.4, 1.7, r=0.25)
art.line(9.55, 3.1, 10.15, 3.1, arrow=True, color=PURPLE, width=2.5)
art.tree((50, (30, None, (35,)), (70,)), 10.25, 2.2, 2.45, 2.6, {35: GREEN}, r=0.25)
art.box(7.0, 5.25, 5.7, 0.8, "Insert 35: smaller than 50, larger than 30", TINT, INK, 15, True)

art = deck.add(
    "Deleting from a BST",
    [
        "Deleting a key from a Binary Search Tree has three cases.",
        "A leaf is simply removed, and a node with one child is replaced by that child.",
        "A node with two children takes the key of its inorder successor, and that successor is then removed.",
    ],
    alt="Three cards, one for each deletion case.",
)
art.steps(
    [
        "Leaf: remove it",
        "One child: the child takes its place",
        "Two children: copy the inorder successor, then delete the successor",
    ],
    7.0,
    1.9,
    5.7,
    1.05,
    0.22,
)

art = deck.add(
    "Inorder Traversal Sorts a BST",
    [
        "An Inorder Traversal of a Binary Search Tree visits its keys in sorted order.",
        "The reason is that all smaller keys are in the left subtree, and all larger keys are in the right subtree.",
        "This gives a simple test of whether a Binary Tree is a valid Binary Search Tree.",
    ],
    alt="A binary search tree above its sorted inorder sequence.",
)
art.tree((50, (30, (20,), (40,)), (70, (60,), (80,))), 7.3, 1.7, 5.2, 2.9)
art.cells([20, 30, 40, 50, 60, 70, 80], 7.1, 5.0, 5.6, 0.7, colors={i: GREEN for i in range(7)})

art = deck.add(
    "The Problem: Skewed BSTs",
    [
        "Inserting sorted keys into a Binary Search Tree builds a skewed tree.",
        "A skewed Binary Search Tree has height n minus 1, so search slows down to O(n) time.",
        "We need a way to keep the height small, whatever order the keys arrive in.",
    ],
    alt="Keys 10, 20, 30, 40 inserted in sorted order form a long right-leaning chain.",
)
art.tree(
    (10, None, (20, None, (30, None, (40,)))),
    8.2,
    1.75,
    3.3,
    3.45,
    {k: RED for k in (10, 20, 30, 40)},
)
art.box(7.0, 5.45, 5.7, 0.8, "Insert 10, 20, 30, 40: the height is 3, not 2", TINT, RED, 15, True)

# ---- part 4: balance ----------------------------------------------------------------------
deck.part_name = "Part 4: Keeping Balance"
art = deck.add(
    "Balance Factor",
    [
        "Before this topic, you should be comfortable with Height and Binary Search Trees.",
        "The Balance Factor of a node is the height of its left subtree minus the height of its right subtree.",
        "An empty subtree has height -1, so a leaf has a Balance Factor of 0.",
        "A value of 2 or -2 shows that the node is too heavy on one side.",
    ],
    alt="A tree with balance factors shown; the root has balance factor 2 and is unbalanced.",
)
art.tree((30, (20, (10,))), 7.4, 1.9, 2.8, 3.3, {30: RED, 20: PURPLE, 10: GREEN})
art.box(10.45, 1.95, 2.3, 0.65, "Factor is 2", RED, WHITE, 14, True)
art.box(10.45, 3.2, 2.3, 0.65, "Factor is 1", PURPLE, WHITE, 14, True)
art.box(10.45, 4.5, 2.3, 0.65, "Factor is 0", GREEN, WHITE, 14, True)

art = deck.add(
    "Rotation",
    [
        "Before this topic, you should be comfortable with Binary Search Trees.",
        "A Rotation is a small rearrangement of a few nodes that changes the height of a subtree.",
        "A Rotation changes only a few pointers, so it takes O(1) time.",
        "It keeps the Binary Search Tree ordering rule, so the Inorder sequence does not change.",
    ],
    alt="Two trees side by side joined by a two-way arrow, showing a rotation keeps T1, x, T2, y, T3 in order.",
)
art.tree(
    ("y", ("x", ("T1",), ("T2",)), ("T3",)),
    7.0,
    1.9,
    2.5,
    2.4,
    {"y": RED, "x": GREEN, "T1": TINT, "T2": TINT, "T3": TINT},
    r=0.25,
)
art.line(9.65, 3.1, 10.25, 3.1, arrow=True, color=PURPLE, width=2.5)
art.tree(
    ("x", ("T1",), ("y", ("T2",), ("T3",))),
    10.3,
    1.9,
    2.4,
    2.4,
    {"y": RED, "x": GREEN, "T1": TINT, "T2": TINT, "T3": TINT},
    r=0.25,
)
art.box(
    7.0,
    4.85,
    5.7,
    0.9,
    "Inorder stays the same on both sides:\nT1, x, T2, y, T3",
    TINT,
    INK,
    15,
    True,
)

art = deck.add(
    "Right Rotation",
    [
        "A Right Rotation fixes a node y that is too heavy on its left side.",
        "The left child x moves up and becomes the new root of the subtree.",
        "Node y becomes the right child of x, and the old right subtree of x becomes the left subtree of y.",
    ],
    alt="Right rotation: 30 with left child 20 and left grandchild 10 becomes 20 with children 10 and 30.",
)
art.tree((30, (20, (10,))), 7.0, 1.9, 2.3, 2.7, {30: RED, 20: GREEN, 10: SOFT})
art.line(9.45, 3.2, 10.05, 3.2, arrow=True, color=PURPLE, width=2.5)
art.tree((20, (10,), (30,)), 10.2, 2.3, 2.5, 1.7, {30: RED, 20: GREEN, 10: SOFT})
art.box(7.0, 5.05, 5.7, 0.75, "The height drops from 2 to 1", TINT, GREEN, 16, True)

art = deck.add(
    "Left Rotation",
    [
        "A Left Rotation is the mirror image, and it fixes a node x that is too heavy on its right side.",
        "The right child y moves up and becomes the new root of the subtree.",
        "Node x becomes the left child of y, and the old left subtree of y becomes the right subtree of x.",
    ],
    alt="Left rotation: 10 with right child 20 and right grandchild 30 becomes 20 with children 10 and 30.",
)
art.tree((10, None, (20, None, (30,))), 7.0, 1.9, 2.3, 2.7, {10: RED, 20: GREEN, 30: SOFT})
art.line(9.45, 3.2, 10.05, 3.2, arrow=True, color=PURPLE, width=2.5)
art.tree((20, (10,), (30,)), 10.2, 2.3, 2.5, 1.7, {10: RED, 20: GREEN, 30: SOFT})
art.box(7.0, 5.05, 5.7, 0.75, "The height drops from 2 to 1", TINT, GREEN, 16, True)

# ---- part 5: AVL trees --------------------------------------------------------------------
deck.part_name = "Part 5: AVL Trees"
art = deck.add(
    "AVL Trees",
    [
        "Before this topic, you should be comfortable with Balance Factor and Rotation.",
        "An AVL Tree is a Binary Search Tree in which every node has a Balance Factor of -1, 0 or 1.",
        "When an update breaks this rule, the tree repairs itself using Rotations.",
        "The height stays below about 1.44 log2 n, so all operations take O(log n) time.",
    ],
    alt="A valid AVL tree with each node marked by its balance factor.",
)
art.tree(
    (40, (20, (10,), (30,)), (60, None, (70,))),
    7.2,
    1.8,
    5.3,
    3.2,
    {40: GREEN, 20: GREEN, 60: GREEN, 10: GREEN, 30: GREEN, 70: GREEN},
)
art.box(
    7.2,
    5.35,
    5.3,
    0.8,
    "Every node's factor is -1, 0 or 1, so this is a valid AVL Tree",
    TINT,
    INK,
    15,
    True,
)

art = deck.add(
    "AVL Insertion: The Steps",
    [
        "AVL Insertion starts as a normal Binary Search Tree insertion.",
        "On the way back up, each ancestor updates its height and Balance Factor.",
        "The lowest unbalanced node is repaired, and one repair restores balance for the whole tree.",
    ],
    alt="Four numbered steps for inserting into an AVL tree.",
)
art.steps(
    [
        "Insert the key as in a BST",
        "Walk back up, updating heights",
        "Find the lowest node with factor 2 or -2",
        "Fix it with one single or double rotation",
    ],
    7.0,
    1.75,
    5.7,
    0.9,
    0.2,
)

art = deck.add(
    "The Four Imbalance Cases",
    [
        "The fix depends on where the new key landed below the unbalanced node z.",
        "The Left-Left and Right-Right cases need a single Rotation.",
        "The Left-Right and Right-Left cases need a double Rotation.",
    ],
    alt="A 2 by 2 grid of the four cases LL, RR, LR and RL with their fixes.",
)
for i, (name, fix, color) in enumerate(
    [("Left-Left", "Right Rotation on z", GREEN), ("Right-Right", "Left Rotation on z", GREEN),
     ("Left-Right", "Left Rotation on the child,\nthen Right Rotation on z", PURPLE),
     ("Right-Left", "Right Rotation on the child,\nthen Left Rotation on z", PURPLE)]
):  # fmt: skip
    x, y = 7.0 + (i % 2) * 2.95, 1.8 + (i // 2) * 2.25
    art.box(x, y, 2.75, 2.05, "", TINT)
    art.box(x + 0.2, y + 0.2, 2.35, 0.55, name, color, WHITE, 15, True)
    art.label(x + 0.05, y + 0.85, 2.65, 1.1, fix, 14)

art = deck.add(
    "Worked Example: Single Rotation",
    [
        "Insert 10, 20 and 30 into an empty AVL Tree in that order.",
        "After inserting 30, node 10 has a Balance Factor of -2, which is the Right-Right case.",
        "A Left Rotation on node 10 makes 20 the new root, and the tree is balanced again.",
    ],
    alt="Tree 10-20-30 as a right chain becoming 20 with children 10 and 30.",
)
art.tree((10, None, (20, None, (30,))), 7.0, 1.9, 2.3, 2.7, {10: RED, 20: PURPLE, 30: GREEN})
art.line(9.45, 3.2, 10.05, 3.2, arrow=True, color=PURPLE, width=2.5)
art.tree((20, (10,), (30,)), 10.2, 2.3, 2.5, 1.7, {10: PURPLE, 20: GREEN, 30: PURPLE})
art.box(7.0, 5.05, 5.7, 0.75, "Left Rotation on 10", TINT, INK, 16, True)

art = deck.add(
    "Worked Example: Double Rotation",
    [
        "Insert 30, 10 and 20 into an empty AVL Tree in that order.",
        "Node 30 has a Balance Factor of 2, and the new key lies in the Left-Right position.",
        "A Left Rotation on 10 gives the Left-Left shape, and a Right Rotation on 30 finishes the repair.",
    ],
    alt="Three trees showing 30-10-20, then 30-20-10, then 20 with children 10 and 30.",
)
art.tree((30, (10, None, (20,))), 6.95, 2.0, 1.6, 2.4, {30: RED, 10: PURPLE, 20: GREEN}, r=0.25)
art.line(8.6, 3.2, 9.0, 3.2, arrow=True, color=PURPLE, width=2.5)
art.tree((30, (20, (10,))), 9.05, 2.0, 1.55, 2.4, {30: RED, 10: PURPLE, 20: GREEN}, r=0.25)
art.line(10.65, 3.2, 11.0, 3.2, arrow=True, color=PURPLE, width=2.5)
art.tree((20, (10,), (30,)), 11.05, 2.4, 1.75, 1.4, {30: PURPLE, 10: PURPLE, 20: GREEN}, r=0.25)
art.box(
    7.0, 5.05, 5.75, 0.75, "Left Rotation on 10, then Right Rotation on 30", TINT, INK, 15, True
)

art = deck.add(
    "AVL Deletion",
    [
        "AVL Deletion starts as a normal Binary Search Tree deletion.",
        "Each ancestor then updates its height and Balance Factor on the way back up.",
        "Unlike insertion, one deletion may need Rotations at several levels, up to O(log n) of them.",
    ],
    alt="Two cards comparing the number of repairs after an insertion and after a deletion.",
)
art.box(7.1, 2.0, 2.65, 2.7, "", TINT)
art.label(7.15, 2.15, 2.55, 0.5, "Insertion", 17, NAVY, True)
art.label(7.15, 2.75, 2.55, 1.0, "1", 44, GREEN, True)
art.label(7.15, 3.8, 2.55, 0.7, "repair at most", 14)
art.box(10.0, 2.0, 2.65, 2.7, "", TINT)
art.label(10.05, 2.15, 2.55, 0.5, "Deletion", 17, NAVY, True)
art.label(10.05, 2.75, 2.55, 1.0, "O(log n)", 30, RED, True)
art.label(10.05, 3.8, 2.55, 0.7, "repairs at most", 14)

art = deck.add(
    "BST or AVL Tree?",
    [
        "A plain Binary Search Tree is simpler, but its worst case is O(n) time.",
        "An AVL Tree does extra work on updates, and it guarantees O(log n) time for every operation.",
        "Choose an AVL Tree when searches are frequent and slow worst cases are not acceptable.",
    ],
    alt="Comparison cards of the worst-case height for one million keys.",
)
art.label(7.0, 1.65, 5.7, 0.5, "Worst-case height for 1,000,000 keys", 16, NAVY, True)
art.box(7.0, 2.35, 2.75, 2.6, "", TINT)
art.label(7.05, 2.5, 2.65, 0.5, "Plain BST", 16, NAVY, True)
art.label(7.05, 3.15, 2.65, 1.2, "999,999", 30, RED, True)
art.box(9.95, 2.35, 2.75, 2.6, "", TINT)
art.label(10.0, 2.5, 2.65, 0.5, "AVL Tree", 16, NAVY, True)
art.label(10.0, 3.15, 2.65, 1.2, "about 29", 30, GREEN, True)

# ---- closing ------------------------------------------------------------------------------
art = deck.cover(
    "Key Takeaways",
    [
        "An AVL Tree is a Binary Search Tree that repairs its own balance.",
        "Balance Factor finds the problem, and Rotation fixes it.",
        "Search, insertion and deletion all stay at O(log n) time.",
    ],
)
art.tree((20, (10,), (30,)), 9.4, 2.7, 3.0, 2.0, {20: GREEN, 10: SOFT, 30: SOFT}, r=0.33, size=16)

deck.prs.core_properties.title = "From Trees to AVL Trees"
deck.prs.core_properties.subject = "Data structures course slides"
deck.prs.core_properties.author = ""
deck.prs.save(OUT)
print(f"{len(deck.prs.slides)} slides -> {OUT}")
