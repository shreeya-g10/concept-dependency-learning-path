"""Unit tests for the evidence check. The LLM and the embedding model are both faked."""

from cdlp.shared.io import EXAMPLES, read_json, read_jsonl
from cdlp.validation import evidence_check
from cdlp.validation.evidence_check import ChunkIndex, gather_chunks, run, verify_quotes

VOCAB = ["recursion", "tree", "binary", "search", "avl", "graph", "balanc", "rotation"]


def fake_embed(texts):
    """Bag-of-words over a tiny vocabulary: deterministic and needs no model."""
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


def load():
    rels = read_json(EXAMPLES / "relationships.json")
    concepts = read_json(EXAMPLES / "concepts.json")
    chunks = read_jsonl(EXAMPLES / "chunks.jsonl")
    return rels, concepts, chunks


def only(rels, rel_id):
    return {**rels, "relationships": [r for r in rels["relationships"] if r["id"] == rel_id]}


def test_gather_keeps_cited_evidence_first_and_adds_retrieved():
    rels, concepts, chunks = load()
    concept_map = {c["id"]: c for c in concepts["concepts"]}
    r3 = next(r for r in rels["relationships"] if r["id"] == "r3")
    picked = gather_chunks(r3, concept_map, ChunkIndex(chunks, fake_embed), k=2)
    ids = [c["chunk_id"] for c in picked]
    assert ids[0] == "ch_l9_p04"
    assert len(ids) == len(set(ids)) and 2 <= len(ids) <= 3


def test_run_passes_validator_model_and_prompt_version(monkeypatch):
    rels, concepts, chunks = load()
    calls = []

    def fake_chat_json(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {
            "support": "strong",
            "quotes": [
                {"chunk_id": "ch_l9_p04", "quote": "a self-balancing binary search tree"},
                {"chunk_id": "ch_l9_p04", "quote": "AVL trees need graphs"},  # invented
            ],
            "rationale": "AVL is defined as a BST.",
        }

    monkeypatch.setattr(evidence_check, "chat_json", fake_chat_json)
    out = run(only(rels, "r3"), concepts, chunks, k=2, model="validator-x", embed=fake_embed)

    prompt, kwargs = calls[0]
    assert kwargs["model"] == "validator-x"
    assert kwargs["prompt_version"] == "evidence_v1"
    assert kwargs["temperature"] == 0.0
    assert "Binary Search Trees" in prompt and "AVL Trees" in prompt and "ch_l9_p04" in prompt
    assert out["model"] == "validator-x" and out["prompt_version"] == "evidence_v1"

    result = out["results"][0]
    assert result["evidence"] == "strong"
    assert result["quotes"] == [
        {
            "chunk_id": "ch_l9_p04",
            "doc": "ds_lec9.pdf",
            "page": 4,
            "quote": "a self-balancing binary search tree",
        }
    ]


def test_strong_without_verifiable_quote_is_capped_at_weak(monkeypatch):
    rels, concepts, chunks = load()
    monkeypatch.setattr(
        evidence_check,
        "chat_json",
        lambda *a, **kw: {
            "support": "strong",
            "quotes": [{"chunk_id": "ch_l9_p04", "quote": "graphs are needed for AVL"}],
        },
    )
    result = run(only(rels, "r6"), concepts, chunks, model="m", embed=fake_embed)["results"][0]
    assert result["evidence"] == "weak"
    assert result["quotes"] == []


def test_none_and_invalid_labels(monkeypatch):
    rels, concepts, chunks = load()
    for label in ["none", "very strong", None]:
        monkeypatch.setattr(
            evidence_check,
            "chat_json",
            lambda *a, label=label, **kw: {
                "support": label,
                "quotes": [{"chunk_id": "ch_l10_p01", "quote": "A graph generalises a tree"}],
            },
        )
        result = run(only(rels, "r6"), concepts, chunks, model="m", embed=fake_embed)["results"][0]
        assert result["evidence"] == "none"
        assert result["quotes"] == []


def test_verify_quotes_ignores_case_whitespace_and_unknown_chunks():
    _, _, chunks = load()
    quotes = [
        {"chunk_id": "ch_l6_p11", "quote": "Traversals  are defined\nrecursively"},
        {"chunk_id": "ch_l6_p11", "quote": "traversals are defined recursively"},  # duplicate
        {"chunk_id": "missing", "quote": "A tree"},
        "not a dict",
    ]
    verified = verify_quotes(quotes, chunks)
    assert len(verified) == 1
    assert verified[0]["doc"] == "ds_lec6.pdf" and verified[0]["page"] == 11
    assert verify_quotes(None, chunks) == []
