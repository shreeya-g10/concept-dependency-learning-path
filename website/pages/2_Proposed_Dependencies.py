"""Owner: Shreeya (initial code: Sneha). Prerequisite edges the LLM proposed, before validation.

Shows the candidate funnel (all pairs -> candidates -> proposed edges), every proposed
edge with its evidence quotes, a filter by concept, and a comparison with the
no-filter baseline (relationships_baseline.json) when that file exists.
"""

from __future__ import annotations

import json

import streamlit as st
from common import (
    ROOT,
    concept_names,
    get_active_course,
    load,
    page_header,
    render_sidebar,
    resolve_path,
)

render_sidebar()
page_header("Proposed Dependencies", "Shreeya", "relationships.json")

course = get_active_course()
names = concept_names()
relationships = load("relationships.json")["relationships"]


def label(concept_id: str) -> str:
    return names.get(concept_id, concept_id)


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


# ---- Candidate funnel -------------------------------------------------------
st.subheader("Candidate funnel")
n_concepts = len(names)
n_pairs = n_concepts * (n_concepts - 1) // 2
n_candidates = candidate_count(course)
cols = st.columns(4)
cols[0].metric("Concepts", n_concepts)
cols[1].metric("Unordered pairs", n_pairs)
cols[2].metric(
    "Candidates",
    "n/a" if n_candidates is None else n_candidates,
    help="From cdlp/discovery/results/candidate_recall_<course>.json. Only candidates "
    "are sent to the LLM, never all O(n²) pairs.",
)
cols[3].metric("Proposed edges", len(relationships))
if n_candidates is None:
    st.caption(
        f"No candidate count for `{course}` yet. Run `python -m cdlp.discovery.candidate_recall` "
        "to fill it in."
    )
elif n_pairs:
    st.caption(
        f"The filter kept {n_candidates / n_pairs:.0%} of pairs; "
        f"the LLM proposed an edge for {len(relationships)} of them."
    )

# ---- Filter -----------------------------------------------------------------
st.subheader("Proposed edges")
concept_ids = sorted({c for r in relationships for c in (r["source"], r["target"])}, key=label)
selected = st.selectbox("Filter by concept", ["(all)", *concept_ids], format_func=label)
strengths = st.multiselect("Strength", ["hard", "soft"], default=["hard", "soft"])

shown = [
    r
    for r in relationships
    if (selected == "(all)" or selected in (r["source"], r["target"]))
    and r["strength"] in strengths
]
st.dataframe(
    [
        {
            "id": r["id"],
            "from": label(r["source"]),
            "to": label(r["target"]),
            "strength": r["strength"],
            "confidence": r["confidence"],
            "evidence chunks": len(r["evidence"]),
            "both directions": bool(r.get("bidirectional")),
        }
        for r in shown
    ],
    width="stretch",
    hide_index=True,
)

# ---- Evidence quotes --------------------------------------------------------
st.subheader("Evidence quotes")
if not shown:
    st.info("No proposed edge matches the filter.")
for r in shown:
    with st.expander(
        f"{label(r['source'])} → {label(r['target'])} · {r['strength']} · {r['confidence']:.2f}"
    ):
        if r.get("bidirectional"):
            st.warning(
                "The LLM proposed both directions (tied course position): reverse "
                f"{r.get('reverse_strength', '?')}, confidence {r.get('reverse_confidence', '?')}. "
                "The validator picks the direction or sends it to human review."
            )
        if not r["evidence"]:
            st.caption("No evidence chunk cited.")
        for ev in r["evidence"]:
            st.markdown(f"> {ev.get('quote') or '(no quote)'}")
            st.caption(f"{ev.get('doc', '?')} p.{ev.get('page', '?')} · chunk `{ev['chunk_id']}`")
        if r.get("method"):
            st.caption(f"method: `{r['method']}`")

# ---- Baseline comparison ----------------------------------------------------
st.subheader("Compared with the baseline prompt")
if not resolve_path("relationships_baseline.json").exists():
    st.info(
        "No relationships_baseline.json for this course. Run discovery with `--baseline` "
        "to compare."
    )
else:
    baseline = load("relationships_baseline.json")["relationships"]
    ours = {(r["source"], r["target"]) for r in relationships}
    theirs = {(r["source"], r["target"]) for r in baseline}
    both, only_ours, only_base = ours & theirs, ours - theirs, theirs - ours
    cols = st.columns(4)
    cols[0].metric("Baseline edges", len(theirs))
    cols[1].metric("In both", len(both))
    cols[2].metric("Only filter + discovery", len(only_ours))
    cols[3].metric("Only baseline", len(only_base))
    st.caption(
        "Baseline: one call with the full concept list and no candidate filter. "
        "Agreement is not correctness: see the RQ1 results on the Validation Agent page."
    )
    st.dataframe(
        [
            {"from": label(s), "to": label(t), "found by": found_by}
            for found_by, pairs in (
                ("both", both),
                ("filter + discovery only", only_ours),
                ("baseline only", only_base),
            )
            for s, t in sorted(pairs)
        ],
        width="stretch",
        hide_index=True,
    )
