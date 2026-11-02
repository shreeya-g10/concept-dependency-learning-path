"""Pick the edges a demo validates, by a written rule. Only ever keeps proposed edges.

Each proposed edge gets one tier, and slots are filled in this order:

1. chain: a forward step between neighbours of the config's "chain".
2. likely_wrong (up to "likely_wrong_slots"): runs backwards along the chain, skips a
   concept of the chain, or joins a family pair the config lists as unlikely. Backwards
   edges come first, then shortcuts, then family pairs; within a signal, edges touching
   the tree family, then the lowest discovery confidence, then id.
3. tree_family: both ends in the "tree" family.
4. other: everything else, highest discovery confidence first, then id.

Tier 2 is filled before tier 3 so that tree edges can't use up the slots kept for showing
rejections. A chain link the LLM did not propose is reported as missing, never added.
The rule reads no gold labels and no validator output, and the result is deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

SIGNAL_ORDER = ("reverses_chain", "chain_shortcut", "unlikely_family_pair")


def load_rule(path: Path | str) -> dict:
    return json.loads(Path(path).read_text())


def _signals(edge: dict, rule: dict, family_of: dict) -> list[str]:
    source, target = edge["source"], edge["target"]
    chain = rule["chain"]
    signals = []
    if source in chain and target in chain:
        step = chain.index(target) - chain.index(source)
        if step < 0:
            signals.append("reverses_chain")
        elif step > 1:
            signals.append("chain_shortcut")
    pair = [family_of.get(source), family_of.get(target)]
    if pair in rule["likely_wrong_family_pairs"]:
        signals.append("unlikely_family_pair")
    return signals


def select(relationships: dict, n: int, rule: dict) -> tuple[dict, dict, dict]:
    """Returns (relationships with only the chosen edges, contract 'subset', full record)."""
    rels = relationships["relationships"]
    family_of = {c: fam for fam, members in rule["families"].items() for c in members}
    tree = set(rule["families"]["tree"])
    chain = rule["chain"]
    links = list(zip(chain, chain[1:], strict=False))
    proposed = {(r["source"], r["target"]) for r in rels}

    def number(rel: dict) -> tuple:
        digits = "".join(ch for ch in rel["id"] if ch.isdigit())
        return (int(digits) if digits else 0, rel["id"])

    def confidence(rel: dict) -> float:
        return float(rel.get("confidence") or 0)

    chain_tier, wrong, family, other = [], [], [], []
    signals_of: dict[str, list[str]] = {}
    for rel in rels:
        signals = _signals(rel, rule, family_of)
        signals_of[rel["id"]] = signals
        if (rel["source"], rel["target"]) in links:
            chain_tier.append(rel)
        elif signals:
            wrong.append(rel)
        elif rel["source"] in tree and rel["target"] in tree:
            family.append(rel)
        else:
            other.append(rel)

    wrong.sort(
        key=lambda r: (
            min(SIGNAL_ORDER.index(s) for s in signals_of[r["id"]]),
            not ({r["source"], r["target"]} & tree),
            confidence(r),
            number(r),
        )
    )
    family.sort(key=lambda r: (-confidence(r), number(r)))
    other.sort(key=lambda r: (-confidence(r), number(r)))

    tiers: dict[str, str] = {}

    def take(edges: list[dict], tier: str, limit: int | None = None) -> None:
        room = n - len(tiers)
        for rel in edges[: room if limit is None else min(room, limit)]:
            tiers.setdefault(rel["id"], tier)

    take(chain_tier, "chain")
    take(wrong, "likely_wrong", rule["likely_wrong_slots"])
    take(family, "tree_family")
    take(other, "other")
    take(wrong, "likely_wrong")  # only if nothing else was left to fill the slots

    kept = [r for r in rels if r["id"] in tiers]
    subset = {"kind": "demo", "n": len(kept), "of": len(rels), "selection": rule["selection"]}
    record = {
        "rule_id": rule["rule_id"],
        "rule": rule,
        "tier_order": ["chain", "likely_wrong", "tree_family", "other"],
        "n_requested": n,
        "n_selected": len(kept),
        "n_proposed": len(rels),
        "missing_chain_links": [
            {"source": a, "target": b} for a, b in links if (a, b) not in proposed
        ],
        "selected": [
            {
                "id": r["id"],
                "source": r["source"],
                "target": r["target"],
                "strength": r.get("strength"),
                "confidence": r.get("confidence"),
                "tier": tiers[r["id"]],
                "signals": signals_of[r["id"]],
            }
            for r in kept
        ],
    }
    return {**relationships, "relationships": kept}, subset, record
