"""For teachers: the links between topics the AI suggested, before they were checked.

Shows how many topic pairs were considered, every suggested link with its quotes, a filter
by topic, and a comparison with the no-filter baseline (relationships_baseline.json) when
that file exists.
"""

from __future__ import annotations

import json

import streamlit as st
import ui
from common import ROOT, concept_names, get_active_course, load, resolve_path

ui.page_header(
    "AI suggestions",
    "The links between topics the AI suggested, before the AI checks.",
    source_file="relationships.json",
    teacher=True,
)

course = get_active_course()
names = concept_names()
relationships = load("relationships.json")["relationships"]


STRENGTH_WORDS = {"hard": "Must learn first", "soft": "Helps to learn first"}


def label(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


def strength_word(strength: str) -> str:
    return STRENGTH_WORDS.get(strength, strength)


def candidate_count(course_id: str) -> int | None:
    """Candidates from the candidate-recall run, if it was run for this course.

    The page may not import discovery code (it loads an embedding model), so it reads
    the result file that `python -m cdlp.discovery.candidate_recall` writes.
    """
    path = ROOT / "cdlp" / "discovery" / "results" / f"candidate_recall_{course_id}.json"
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["metrics"]["candidates"])
    except (OSError, KeyError, ValueError, TypeError):
        return None


# ---- How many pairs were considered -----------------------------------------
st.subheader("From topic pairs to suggested links")
n_concepts = len(names)
n_pairs = n_concepts * (n_concepts - 1) // 2
n_candidates = candidate_count(course)
st.metric("Topics", n_concepts)
st.metric("Possible topic pairs", n_pairs)
st.metric(
    "Pairs sent to the AI",
    "n/a" if n_candidates is None else n_candidates,
    help="Only pairs that look related are sent to the AI, never every possible pair.",
)
st.metric("Suggested links", len(relationships))
if n_candidates is None:
    st.caption(
        "No count for this subject yet. To fill it in, run "
        "`python -m cdlp.discovery.candidate_recall`."
    )
elif n_pairs:
    st.caption(
        f"The filter kept {n_candidates / n_pairs:.0%} of pairs; "
        f"the AI suggested a link for {len(relationships)} of them."
    )

# ---- Filter -----------------------------------------------------------------
st.subheader("Suggested links")
concept_ids = sorted({c for r in relationships for c in (r["source"], r["target"])}, key=label)
selected = st.selectbox("Filter by topic", ["(all)", *concept_ids], format_func=label)
strengths = st.multiselect(
    "Kind of link", ["hard", "soft"], default=["hard", "soft"], format_func=strength_word
)

shown = [
    r
    for r in relationships
    if (selected == "(all)" or selected in (r["source"], r["target"]))
    and r["strength"] in strengths
]
st.dataframe(
    [
        {
            "From": label(r["source"]),
            "To": label(r["target"]),
            "Kind": strength_word(r["strength"]),
            "How sure the AI is": r["confidence"],
            "Quotes": len(r["evidence"]),
            "Both directions": bool(r.get("bidirectional")),
        }
        for r in shown
    ],
    width="stretch",
    hide_index=True,
)

st.caption(
    "Technical terms: a suggested link is a candidate prerequisite edge · Must learn first = "
    "hard, Helps to learn first = soft · How sure the AI is = discovery confidence."
)

# ---- Evidence quotes --------------------------------------------------------
st.subheader("Quotes from the course files")
if not shown:
    st.info("No suggested link matches the filter. Change the filter above to see more.")
for r in shown:
    with st.expander(
        f"{label(r['source'])} → {label(r['target'])} · {strength_word(r['strength'])}"
    ):
        if r.get("bidirectional"):
            st.warning(
                "The AI suggested both directions: reverse "
                f"{r.get('reverse_strength', '?')}, confidence {r.get('reverse_confidence', '?')}. "
                "The AI checks pick the direction or send it to you."
            )
        st.caption(f"{r['strength']} · confidence {r['confidence']:.2f}")
        if not r["evidence"]:
            st.caption("No quote given.")
        for ev in r["evidence"]:
            st.markdown(f"> {ev.get('quote') or '(no quote)'}")
            st.caption(f"{ev.get('doc', '?')} p.{ev.get('page', '?')}")

# ---- Baseline comparison ----------------------------------------------------
st.subheader("Compared with a simpler method")
st.caption("Technical term: the no-filter baseline.")
if not resolve_path("relationships_baseline.json").exists():
    st.info(
        "The simpler method has not been run for this subject. To compare, run discovery "
        "with `--baseline`."
    )
else:
    baseline = load("relationships_baseline.json")["relationships"]
    ours = {(r["source"], r["target"]) for r in relationships}
    theirs = {(r["source"], r["target"]) for r in baseline}
    both, only_ours, only_base = ours & theirs, ours - theirs, theirs - ours
    st.metric("Links from the simpler method", len(theirs))
    st.metric("Found by both", len(both))
    st.metric("Found only by our method", len(only_ours))
    st.metric("Found only by the simpler method", len(only_base))
    st.caption(
        "The simpler method makes one AI call with the full topic list and no filter. "
        "When two methods agree, that does not prove they are right: see the test results on "
        "the AI checks page."
    )
    st.dataframe(
        [
            {"From": label(s), "To": label(t), "Found by": found_by}
            for found_by, pairs in (
                ("both", both),
                ("our method only", only_ours),
                ("simpler method only", only_base),
            )
            for s, t in sorted(pairs)
        ],
        width="stretch",
        hide_index=True,
    )
