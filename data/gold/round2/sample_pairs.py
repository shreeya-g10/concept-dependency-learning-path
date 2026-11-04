"""Samples ds101 concept pairs for round 2 of gold labelling. Makes no LLM call.

Reads only the filtered concept list and the chunks, never relationships.json or
validated_graph.json, so the sample cannot depend on what discovery or the validator said.

Most pairs come from the candidate filter. The rest do not, so the labels can also measure
what the filter misses (candidate recall). Pairs already in the gold, and pairs in set 1, are
left out: set 1 (seed 42, in set1_ai_assisted_not_used/) was labelled with AI help, so it is
not gold and its annotator has seen AI answers for those pairs. The file for the annotator is
in send_to_annotator/. It does not say which group a pair came from, and A and B are in a
seeded random order. The key is in private_keys/, for scoring only: never send that folder.

    python data/gold/round2/sample_pairs.py <concepts.json> <chunks.jsonl>
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from cdlp.discovery.candidates import generate_candidates  # noqa: E402
from cdlp.shared.io import read_jsonl  # noqa: E402

SEED = 43
N_CANDIDATE, N_OTHER = 90, 30
GOLD_ID_TO_CONCEPT = {"trees": "general_tree", "graphs": "graph"}  # as in order_bias_ds101.json
HERE = Path(__file__).parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    concepts_path, chunks_path = Path(sys.argv[1]), Path(sys.argv[2])
    concepts = json.loads(concepts_path.read_text())["concepts"]
    by_id = {c["id"]: c for c in concepts}
    assert len(by_id) == 85, len(by_id)
    chunks = list(read_jsonl(chunks_path))
    candidates = {frozenset((c.source, c.target)) for c in generate_candidates(concepts, chunks)}
    assert len(candidates) == 1380, len(candidates)

    labelled = set()
    for name in ("annotator_a", "annotator_b", "annotator_c", "annotator_d"):
        with (ROOT / f"data/gold/annotations/{name}.csv").open(newline="") as f:
            for row in csv.DictReader(f):
                labelled.add(
                    frozenset(GOLD_ID_TO_CONCEPT.get(row[k], row[k]) for k in ("source", "target"))
                )

    with (HERE / "set1_ai_assisted_not_used/ds101_pairs_key.csv").open(newline="") as f:
        set1 = {frozenset((r["concept_a_id"], r["concept_b_id"])) for r in csv.DictReader(f)}
    assert len(set1) == 150, len(set1)
    labelled |= set1

    every = sorted(frozenset(p) for p in combinations(sorted(by_id), 2))
    every = sorted((p for p in every if p not in labelled), key=sorted)
    rng = random.Random(SEED)
    group_a = rng.sample([p for p in every if p in candidates], N_CANDIDATE)
    group_b = rng.sample([p for p in every if p not in candidates], N_OTHER)
    chosen = [(p, "candidate") for p in group_a] + [(p, "not_candidate") for p in group_b]
    rng.shuffle(chosen)

    def place(concept: dict) -> str:
        sources = concept.get("sources") or [{}]
        return f"{sources[0].get('doc', '')} p.{sources[0].get('page', '')}"

    with (
        (HERE / "send_to_annotator/ds101_set2_to_label.csv").open("w", newline="") as out,
        (HERE / "private_keys/ds101_set2_key.csv").open("w", newline="") as key,
    ):
        labels = csv.writer(out)
        scoring = csv.writer(key)
        labels.writerow(
            ["pair", "concept_a", "concept_b", "where_a", "where_b", "first", "strength", "note"]
        )
        scoring.writerow(["pair", "concept_a_id", "concept_b_id", "group"])
        for number, (pair, group) in enumerate(chosen, start=1):
            a, b = sorted(pair)
            if rng.random() < 0.5:
                a, b = b, a
            labels.writerow(
                [
                    number,
                    by_id[a]["name"],
                    by_id[b]["name"],
                    place(by_id[a]),
                    place(by_id[b]),
                    "",
                    "",
                    "",
                ]
            )
            scoring.writerow([number, a, b, group])
    (HERE / "private_keys/set2_config.json").write_text(
        json.dumps(
            {
                "set": 2,
                "seed": SEED,
                "excludes_set1_pairs": len(set1),
                "n_candidate": N_CANDIDATE,
                "n_not_candidate": N_OTHER,
                "pairs_available": len(every),
                "candidates_total": len(candidates),
                "concepts_sha256": sha(concepts_path),
                "chunks_sha256": sha(chunks_path),
                "read_validator_or_discovery_output": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "wrote", len(chosen), "pairs from", len(every), "unlabelled;", len(candidates), "candidates"
    )


if __name__ == "__main__":
    main()
