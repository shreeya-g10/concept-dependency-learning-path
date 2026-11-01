"""root_cause — validated graph + quiz items + student answers -> root_cause.json

    python -m cdlp.root_cause --graph outputs/validated_graph.json \
        --quiz outputs/quiz_items.json --answers outputs/student_answers.json \
        --state outputs/student_state.json --out outputs/root_cause.json

One trace per wrong answer. --method llm (default) calls the LLM through api.trace;
--method target / nearest run the RQ3 baselines with no LLM. --state is optional:
without it every concept's mastery is unknown.
"""

import argparse
import sys
from pathlib import Path

from cdlp.root_cause import api
from cdlp.root_cause.baselines import METHODS
from cdlp.shared.io import read_json, write_json

SCHEMA_VERSION = "1.1"


def tracer(method: str):
    return api.trace if method == "llm" else METHODS[method]


def mastery_by_student(state_path: Path | None) -> dict[str, dict[str, float]]:
    if state_path is None:
        return {}
    return {s["student_id"]: s.get("mastery", {}) for s in read_json(state_path)["students"]}


def run(graph: dict, quiz: dict, answers: dict, mastery: dict, method: str) -> dict:
    items = {i["id"]: i for i in quiz["items"]}
    trace = tracer(method)
    traces = []
    for row in answers["answers"]:
        if row["correct"]:
            continue
        item = items.get(row["item_id"])
        if item is None:
            print(f"skipped {row['item_id']}: not in quiz items", file=sys.stderr)
            continue
        result = trace(graph, item, row["answer"], mastery.get(row["student_id"], {}))
        traces.append({"student_id": row["student_id"], **result})
    return {"schema_version": SCHEMA_VERSION, "course_id": answers["course_id"], "traces": traces}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--state", type=Path, help="student_state.json (mastery per student)")
    parser.add_argument("--method", choices=["llm", *METHODS], default="llm")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    out = run(
        read_json(args.graph),
        read_json(args.quiz),
        read_json(args.answers),
        mastery_by_student(args.state),
        args.method,
    )
    write_json(args.out, out)
    print(f"{len(out['traces'])} traces ({args.method}) -> {args.out}")


if __name__ == "__main__":
    main()
