"""RQ3: top-1 / top-3 accuracy of root-cause tracing against a labelled answer set.

The dataset has the root_cause_testset.json shape (student_answers rows plus
`expected_concept`). Mastery comes from a `mastery` field on each row if present
(the dev set has one), otherwise from --state by student_id, otherwise unknown.

    # baselines, no LLM
    python -m cdlp.root_cause.evaluate --dataset cdlp/root_cause/tests/fixtures/dev_set.json \
        --graph cdlp/shared/examples/validated_graph.json \
        --quiz cdlp/shared/examples/quiz_items.json --methods target nearest

Writes cdlp/root_cause/results/<name>.json with the config, per-row predictions
and the scores. Develop the prompt on the dev set only, never on the test set.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from cdlp.root_cause import tracer
from cdlp.root_cause.__main__ import mastery_by_student
from cdlp.root_cause.__main__ import tracer as pick_tracer
from cdlp.root_cause.baselines import METHODS
from cdlp.shared.io import read_json
from cdlp.shared.llm import DEFAULT_SEED

RESULTS = Path(__file__).parent / "results"


def evaluate(graph: dict, quiz: dict, dataset: dict, state: dict, method: str) -> dict:
    items = {i["id"]: i for i in quiz["items"]}
    trace = pick_tracer(method)
    rows, top1, top3, fallbacks = [], 0, 0, 0
    wrong = [r for r in dataset["answers"] if not r["correct"]]
    for r in wrong:
        mastery = r.get("mastery") or state.get(r["student_id"], {})
        result = trace(graph, items[r["item_id"]], r["answer"], mastery)
        ranked = [c["concept_id"] for c in result["candidates"]]
        hit1 = ranked[:1] == [r["expected_concept"]]
        hit3 = r["expected_concept"] in ranked[:3]
        top1 += hit1
        top3 += hit3
        fallbacks += result["explanation"].startswith(tracer.FALLBACK_PREFIX)
        rows.append(
            {
                "student_id": r["student_id"],
                "item_id": r["item_id"],
                "expected": r["expected_concept"],
                "ranked": ranked,
                "top1": hit1,
                "top3": hit3,
                "explanation": result["explanation"],
            }
        )
    n = len(wrong)
    return {
        "method": method,
        "n": n,
        "top1_accuracy": round(top1 / n, 4) if n else None,
        "top3_accuracy": round(top3 / n, 4) if n else None,
        "llm_fallbacks": fallbacks if method == "llm" else None,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--quiz", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--methods", nargs="+", choices=["llm", *METHODS], default=["llm"])
    parser.add_argument("--name", help="results file name (default: <dataset stem>)")
    args = parser.parse_args()

    graph, quiz, dataset = read_json(args.graph), read_json(args.quiz), read_json(args.dataset)
    state = mastery_by_student(args.state)
    config = {
        "dataset": str(args.dataset),
        "graph": str(args.graph),
        "quiz": str(args.quiz),
        "state": str(args.state) if args.state else None,
        "methods": args.methods,
        "llm": {
            "model": tracer.model_id(),
            "prompt_version": tracer.PROMPT_VERSION,
            "temperature": tracer.TEMPERATURE,
            "seed": DEFAULT_SEED,
        },
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    results = [evaluate(graph, quiz, dataset, state, m) for m in args.methods]
    out = RESULTS / f"{args.name or args.dataset.stem}.json"
    RESULTS.mkdir(exist_ok=True)
    out.write_text(json.dumps({"config": config, "results": results}, indent=2) + "\n")
    for r in results:
        print(f"{r['method']:8} n={r['n']}  top1={r['top1_accuracy']}  top3={r['top3_accuracy']}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
