"""Draw the AVL demo's accepted graph exactly as the website's Topic map draws it, for Fig. 5.

The node, edge and colour settings are copied from website/pages/5_Topic_map.py (All topics view),
with the same physics layout and seed. For print, labels are larger (30 instead of 14) and the
springs shorter and weaker (95 and -2000 instead of 110 and -2500), and the navigation buttons are
left out, so the picture is the website's drawing, not a screenshot of it. The HTML is then
photographed with headless Chrome:

    python docs/paper/ieee/website_map.py
"""

import json
import subprocess
import tempfile
from pathlib import Path

from pyvis.network import Network

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATA = ROOT / "docs/paper/results/avl_demo_accepted_graph.json"
PNG = HERE / "figures" / "fig_avl_website_map.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# From website/pages/5_Topic_map.py
MAP_BACKGROUND = "#F4F2FB"
MAP_TEXT = "#1F1B3D"
MAP_CSS = (
    f"html, body, .card {{ background: {MAP_BACKGROUND} !important; margin: 0; }}"
    ".card, #mynetwork { border: 0 !important; }"
)
LAYOUT = """
{
  "layout": { "randomSeed": 7 },
  "edges": {
    "smooth": { "type": "cubicBezier", "roundness": 0.25 }
  },
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -2000,
      "centralGravity": 0.25,
      "springLength": 95,
      "springConstant": 0.04,
      "damping": 0.12,
      "avoidOverlap": 1.0
    },
    "minVelocity": 0.75
  }
}
"""


def wrap_label(label: str, max_chars: int = 18) -> str:
    lines: list[list[str]] = [[]]
    for word in label.split():
        if lines[-1] and len(" ".join([*lines[-1], word])) > max_chars:
            lines.append([])
        lines[-1].append(word)
    return "\n".join(" ".join(line) for line in lines)


def main() -> None:
    data = json.loads(DATA.read_text())
    names = {}
    for edge in data["edges"]:
        names[edge["source"]], names[edge["target"]] = edge["source_name"], edge["target_name"]
    network = Network(
        height="900px",
        width="100%",
        directed=True,
        bgcolor=MAP_BACKGROUND,
        font_color=MAP_TEXT,
        cdn_resources="in_line",
    )
    for concept_id in sorted(names):
        network.add_node(
            concept_id,
            label=wrap_label(names[concept_id]),
            shape="box",
            margin=12,
            borderWidth=2.5,
            color={"background": "#E6E2F6", "border": "#4B3F8F"},
            font={"size": 30, "color": MAP_TEXT, "face": "system-ui, sans-serif"},
        )
    for edge in data["edges"]:
        network.add_edge(
            edge["source"],
            edge["target"],
            arrows={"to": {"enabled": True, "scaleFactor": 0.85}},
            color="#4B3F8F",
            dashes=edge["strength"] != "hard",
        )
    network.set_options(LAYOUT)
    html = network.generate_html().replace("</head>", f"<style>{MAP_CSS}</style></head>", 1)
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "map.html"
        page.write_text(html)
        subprocess.run(
            [CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=2",
             "--window-size=1100,1100", "--virtual-time-budget=15000", f"--screenshot={PNG}",
             page.as_uri()],
            check=True, capture_output=True,
        )  # fmt: skip
    crop_margins()
    print("wrote", PNG.name)


def crop_margins(pad: int = 30) -> None:
    """Cut the empty background around the drawing."""
    from PIL import Image, ImageChops

    image = Image.open(PNG).convert("RGB")
    empty = Image.new("RGB", image.size, MAP_BACKGROUND)
    left, top, right, bottom = ImageChops.difference(image, empty).getbbox()
    image.crop((max(left - pad, 0), max(top - pad, 0), right + pad, bottom + pad)).save(PNG)


if __name__ == "__main__":
    main()
