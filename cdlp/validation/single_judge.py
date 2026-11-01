"""RQ1 baseline "single LLM judge": the semantic check alone decides every edge.

    python -m cdlp.validation.single_judge --relationships outputs/rq1/ds101/relationships.json \
        --concepts outputs/ds101/concepts.json --out outputs/rq1/ds101/validated_single_judge.json

One validator call per proposed edge with the semantic prompt (default `semantic_v2`),
no retrieval and no other check. ACCEPT if the grade is strong or medium, else REJECT
(the rule in semantic_check.JUDGE_ACCEPT). Never HUMAN_REVIEW.

Output: the shape cdlp/validation/evaluate.py reads for a `validated` setting
(`edges` with `source`, `target`, `decision`), plus the grade and rationale per edge.
It is not a validated_graph.json (the judge runs no evidence / necessity / graph check,
so it cannot fill those fields honestly), hence its own file name.

At the end the LLM call counts are written with cdlp.shared.llm.write_stats() to
`<out dir>/single_judge.stats.json` (or --stats), which evaluate.py reads for the cost.

The prompt file is read from prompts/<version>.txt with the same placeholders as
semantic_check.py. `semantic_v2` arrives with the semantic-v2 PR; until then, run with
`--prompt-version semantic_v1` or the CLI stops with a clear message.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cdlp.shared import llm
from cdlp.shared.io import read_json
from cdlp.validation.semantic_check import JUDGE_ACCEPT, LEVELS

SETTING = "single_judge"
PROMPT_VERSION = "semantic_v2"
PROMPT_DIR = Path(__file__).parent / "prompts"
TEMPERATURE = 0.0
SCHEMA_VERSION = "1.0"  # this file's own format (not a shared contract)


def validator_model() -> str:
    return os.getenv("LLM_VALIDATOR_MODEL", "llama3.1:8b")


def load_prompt(prompt_version: str) -> str:
    path = PROMPT_DIR / f"{prompt_version}.txt"
    if not path.is_file():
        raise SystemExit(
            f"{path} not found. semantic_v2 comes with the semantic-v2 PR; "
            "until it is merged, pass --prompt-version semantic_v1."
        )
    return path.read_text(encoding="utf-8")


def build_prompt(template: str, relationship: dict, concepts: dict) -> str:
    """Same placeholders as semantic_check.build_prompt."""
    src, tgt = concepts[relationship["source"]], concepts[relationship["target"]]
    replacements = {
        "{source_name}": src["name"],
        "{source_aliases}": ", ".join(src.get("aliases") or []) or "no aliases",
        "{source_description}": src.get("description") or "(no description)",
        "{target_name}": tgt["name"],
        "{target_aliases}": ", ".join(tgt.get("aliases") or []) or "no aliases",
        "{target_description}": tgt.get("description") or "(no description)",
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def decision_for(grade: str) -> str:
    return "ACCEPT" if grade in JUDGE_ACCEPT else "REJECT"


def judge(prompt: str, *, model: str, prompt_version: str, temperature: float, seed: int) -> dict:
    """One semantic grade. A reply that is not JSON, or has no valid grade, is `none`."""
    try:
        response = llm.chat_json(
            prompt,
            model=model,
            temperature=temperature,
            prompt_version=prompt_version,
            seed=seed,
        )
    except ValueError:  # the model returned text that is not JSON
        response = {}
    if not isinstance(response, dict):
        response = {}
    grade = str(response.get("semantic", "")).strip().lower()
    grade = grade if grade in LEVELS else "none"
    return {
        "semantic": grade,
        "rationale": str(response.get("rationale", "")).strip(),
        "decision": decision_for(grade),
    }


def edge_record(relationship: dict, decision: str, **extra) -> dict:
    return {
        "id": relationship["id"],
        "source": relationship["source"],
        "target": relationship["target"],
        "type": "PREREQUISITE",
        "strength": relationship.get("strength"),
        "decision": decision,
        **extra,
    }


def run(
    relationships: dict,
    concepts: dict,
    *,
    model: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    seed: int = llm.DEFAULT_SEED,
) -> dict:
    model = model or validator_model()
    template = load_prompt(prompt_version)
    concept_map = {c["id"]: c for c in concepts["concepts"]}
    edges = []
    for r in relationships["relationships"]:
        verdict = judge(
            build_prompt(template, r, concept_map),
            model=model,
            prompt_version=prompt_version,
            temperature=TEMPERATURE,
            seed=seed,
        )
        edges.append(
            edge_record(
                r,
                verdict["decision"],
                semantic=verdict["semantic"],
                rationale=verdict["rationale"],
            )
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": relationships["course_id"],
        "method": SETTING,
        "model": model,
        "prompt_version": prompt_version,
        "temperature": TEMPERATURE,
        "seed": seed,
        "rule": f"ACCEPT if semantic in {sorted(JUDGE_ACCEPT)}, else REJECT",
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "edges": edges,
    }


def cli(setting: str, description: str, runner: Callable[..., dict], argv=None, extra=None):
    """Shared CLI for single_judge and self_consistency (same shape)."""
    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=None, help="default: LLM_VALIDATOR_MODEL")
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--stats", type=Path, help=f"default: <out dir>/{setting}.stats.json")
    for add in extra or []:
        add(parser)
    args = parser.parse_args(argv)

    result = runner(read_json(args.relationships), read_json(args.concepts), args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    stats = llm.write_stats(args.stats or args.out.parent / f"{setting}.stats.json")
    decisions = [e["decision"] for e in result["edges"]]
    print(
        f"{setting} ({result['model']}, {result['prompt_version']}): "
        f"{decisions.count('ACCEPT')} ACCEPT, {decisions.count('REJECT')} REJECT; "
        f"{stats['llm_calls']} LLM calls, {stats['cache_hits']} cache hits -> {args.out}"
    )
    return result


def main(argv: list[str] | None = None) -> dict:
    return cli(
        SETTING,
        __doc__,
        lambda rels, concepts, args: run(
            rels, concepts, model=args.model, prompt_version=args.prompt_version
        ),
        argv,
    )


if __name__ == "__main__":
    main()
