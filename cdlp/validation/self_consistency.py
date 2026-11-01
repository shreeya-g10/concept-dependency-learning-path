"""RQ1 baseline "self-consistency": the single judge sampled 3 times, majority vote.

    python -m cdlp.validation.self_consistency \
        --relationships outputs/rq1/ds101/relationships.json \
        --concepts outputs/ds101/concepts.json \
        --out outputs/rq1/ds101/validated_self_consistency.json

Per proposed edge: the single-judge prompt (default `semantic_v2`) is asked once per
seed (default 42, 43, 44) at temperature 0.7, each sample gives ACCEPT / REJECT by the
single-judge rule, and the majority decides. A tie (only possible with an even number
of seeds) REJECTs. `confidence` is the share of samples that voted for the decision.

Why it is in RQ1: it spends several calls per edge like the agent but adds no
independent evidence, so it separates "more LLM calls" from "independent checks".

Why temperature 0.7: at temperature 0 different seeds mostly return the same answer,
so the vote would be a single judge three times over. The temperature is recorded in
the output and in the cache key.

Output has the single-judge shape (`edges` with `decision`), plus every sample. At the
end the call counts are written with cdlp.shared.llm.write_stats() to
`<out dir>/self_consistency.stats.json` (or --stats).
"""

from __future__ import annotations

from datetime import datetime, timezone

from cdlp.validation.single_judge import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    build_prompt,
    cli,
    edge_record,
    judge,
    load_prompt,
    validator_model,
)

SETTING = "self_consistency"
SEEDS = (42, 43, 44)
TEMPERATURE = 0.7


def majority(decisions: list[str]) -> tuple[str, float]:
    """(decision, share of votes for it). Ties REJECT."""
    accepts = decisions.count("ACCEPT")
    rejects = len(decisions) - accepts
    decision = "ACCEPT" if accepts > rejects else "REJECT"
    votes = accepts if decision == "ACCEPT" else rejects
    return decision, round(votes / len(decisions), 4) if decisions else 0.0


def run(
    relationships: dict,
    concepts: dict,
    *,
    model: str | None = None,
    prompt_version: str = PROMPT_VERSION,
    seeds: tuple[int, ...] = SEEDS,
    temperature: float = TEMPERATURE,
) -> dict:
    if not seeds:
        raise ValueError("self-consistency needs at least one seed")
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"seeds must differ: {seeds}")
    model = model or validator_model()
    template = load_prompt(prompt_version)
    concept_map = {c["id"]: c for c in concepts["concepts"]}
    edges = []
    for r in relationships["relationships"]:
        prompt = build_prompt(template, r, concept_map)
        samples = [
            {
                "seed": seed,
                **judge(
                    prompt,
                    model=model,
                    prompt_version=prompt_version,
                    temperature=temperature,
                    seed=seed,
                ),
            }
            for seed in seeds
        ]
        decision, share = majority([s["decision"] for s in samples])
        edges.append(edge_record(r, decision, confidence=share, samples=samples))
    return {
        "schema_version": SCHEMA_VERSION,
        "course_id": relationships["course_id"],
        "method": SETTING,
        "model": model,
        "prompt_version": prompt_version,
        "temperature": temperature,
        "seeds": list(seeds),
        "rule": "majority of single-judge decisions over the seeds; a tie REJECTs",
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "edges": edges,
    }


def _add_args(parser) -> None:
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    parser.add_argument("--temperature", type=float, default=TEMPERATURE)


def main(argv: list[str] | None = None) -> dict:
    return cli(
        SETTING,
        __doc__,
        lambda rels, concepts, args: run(
            rels,
            concepts,
            model=args.model,
            prompt_version=args.prompt_version,
            seeds=tuple(args.seeds),
            temperature=args.temperature,
        ),
        argv,
        extra=[_add_args],
    )


if __name__ == "__main__":
    main()
