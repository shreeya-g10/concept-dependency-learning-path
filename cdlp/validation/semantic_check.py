"""Semantic check: does teaching A before B make pedagogical sense?

For each relationship A -> B the validator model (LLM_VALIDATOR_MODEL, a different
model from discovery) grades the order as strong / medium / weak / none with a
one-sentence rationale. It sees only the concepts' names, aliases and
descriptions, never the course chunks: grounding in the material is the evidence
check's job, so the two checks fail independently.

The same call doubles as the RQ1 "single LLM judge" baseline: on its own it
ACCEPTs an edge graded strong or medium and REJECTs the rest. The full validation
agent combines this grade with the evidence, necessity and graph checks instead.

    python -m cdlp.validation.semantic_check --relationships outputs/relationships.json \
        --concepts outputs/concepts.json --out outputs/semantic_check.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from cdlp.shared.io import read_json
from cdlp.shared.llm import DEFAULT_SEED, chat_json

load_dotenv()

# v2 grades "B is a kind / specialisation of A" as strong; v1 under-graded those
# edges (see results/README.md). v1 stays selectable with --prompt-version.
PROMPT_VERSION = "semantic_v2"
PROMPT_DIR = Path(__file__).parent / "prompts"
LEVELS = ("strong", "medium", "weak", "none")
TEMPERATURE = 0.0
# Single-judge baseline rule: these grades ACCEPT, everything else REJECTs.
JUDGE_ACCEPT = frozenset({"strong", "medium"})


def validator_model() -> str:
    return os.getenv("LLM_VALIDATOR_MODEL", "llama3.1:8b")


def prompt_file(version: str = PROMPT_VERSION) -> Path:
    return PROMPT_DIR / f"{version}.txt"


def build_prompt(relationship: dict, concepts: dict, prompt_version: str = PROMPT_VERSION) -> str:
    src, tgt = concepts[relationship["source"]], concepts[relationship["target"]]
    replacements = {
        "{source_name}": src["name"],
        "{source_aliases}": ", ".join(src.get("aliases") or []) or "no aliases",
        "{source_description}": src.get("description") or "(no description)",
        "{target_name}": tgt["name"],
        "{target_aliases}": ", ".join(tgt.get("aliases") or []) or "no aliases",
        "{target_description}": tgt.get("description") or "(no description)",
    }
    prompt = prompt_file(prompt_version).read_text()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def judge_decision(grade: str) -> str:
    return "ACCEPT" if grade in JUDGE_ACCEPT else "REJECT"


def check_relationship(
    relationship: dict, concepts: dict, *, model: str, prompt_version: str = PROMPT_VERSION
) -> dict:
    try:
        response = chat_json(
            build_prompt(relationship, concepts, prompt_version),
            model=model,
            temperature=TEMPERATURE,
            prompt_version=prompt_version,
        )
    except ValueError:  # the model returned text that is not JSON
        response = {}
    if not isinstance(response, dict):
        response = {}
    grade = str(response.get("semantic", "")).strip().lower()
    grade = grade if grade in LEVELS else "none"
    return {
        "relationship_id": relationship["id"],
        "source": relationship["source"],
        "target": relationship["target"],
        "semantic": grade,
        "rationale": str(response.get("rationale", "")).strip(),
        "judge_decision": judge_decision(grade),
    }


def run(
    relationships: dict,
    concepts: dict,
    *,
    model: str | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> dict:
    model = model or validator_model()
    concept_map = {c["id"]: c for c in concepts["concepts"]}
    return {
        "course_id": relationships["course_id"],
        "model": model,
        "prompt_version": prompt_version,
        "temperature": TEMPERATURE,
        "seed": DEFAULT_SEED,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "judge_rule": f"ACCEPT if semantic in {sorted(JUDGE_ACCEPT)}, else REJECT",
        "results": [
            check_relationship(r, concept_map, model=model, prompt_version=prompt_version)
            for r in relationships["relationships"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--concepts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default=None, help="default: LLM_VALIDATOR_MODEL")
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    args = parser.parse_args()

    result = run(
        read_json(args.relationships),
        read_json(args.concepts),
        model=args.model,
        prompt_version=args.prompt_version,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    decisions = [r["judge_decision"] for r in result["results"]]
    print(
        f"semantic check ({result['model']}): {decisions.count('ACCEPT')} ACCEPT, "
        f"{decisions.count('REJECT')} REJECT -> {args.out}"
    )


if __name__ == "__main__":
    main()
