"""LLM discovery: ask the LLM whether each candidate pair is a direct prerequisite.

Discovery only proposes edges. It never rewrites or drops an edge for graph
reasons by default: cycles, duplicates and transitive redundancy are the
validator's graph check (cdlp/validation/graph_checks.py).
"""

import hashlib
import json
from collections import Counter
from itertools import chain, zip_longest
from pathlib import Path

from cdlp.discovery.candidates import _mentions, _terms
from cdlp.shared.llm import chat_json

PROMPT_VERSION = "discover_v3_1"  # course runs: discover_v3 with a hash-chosen A and B
# Asks one fixed direction per pair. Benchmark runs (--pairs) keep it unless told otherwise, so
# RQ1 results stay comparable. discover_v1 is kept for the record; it leaked gold pairs.
DIRECTIONAL_PROMPT_VERSION = "discover_v2"
TEMPERATURE = 0.0
ORDER_RULE_PATH = Path(__file__).parent / "configs" / "order_rule_v2.json"
DIRECTION_RULE_PATH = Path(__file__).parent / "configs" / "direction_rule_v1.json"

# Versions that ask one neutral question per unordered pair (A before B, B before A or
# neither), so the direction comes from the model and not from the course file order.
NEUTRAL_PROMPT_VERSIONS = {"discover_v3", "discover_v3_1"}
# How A and B are chosen. discover_v3's text says A is the lower ID, so it keeps that order.
PAIR_ORDER_RULES = {"discover_v3": "lower_id_first", "discover_v3_1": "sha256_of_pair_v1"}
NEUTRAL_ANSWERS = {"A_BEFORE_B", "B_BEFORE_A", "NEITHER"}
# Versions that ask one YES/NO question per direction, with no A or B labels. Never the default
# until that is decided, and refused with --pairs, so benchmark prompts cannot change by accident.
DIRECTION_PROMPT_VERSIONS = {"discover_v4"}
DIRECTION_PAIR_RULE = "one_call_per_direction_v1"
# Ollama's default context is 4096 tokens; a longer prompt loses its START, which held the
# question in discover_v2 (200 of the 237 ds101 calls). These caps keep a neutral prompt
# near 8,000 characters (about 2,300 tokens at the 3.56 characters per token of that run).
MAX_EVIDENCE_CHUNKS = 4
MAX_EXCERPT_CHARS = 1200

# The prompt asks for a confidence *label*; the contract needs a number in [0, 1].
# These values are a fixed, arbitrary ordinal mapping, not calibrated probabilities.
# Unknown or missing labels get LOW. Change them only together with PROMPT_VERSION.
CONFIDENCE_SCORES = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5}
DEFAULT_CONFIDENCE = CONFIDENCE_SCORES["LOW"]


def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (Path(__file__).parent / "prompts" / f"{version}.txt").read_text()


def confidence_score(label) -> float:
    """Map the LLM's HIGH/MEDIUM/LOW label to a number; tolerate numbers and junk."""
    if isinstance(label, (int, float)) and not isinstance(label, bool) and 0 <= label <= 1:
        return float(label)
    if isinstance(label, str):
        return CONFIDENCE_SCORES.get(label.strip().upper(), DEFAULT_CONFIDENCE)
    return DEFAULT_CONFIDENCE


def _normalise_result(result, source_id: str, target_id: str, allowed_chunks: set) -> dict:
    """Turn whatever the LLM returned into one well-formed record. Malformed -> NONE."""
    if not isinstance(result, dict):
        result = {}
    relationship = str(result.get("relationship", "NONE")).strip().upper()
    strength = str(result.get("strength", "NONE")).strip().lower()
    if relationship != "DIRECT" or strength not in {"hard", "soft"}:
        relationship, strength = "NONE", "none"
    chunk_ids = result.get("evidence_chunk_ids")
    if not isinstance(chunk_ids, list):
        chunk_ids = []
    return {
        "source": source_id,  # always ours, never the LLM's
        "target": target_id,
        "relationship": relationship,
        "strength": strength,
        "confidence": confidence_score(result.get("confidence")),
        # only chunks we actually showed the LLM count as evidence
        "evidence_chunk_ids": [c for c in chunk_ids if c in allowed_chunks],
    }


def discover_relationship(
    source: dict,
    target: dict,
    evidence: list[dict],
    candidate_reasons: list[str],
    prompt_version: str = DIRECTIONAL_PROMPT_VERSION,
) -> dict:
    evidence_text = "\n".join(f"Chunk ID: {item['chunk_id']}\n{item['text']}" for item in evidence)
    prompt = load_prompt(prompt_version).format(
        source_id=source["id"],
        source_name=source["name"],
        source_description=source.get("description", ""),
        target_id=target["id"],
        target_name=target["name"],
        target_description=target.get("description", ""),
        candidate_reasons=", ".join(candidate_reasons),
        evidence=evidence_text,
    )
    try:
        result = chat_json(prompt, prompt_version=prompt_version, temperature=TEMPERATURE)
    except ValueError:  # the model returned text that is not JSON
        result = {}
    return _normalise_result(
        result, source["id"], target["id"], {item["chunk_id"] for item in evidence}
    )


def _evidence_for(source: dict, target: dict, chunk_map: dict) -> list[dict]:
    evidence = []
    for concept in (source, target):
        for source_info in concept.get("sources", []):
            chunk = chunk_map.get(source_info.get("chunk_id"))
            if chunk is not None and chunk not in evidence:
                evidence.append(chunk)
    return evidence


def _hash_order(chunk_id: str) -> str:
    """A stable order unrelated to file order, so evidence order cannot hint at direction."""
    return hashlib.sha256(chunk_id.encode()).hexdigest()


def _excerpt(text: str, terms: list[str], limit: int = MAX_EXCERPT_CHARS) -> str:
    """At most limit characters, starting just before the first mention of either concept."""
    if len(text) <= limit:
        return text
    lowered = text.lower()
    hits = [i for i in (lowered.find(term) for term in terms) if i >= 0]
    start = max(0, min(hits) - 100) if hits else 0
    return text[start : start + limit]


def select_neutral_evidence(a: dict, b: dict, chunk_map: dict) -> list[dict]:
    """A few short excerpts: chunks naming both concepts first, then A's and B's in turn."""

    def own_chunks(concept: dict) -> list[dict]:
        ids = dict.fromkeys(s.get("chunk_id") for s in concept.get("sources", []))
        return [chunk_map[i] for i in ids if i in chunk_map]

    a_terms, b_terms = _terms(a), _terms(b)

    def names_both(chunk: dict) -> bool:
        text = chunk.get("text", "")
        return any(_mentions(t, text) for t in a_terms) and any(_mentions(t, text) for t in b_terms)

    a_chunks, b_chunks = own_chunks(a), own_chunks(b)
    both = [c for c in {c["chunk_id"]: c for c in a_chunks + b_chunks}.values() if names_both(c)]
    both.sort(key=lambda c: _hash_order(c["chunk_id"]))
    turns = chain.from_iterable(zip_longest(a_chunks, b_chunks))
    picked = {c["chunk_id"]: c for c in both[:MAX_EVIDENCE_CHUNKS]}
    for chunk in turns:
        if len(picked) >= MAX_EVIDENCE_CHUNKS:
            break
        if chunk is not None:
            picked.setdefault(chunk["chunk_id"], chunk)
    terms = a_terms + b_terms
    return [
        {**chunk, "text": _excerpt(chunk.get("text", ""), terms)}
        for chunk in sorted(picked.values(), key=lambda c: _hash_order(c["chunk_id"]))
    ]


def neutral_order(x: dict, y: dict, prompt_version: str) -> tuple[dict, dict]:
    """(A, B) for a pair, the same whichever way round it arrives.

    Under the lower-ID rule, position follows the IDs, and IDs can correlate with the true
    direction (every positive ds101 gold edge has the later concept first alphabetically), so
    a model's position preference and the real answer cannot be told apart. A hash of the pair
    makes position unrelated to the concepts, and sha256 stays the same between processes,
    which Python's hash() does not.
    """
    low, high = sorted((x, y), key=lambda concept: concept["id"])
    if PAIR_ORDER_RULES[prompt_version] == "lower_id_first":
        return low, high
    digest = hashlib.sha256(f"{low['id']}\0{high['id']}".encode()).digest()
    return (high, low) if digest[0] & 1 else (low, high)


def build_neutral_prompt(x: dict, y: dict, evidence: list[dict], prompt_version: str) -> str:
    """The same text whichever way round the pair arrives: see neutral_order()."""
    a, b = neutral_order(x, y, prompt_version)
    return format_neutral_prompt(a, b, evidence, prompt_version)


def format_neutral_prompt(a: dict, b: dict, evidence: list[dict], prompt_version: str) -> str:
    """The prompt with this exact A and B. order_bias.py asks both ways through this."""
    return load_prompt(prompt_version).format(
        a_id=a["id"],
        a_name=a["name"],
        a_description=a.get("description", ""),
        b_id=b["id"],
        b_name=b["name"],
        b_description=b.get("description", ""),
        evidence="\n".join(f"Chunk ID: {i['chunk_id']}\n{i['text']}" for i in evidence),
    )


def _names_concept(value, concept: dict) -> bool:
    """Did the model name this concept? Tolerates case and _ - or space between words."""

    def norm(text) -> str:
        return " ".join(str(text).lower().replace("_", " ").replace("-", " ").split())

    names = (concept["id"], concept["name"], *(concept.get("aliases") or []))
    return norm(value) in {norm(name) for name in names}


def _normalise_neutral_result(result, a: dict, b: dict, allowed_chunks: set) -> dict:
    """Turn the reply into one record. Off-topic or malformed replies count as NEITHER."""
    if not isinstance(result, dict):
        result = {}
    answer = str(result.get("answer", "NEITHER")).strip().upper().replace(" ", "_")
    strength = str(result.get("strength", "NONE")).strip().lower()
    on_topic = _names_concept(result.get("a"), a) and _names_concept(result.get("b"), b)
    source, target = (b, a) if answer == "B_BEFORE_A" else (a, b)
    direct = on_topic and answer in {"A_BEFORE_B", "B_BEFORE_A"} and strength in {"hard", "soft"}
    chunk_ids = result.get("evidence_chunk_ids")
    return {
        "source": source["id"],  # always ours, never the LLM's
        "target": target["id"],
        "relationship": "DIRECT" if direct else "NONE",
        "strength": strength if direct else "none",
        "confidence": confidence_score(result.get("confidence")),
        "evidence_chunk_ids": [
            c for c in (chunk_ids if isinstance(chunk_ids, list) else []) if c in allowed_chunks
        ],
        "answer": answer if answer in NEUTRAL_ANSWERS and direct else "NEITHER",
        "on_topic": on_topic,
        "pair_a": a["id"],
        "pair_b": b["id"],
    }


def _ask_neutral(a: dict, b: dict, evidence: list[dict], prompt_version: str) -> dict:
    """One question with this exact A and B."""
    prompt = format_neutral_prompt(a, b, evidence, prompt_version)
    try:
        result = chat_json(prompt, prompt_version=prompt_version, temperature=TEMPERATURE)
    except ValueError:  # the model returned text that is not JSON
        result = {}
    return _normalise_neutral_result(result, a, b, {item["chunk_id"] for item in evidence})


def discover_pair_neutral(
    x: dict, y: dict, chunk_map: dict, prompt_version: str = PROMPT_VERSION
) -> dict:
    a, b = neutral_order(x, y, prompt_version)
    # Chosen by ID, not by A and B, so a pair gets the same evidence under every order rule
    # and a change in the answers can only come from the order.
    evidence = select_neutral_evidence(*sorted((x, y), key=lambda c: c["id"]), chunk_map)
    return _ask_neutral(a, b, evidence, prompt_version)


def load_direction_rule(path: Path | str = DIRECTION_RULE_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_order_rule(path: Path | str = ORDER_RULE_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_order_rule(first: dict, second: dict) -> tuple[str, list[dict]]:
    """(order_agreement, the links to propose) from the two asks of one pair, first = hash order.

    The rule is fixed in configs/order_rule_v1.json. It never picks a direction when the
    two orders disagree.
    """
    links = [r for r in (first, second) if r["answer"] != "NEITHER"]
    if not links:
        return "neither", []
    if len(links) == 1:
        return "unstable", links
    if (first["source"], first["target"]) == (second["source"], second["target"]):
        cited = dict.fromkeys(first["evidence_chunk_ids"] + second["evidence_chunk_ids"])
        return "stable", [{**first, "evidence_chunk_ids": list(cited)}]
    return "reversed", links


def discover_pair_both_orders(
    x: dict, y: dict, chunk_map: dict, prompt_version: str = PROMPT_VERSION
) -> list[dict]:
    """One record per proposed link (or one NONE record), each carrying both raw answers."""
    a, b = neutral_order(x, y, prompt_version)
    evidence = select_neutral_evidence(*sorted((x, y), key=lambda c: c["id"]), chunk_map)
    first = _ask_neutral(a, b, evidence, prompt_version)  # the same ask as a one-order run
    second = _ask_neutral(b, a, evidence, prompt_version)
    agreement, links = apply_order_rule(first, second)
    asks = [first, second]
    if not links:
        return [{**first, "order_agreement": agreement, "pair_asks": asks}]
    return [{**link, "order_agreement": agreement, "pair_asks": asks} for link in links]


def format_direction_prompt(
    needed: dict, topic: dict, evidence: list[dict], prompt_version: str
) -> str:
    """Does a student need `needed` to understand `topic`? Only the names and order change."""
    return load_prompt(prompt_version).format(
        needed_name=needed["name"],
        needed_description=needed.get("description", ""),
        topic_name=topic["name"],
        topic_description=topic.get("description", ""),
        evidence="\n".join(f"Chunk ID: {i['chunk_id']}\n{i['text']}" for i in evidence),
    )


def _normalise_direction_result(result, needed: dict, topic: dict, allowed_chunks: set) -> dict:
    """One record per direction. Anything but a clean YES or NO counts as NO, marked invalid."""
    if not isinstance(result, dict):
        result = {}
    raw_answer = result.get("answer")
    answer = str(raw_answer if raw_answer is not None else "").strip().upper()
    strength = str(result.get("strength", "NONE")).strip().lower()
    on_topic = _names_concept(result.get("needed"), needed) and _names_concept(
        result.get("topic"), topic
    )
    yes = on_topic and answer == "YES" and strength in {"hard", "soft"}
    chunk_ids = result.get("evidence_chunk_ids")
    return {
        "source": needed["id"],  # always ours, never the LLM's
        "target": topic["id"],
        "relationship": "DIRECT" if yes else "NONE",
        "strength": strength if yes else "none",
        "confidence": DEFAULT_CONFIDENCE,  # not asked: see configs/direction_rule_v1.json
        "evidence_chunk_ids": [
            c for c in (chunk_ids if isinstance(chunk_ids, list) else []) if c in allowed_chunks
        ],
        "answer": "YES" if yes else "NO",
        "raw_answer": "" if raw_answer is None else str(raw_answer),
        "valid": yes or (on_topic and answer == "NO"),
        "on_topic": on_topic,
    }


def _ask_direction(needed: dict, topic: dict, evidence: list[dict], prompt_version: str) -> dict:
    prompt = format_direction_prompt(needed, topic, evidence, prompt_version)
    try:
        result = chat_json(prompt, prompt_version=prompt_version, temperature=TEMPERATURE)
    except ValueError:  # the model returned text that is not JSON
        result = {}
    return _normalise_direction_result(result, needed, topic, {i["chunk_id"] for i in evidence})


def apply_direction_rule(first: dict, second: dict) -> tuple[str, list[dict]]:
    """(direction_agreement, the links to propose). Rule: configs/direction_rule_v1.json."""
    links = [r for r in (first, second) if r["answer"] == "YES"]
    return {0: "none", 1: "one_way", 2: "both_yes"}[len(links)], links


def discover_pair_directions(x: dict, y: dict, chunk_map: dict, prompt_version: str) -> list[dict]:
    """One record per proposed link (or one NONE record), each carrying both raw answers."""
    low, high = sorted((x, y), key=lambda concept: concept["id"])
    evidence = select_neutral_evidence(low, high, chunk_map)
    asks = [
        _ask_direction(low, high, evidence, prompt_version),
        _ask_direction(high, low, evidence, prompt_version),
    ]
    agreement, links = apply_direction_rule(*asks)
    extra = {"direction_agreement": agreement, "direction_asks": asks}
    return [{**link, **extra} for link in links] or [{**asks[0], **extra}]


def direction_answers(relationships: list[dict]) -> list[dict]:
    """Both raw answers per pair and direction, from a one-call-per-direction run."""
    rows = {}
    for r in relationships:
        if "direction_asks" in r:
            first = r["direction_asks"][0]
            rows.setdefault(
                (first["source"], first["target"]),
                {
                    "direction_agreement": r["direction_agreement"],
                    "asks": [
                        {
                            "needed": ask["source"],
                            "topic": ask["target"],
                            **{
                                k: ask[k]
                                for k in (
                                    "answer",
                                    "raw_answer",
                                    "valid",
                                    "on_topic",
                                    "strength",
                                    "evidence_chunk_ids",
                                )
                            },
                        }
                        for ask in r["direction_asks"]
                    ],
                },
            )
    return list(rows.values())


def direction_summary(answers: list[dict]) -> dict:
    """Printed and saved, so a bad run or a model that favours YES shows up early."""
    asks = [ask for row in answers for ask in row["asks"]]
    return {
        "YES": sum(a["answer"] == "YES" for a in asks),
        "NO": sum(a["answer"] == "NO" for a in asks),
        "invalid": sum(not a["valid"] for a in asks),
        "off_topic": sum(not a["on_topic"] for a in asks),
        "hard": sum(a["strength"] == "hard" for a in asks),
        "soft": sum(a["strength"] == "soft" for a in asks),
    }


def pair_answers(relationships: list[dict]) -> list[dict]:
    """Both raw answers per pair (asks[0] is the hash order), from a both-orders run."""
    rows = {}
    for r in relationships:
        if "pair_asks" in r:
            key = frozenset((r["pair_a"], r["pair_b"]))
            rows.setdefault(key, {"order_agreement": r["order_agreement"], "asks": r["pair_asks"]})
    return list(rows.values())


def single_order_relationships(answers: list[dict]) -> list[dict]:
    """What a one-order run would have recorded, from the same both-orders run."""
    return [row["asks"][0] for row in answers]


def neutral_summary(relationships: list[dict]) -> dict:
    """What a neutral run answered. Printed so a bad run shows up before anyone uses it."""
    answers = Counter(r.get("answer") for r in relationships)
    direct = [r for r in relationships if r["relationship"] == "DIRECT"]
    return {
        "A_BEFORE_B": answers["A_BEFORE_B"],
        "B_BEFORE_A": answers["B_BEFORE_A"],
        "NEITHER": answers["NEITHER"],
        "off_topic": sum(not r.get("on_topic") for r in relationships),
        "hard": sum(r["strength"] == "hard" for r in direct),
        "soft": sum(r["strength"] == "soft" for r in direct),
        "confidence": dict(sorted(Counter(r["confidence"] for r in direct).items())),
    }


def _merge_both_directions(forward: dict, backward: dict) -> dict:
    """A tied pair was asked both ways. Keep ONE record, never two opposite edges."""
    forward_direct = forward["relationship"] == "DIRECT"
    backward_direct = backward["relationship"] == "DIRECT"
    if forward_direct and backward_direct:
        # the stronger-confidence direction is kept; ties keep the alphabetical one
        kept, other = (
            (backward, forward)
            if backward["confidence"] > forward["confidence"]
            else (
                forward,
                backward,
            )
        )
        return {
            **kept,
            "bidirectional": True,
            "reverse_strength": other["strength"],
            "reverse_confidence": other["confidence"],
        }
    return backward if backward_direct else forward


def transitive_edges(relationships: list[dict]) -> set:
    """DIRECT edges implied by a longer path of other DIRECT edges (any length).

    Pure Python (CI has no networkx). An edge u -> v is redundant if v is still
    reachable from u without that edge. Only used behind --remove-transitive.
    """
    edges = {(r["source"], r["target"]) for r in relationships if r.get("relationship") == "DIRECT"}
    successors: dict[str, set] = {}
    for u, v in edges:
        successors.setdefault(u, set()).add(v)

    def reachable_without(u: str, v: str) -> bool:
        stack, seen = [w for w in successors.get(u, ()) if w != v], set()
        while stack:
            node = stack.pop()
            if node == v:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(successors.get(node, ()))
        return False

    if any(reachable_without(v, u) or (v, u) in edges for u, v in edges):
        return set()  # cyclic: redundancy is undefined; leave it to the validator
    return {(u, v) for u, v in edges if reachable_without(u, v)}


def discover_candidates(
    candidates: list,
    concepts: list[dict],
    chunks: list[dict],
    remove_transitive: bool = False,
    prompt_version: str = PROMPT_VERSION,
    both_orders: bool = False,
) -> list[dict]:
    concept_map = {concept["id"]: concept for concept in concepts}
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}

    relationships = []
    if prompt_version in DIRECTION_PROMPT_VERSIONS:
        for pair in dict.fromkeys(frozenset((c.source, c.target)) for c in candidates):
            x, y = sorted(pair)
            relationships += discover_pair_directions(
                concept_map[x], concept_map[y], chunk_map, prompt_version
            )
    elif prompt_version in NEUTRAL_PROMPT_VERSIONS:
        # one question per unordered pair; the candidate's direction and reasons are not used
        for pair in dict.fromkeys(frozenset((c.source, c.target)) for c in candidates):
            x, y = sorted(pair)
            if both_orders:
                relationships += discover_pair_both_orders(
                    concept_map[x], concept_map[y], chunk_map, prompt_version
                )
                continue
            relationships.append(
                discover_pair_neutral(concept_map[x], concept_map[y], chunk_map, prompt_version)
            )
    else:
        for candidate in candidates:
            source = concept_map[candidate.source]
            target = concept_map[candidate.target]
            evidence = _evidence_for(source, target, chunk_map)
            forward = discover_relationship(
                source, target, evidence, candidate.reasons, prompt_version
            )
            if getattr(candidate, "tied", False):
                backward = discover_relationship(
                    target, source, evidence, candidate.reasons, prompt_version
                )
                forward = _merge_both_directions(forward, backward)
            relationships.append(forward)

    if remove_transitive:
        # opt-in only: redundant edges are left out of the output; no record is rewritten
        redundant = transitive_edges(relationships)
        relationships = [r for r in relationships if (r["source"], r["target"]) not in redundant]
    return relationships


def build_contract_relationships(
    relationships: list[dict],
    concepts: list[dict],
    chunks: list[dict],
    prompt_version: str = PROMPT_VERSION,
) -> list[dict]:
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    contract = []
    for relationship in relationships:
        if relationship.get("relationship") != "DIRECT":
            continue
        strength = str(relationship.get("strength", "")).lower()
        if strength not in {"hard", "soft"}:
            continue

        evidence = []
        for chunk_id in relationship.get("evidence_chunk_ids", []):
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            item = {"chunk_id": chunk_id, "quote": chunk.get("text", "")[:200]}
            if chunk.get("doc"):
                item["doc"] = chunk["doc"]
            if isinstance(chunk.get("page"), int) and chunk["page"] >= 1:
                item["page"] = chunk["page"]  # schema: page >= 1, so never write a fake 0
            evidence.append(item)

        edge = {
            "id": f"r{len(contract) + 1}",
            "source": relationship["source"],
            "target": relationship["target"],
            "type": "PREREQUISITE",
            "strength": strength,
            "confidence": confidence_score(relationship.get("confidence")),
            "evidence": evidence,
            "method": f"llm_{prompt_version}",
        }
        if relationship.get("bidirectional"):
            edge["bidirectional"] = True
            edge["reverse_strength"] = relationship["reverse_strength"]
            edge["reverse_confidence"] = relationship["reverse_confidence"]
        if "pair_a" in relationship:  # which concept was A, so a position bias can be measured
            edge["pair_order"] = {
                "a": relationship["pair_a"],
                "b": relationship["pair_b"],
                "rule": PAIR_ORDER_RULES[prompt_version],
                "answer": relationship["answer"],
            }
        if relationship.get("order_agreement"):
            edge["order_agreement"] = relationship["order_agreement"]
        if relationship.get("direction_agreement"):
            edge["direction_agreement"] = relationship["direction_agreement"]
        contract.append(edge)
    return contract
