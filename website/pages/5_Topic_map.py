"""Topic map: learn before -> this topic -> learn next, as tappable cards.

Works on a phone and on weak internet: the picture sends the whole drawing library, so a map
of more than FULL_MAP_LIMIT links stays behind a button. Two views once a student has a plan:
My Study Path (their topics, in the words of the study plan) and All Topics. Everything here
reads the ACCEPT links of validated_graph.json directly; the machine-written `reason` of a link
is for teachers and is not shown.
"""

from __future__ import annotations

import common
import streamlit as st
import streamlit.components.v1 as components
import strings as S
import study_path
import ui

from cdlp.learning_path import api

FULL_MAP_LIMIT = 30  # at most this many links: the picture shows without asking

# The page background and text of .streamlit/config.toml, so the picture sits in the theme.
MAP_BACKGROUND = "#F4F2FB"
MAP_TEXT = "#1F1B3D"
# background, border, border width
PATH_COLOURS = {
    "next": ("#FEF3C7", "#D97706", 3.5),
    "done": ("#D1FAE5", "#059669", 2.0),
    "know_it": ("#D1FAE5", "#059669", 2.0),
    "quick_revision": ("#DBEAFE", "#2563EB", 2.0),
    "study_this": ("#E6E2F6", "#4B3F8F", 2.0),
    "start_here": ("#FCE7F3", "#BE185D", 2.0),
    "not_checked": ("#F3F4F6", "#6B7280", 1.5),
    "later": ("#F3F4F6", "#6B7280", 1.5),
}
GOAL_BORDER = "#4338CA"
# pyvis puts its picture on a white page with a grey frame, and vis.js has bright green buttons.
MAP_CSS = (
    f"html, body, .card {{ background: {MAP_BACKGROUND} !important; }}"
    ".card, #mynetwork { border: 0 !important; }"
    ".vis-navigation .vis-button { filter: hue-rotate(130deg) saturate(0.6); }"
)

ui.page_header(S.MAP_TITLE, S.MAP_INTRO, source_file="validated_graph.json")

names = common.concept_names()
concepts = {c["id"]: c for c in common.load("concepts.json")["concepts"]}
graph_data = common.load("validated_graph.json")
accepted = [e for e in graph_data.get("edges", []) if e.get("decision") == "ACCEPT"]


def name(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def strength_words(edge: dict) -> str:
    return S.MAP_NEED_LABEL if edge.get("strength", "hard") == "hard" else S.MAP_HELP_LABEL


if not names:
    ui.empty_state(S.MAP_EMPTY, S.MAP_EMPTY_NEXT, action=S.TOPICS_ADD, page="add", icon="📄")
    st.stop()

# Only topics with an accepted link. The others stay in concepts.json and on See your topics;
# the teacher page lists them.
linked = {end for edge in accepted for end in (edge["source"], edge["target"])}
ready = sorted((c for c in names if c in linked), key=lambda c: names[c].lower())
if not ready:
    st.info(S.MAP_NONE_READY, icon="ℹ️")
    st.stop()

# The topic in focus: kept under a plain key, because widget state does not survive other pages.
if st.session_state.get("map_focus") not in ready:
    remembered = st.session_state.get("study_target")
    st.session_state.map_focus = remembered if remembered in ready else ready[0]


def focus_on(concept_id: str) -> None:
    st.session_state.map_focus = concept_id
    st.session_state.map_search = ""


def search(query: str) -> list[str]:
    typed = query.strip().lower()
    return [
        c
        for c in ready
        if typed in names[c].lower()
        or any(typed in a.lower() for a in concepts.get(c, {}).get("aliases", []))
    ]


def wrap_label(label: str, max_chars: int = 18) -> str:
    lines: list[list[str]] = [[]]
    for word in label.split():
        if lines[-1] and len(" ".join([*lines[-1], word])) > max_chars:
            lines.append([])
        lines[-1].append(word)
    return "\n".join(" ".join(line) for line in lines)


def path_view() -> dict | None:
    """The student's plan for the topic they picked, or None when they have no plan yet."""
    target = st.session_state.get("study_target")
    if target not in ready or not study_path.answered(common.get_active_course()):
        return None
    quiz = common.load("quiz_items.json")
    order = api.prerequisite_order(graph_data, target)
    return {
        "target": target,
        "order": order,
        "edges": [e for e in accepted if e["source"] in order and e["target"] in order],
        "plan": study_path.plan_state(common.get_active_course(), graph_data, quiz, target),
    }


def path_summary(path: dict) -> str:
    plan = path["plan"]
    if plan["next_up"]:
        return S.PLAN_JUST_START.format(topic=name(plan["next_up"]))
    if plan["order"]:
        return S.PLAN_ALL_DONE.format(topic=name(path["target"]))
    return S.PLAN_ALL_KNOWN.format(topic=name(path["target"]))


def path_node(path: dict, concept_id: str) -> dict:
    """The add_node arguments for one topic of My Study Path."""
    state = study_path.state_of(path["plan"], concept_id)
    words = study_path.topic_words(path["plan"], concept_id)
    background, border, width = PATH_COLOURS[state]
    if concept_id == path["target"]:
        words = [*words, S.MAP_GOAL]
        if state != "next":
            border, width = GOAL_BORDER, 3.0
    lines = [wrap_label(name(concept_id)), *(wrap_label(w, 22) for w in words)]
    return {
        "label": "\n".join(lines),
        "words": ", ".join(words),
        "background": background,
        "border": border,
        "width": width,
    }


def all_topics_node(concept_id: str) -> dict:
    return {
        "label": wrap_label(name(concept_id)),
        "background": "#E6E2F6",
        "border": "#4B3F8F",
        "width": 1.5,
    }


def draw(nodes: list[tuple[str, dict]], edges: list[dict], *, in_order: bool) -> None:
    """The picture, or a list of links if the drawing library is missing."""
    try:
        from pyvis.network import Network
    except ImportError:
        for concept_id, node in nodes:
            if node.get("words"):
                st.markdown(S.MAP_PATH_LINE.format(topic=name(concept_id), words=node["words"]))
        for edge in edges:
            st.markdown(
                S.MAP_LIST_ONLY.format(
                    source=name(edge["source"]),
                    target=name(edge["target"]),
                    strength=strength_words(edge),
                )
            )
        return

    st.caption(S.MAP_PICTURE_NOTE)
    network = Network(
        height="560px",
        width="100%",
        directed=True,
        bgcolor=MAP_BACKGROUND,
        font_color=MAP_TEXT,
        cdn_resources="in_line",
    )
    for concept_id, node in nodes:
        network.add_node(
            concept_id,
            label=node["label"],
            title=name(concept_id),
            shape="box",
            margin=10,
            borderWidth=node["width"],
            borderWidthSelected=3.0,
            color={
                "background": node["background"],
                "border": node["border"],
                "highlight": {"background": node["background"], "border": "#312E81"},
            },
            font={"size": 14, "color": MAP_TEXT, "face": "system-ui, sans-serif"},
            shadow={"enabled": True, "color": "rgba(0,0,0,0.06)", "size": 5, "x": 1, "y": 2},
        )
    for edge in edges:
        network.add_edge(
            edge["source"],
            edge["target"],
            arrows={"to": {"enabled": True, "scaleFactor": 0.85}},
            color="#4B3F8F",
            dashes=edge.get("strength", "hard") != "hard",
            title=strength_words(edge),
        )
    network.set_options(PATH_LAYOUT if in_order else FREE_LAYOUT)
    themed = network.generate_html().replace("</head>", f"<style>{MAP_CSS}</style></head>", 1)
    components.html(themed, height=580, scrolling=False)
    st.caption(S.MAP_KEY)


PATH_LAYOUT = """
{
  "layout": {
    "hierarchical": {
      "enabled": true,
      "direction": "UD",
      "sortMethod": "directed",
      "nodeSpacing": 170,
      "levelSeparation": 120
    }
  },
  "physics": { "enabled": false },
  "interaction": { "hover": true, "zoomView": true, "dragNodes": true }
}
"""
FREE_LAYOUT = """
{
  "layout": { "randomSeed": 7 },
  "edges": {
    "smooth": { "type": "cubicBezier", "roundness": 0.25 }
  },
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -2500,
      "centralGravity": 0.25,
      "springLength": 110,
      "springConstant": 0.04,
      "damping": 0.12,
      "avoidOverlap": 1.0
    },
    "minVelocity": 0.75
  },
  "interaction": {
    "hover": true,
    "zoomView": true,
    "navigationButtons": true
  }
}
"""


def show_map() -> None:
    """The view switch, then the picture. Near the top, so it is easy to find.

    A view of more than FULL_MAP_LIMIT links sends the drawing library only after its own tap,
    so opening a large path never also opens a larger All Topics map.
    """
    path = path_view()
    on_path = (
        path is not None
        and st.radio(
            S.MAP_VIEW_LABEL,
            [S.MAP_VIEW_PATH, S.MAP_VIEW_ALL],
            horizontal=True,
            key="map_view_mode",
        )
        == S.MAP_VIEW_PATH
    )
    edges = path["edges"] if on_path else accepted
    if on_path:
        st.markdown(path_summary(path))
    if len(edges) > FULL_MAP_LIMIT:
        flag = "map_path_full" if on_path else "map_full"
        showing = st.session_state.get(flag, False)
        see, hide = (
            (S.MAP_SEE_PATH, S.MAP_HIDE_PATH) if on_path else (S.MAP_SEE_FULL, S.MAP_HIDE_FULL)
        )
        if ui.action_button(
            hide if showing else see, icon="🗺️", primary=False, key="map_full_button"
        ):
            st.session_state[flag] = not showing
            st.rerun()
        if not showing:
            return

    if on_path:
        nodes = [(c, path_node(path, c)) for c in path["order"]]
    else:
        nodes = [(c, all_topics_node(c)) for c in sorted(linked)]
    draw(nodes, edges, in_order=on_path)


st.markdown(S.MAP_READY_COUNT.format(ready=len(ready), total=len(names)))
show_map()
query = st.text_input(S.MAP_PICK, placeholder=S.MAP_SEARCH_HINT, key="map_search")
if query.strip():
    found = search(query)
    if not found:
        st.info(S.MAP_TOPIC_NOT_READY, icon="ℹ️")
    for concept_id in found:
        st.button(
            name(concept_id),
            key=f"found_{concept_id}",
            width="stretch",
            on_click=focus_on,
            args=(concept_id,),
        )
with st.expander(S.MAP_ALL_READY):
    for concept_id in ready:
        st.button(
            name(concept_id),
            key=f"all_{concept_id}",
            width="stretch",
            on_click=focus_on,
            args=(concept_id,),
        )

focus = st.session_state.map_focus
before = sorted((e for e in accepted if e["target"] == focus), key=lambda e: name(e["source"]))
after = sorted((e for e in accepted if e["source"] == focus), key=lambda e: name(e["target"]))


def card(concept_id: str, where: str) -> None:
    st.button(
        name(concept_id),
        key=f"{where}_{concept_id}",
        width="stretch",
        on_click=focus_on,
        args=(concept_id,),
    )


if before:
    st.markdown(S.MAP_BEFORE)
    for edge in before:
        card(edge["source"], "before")
        st.caption(strength_words(edge))
    st.markdown(S.MAP_ARROW)

with st.container(border=True):
    st.markdown(S.MAP_THIS_TOPIC.format(topic=name(focus)))
    if concepts.get(focus, {}).get("description"):
        st.write(concepts[focus]["description"])
    sources = concepts.get(focus, {}).get("sources", [])
    if sources:
        st.caption(common.citation(sources[0].get("doc", ""), sources[0].get("page", "")))

if after:
    st.markdown(S.MAP_ARROW)
    st.markdown(S.MAP_AFTER)
    for edge in after:
        card(edge["target"], "after")

# Never say "nothing comes first": a missing link may only mean we have not found it yet.
if not before:
    st.caption(S.MAP_NOTHING_BEFORE)
if not after:
    st.caption(S.MAP_NOTHING_AFTER)

st.markdown(S.MAP_LINKS)
for edge in [*before, *after]:
    with st.expander(f"{name(edge['source'])} → {name(edge['target'])}"):
        for ev in edge.get("evidence", []):
            if ev.get("quote"):
                st.markdown(f"> {ev['quote']}")
            st.caption(common.citation(ev.get("doc", ""), ev.get("page", "")))
