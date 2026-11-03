"""discover_v3 with the LLM mocked: neutral question, direction from the answer, small prompt."""

import json
import os
import re
import subprocess
import sys
from itertools import combinations

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.discovery import candidates, llm_discovery
from cdlp.discovery.candidates import Candidate
from cdlp.shared import llm
from cdlp.shared.validate import check_file

V3 = "discover_v3"
V31 = "discover_v3_1"
EX = "cdlp/shared/examples"


def concept(cid, description="", sources=()):
    return {
        "id": cid,
        "name": cid.replace("_", " ").title(),
        "description": description,
        "sources": [{"chunk_id": s} for s in sources],
    }


# file order says zebra first, but the IDs sort apple first
ZEBRA = concept("zebra", sources=["c1"])
APPLE = concept("apple", sources=["c2"])
CONCEPTS = [ZEBRA, APPLE]
CHUNKS = [
    {"chunk_id": "c1", "doc": "x.pdf", "page": 1, "text": "zebra text"},
    {"chunk_id": "c2", "doc": "x.pdf", "page": 2, "text": "apple text"},
]


def reply(answer="A_BEFORE_B", strength="SOFT", a="apple", b="zebra", conf="MEDIUM", cited=("c1",)):
    return {
        "a": a,
        "b": b,
        "answer": answer,
        "strength": strength,
        "confidence": conf,
        "evidence_chunk_ids": list(cited),
    }


@pytest.fixture
def llm_mock(monkeypatch):
    """Records every prompt; returns whatever the test put in .answer."""

    class Mock:
        prompts: list = []
        answer = reply()

    mock = Mock()
    mock.prompts = []

    def fake(prompt, **kwargs):
        assert kwargs["prompt_version"] in (V3, V31)
        mock.prompts.append(prompt)
        return mock.answer

    monkeypatch.setattr(llm_discovery, "chat_json", fake)
    return mock


def run(candidate_list, concepts=CONCEPTS, chunks=CHUNKS):
    return llm_discovery.discover_candidates(candidate_list, concepts, chunks, prompt_version=V3)


def test_the_answer_sets_the_direction_not_the_candidate(llm_mock):
    # the candidate says zebra -> apple (file order); the model says A (apple) first
    (record,) = run([Candidate("zebra", "apple", ["course_order"])])
    assert (record["source"], record["target"]) == ("apple", "zebra")

    llm_mock.answer = reply("B_BEFORE_A")
    (record,) = run([Candidate("zebra", "apple", ["course_order"])])
    assert (record["source"], record["target"]) == ("zebra", "apple")


def test_prompt_is_identical_whichever_way_the_candidate_points(llm_mock):
    run([Candidate("zebra", "apple", ["course_order"])])
    run([Candidate("apple", "zebra", ["same_chunk"])])
    assert llm_mock.prompts[0] == llm_mock.prompts[1]


def test_prompt_orders_concepts_by_id_and_drops_order_hints(llm_mock):
    run([Candidate("zebra", "apple", ["course_order"])])
    prompt = llm_mock.prompts[0]
    assert prompt.index("ID: apple") < prompt.index("ID: zebra")
    assert "course_order" not in prompt
    assert "SOURCE" not in prompt and "TARGET" not in prompt


def test_one_call_per_unordered_pair_even_if_tied_or_listed_twice(llm_mock):
    run(
        [
            Candidate("zebra", "apple", ["same_chunk"], tied=True),
            Candidate("apple", "zebra", ["same_chunk"]),
        ]
    )
    assert len(llm_mock.prompts) == 1


def test_question_comes_after_the_evidence(llm_mock):
    """An over-long prompt loses its start, so the pair and the question must be at the end."""
    run([Candidate("zebra", "apple", [])])
    prompt = llm_mock.prompts[0]
    assert prompt.index("COURSE EVIDENCE:") < prompt.index("ID: apple") < prompt.index("QUESTION")


@pytest.mark.parametrize(
    "bad",
    [
        reply(a="Red-Black Tree", b="AVL Tree"),  # what discover_v2 got back from truncated prompts
        reply(a="zebra", b="apple"),  # A and B swapped: the direction would flip
        {"answer": "A_BEFORE_B", "strength": "HARD", "confidence": "HIGH"},  # did not say
    ],
)
def test_answer_about_other_concepts_is_not_an_edge(llm_mock, bad):
    llm_mock.answer = bad
    (record,) = run([Candidate("zebra", "apple", [])])
    assert record["relationship"] == "NONE"
    assert record["on_topic"] is False
    assert llm_discovery.build_contract_relationships([record], CONCEPTS, CHUNKS, V3) == []


@pytest.mark.parametrize(
    "bad",
    [
        reply("MAYBE"),
        reply("A_BEFORE_B", strength="NONE"),
        reply("NEITHER", strength="HARD"),
        "not a dict",
        {},
    ],
)
def test_malformed_replies_become_neither(llm_mock, bad):
    llm_mock.answer = bad
    (record,) = run([Candidate("zebra", "apple", [])])
    assert record["relationship"] == "NONE"
    assert record["answer"] == "NEITHER"


def test_echoing_the_name_or_alias_is_on_topic(llm_mock):
    llm_mock.answer = reply(a="APPLE", b="Zebra")
    (record,) = run([Candidate("zebra", "apple", [])])
    assert record["on_topic"] is True and record["relationship"] == "DIRECT"


def test_strength_confidence_and_evidence_come_through(llm_mock):
    llm_mock.answer = reply("B_BEFORE_A", "SOFT", conf="LOW", cited=("c1", "invented"))
    records = run([Candidate("zebra", "apple", [])])
    (edge,) = llm_discovery.build_contract_relationships(records, CONCEPTS, CHUNKS, V3)
    assert edge["strength"] == "soft"
    assert edge["confidence"] == llm_discovery.CONFIDENCE_SCORES["LOW"]
    assert [e["chunk_id"] for e in edge["evidence"]] == ["c1"]
    assert edge["method"] == "llm_discover_v3"


def test_summary_counts_answers_and_off_topic(llm_mock):
    records = run([Candidate("zebra", "apple", [])])
    llm_mock.answer = reply(a="other", b="thing")
    records += run([Candidate("zebra", "apple", [])])
    summary = llm_discovery.neutral_summary(records)
    assert summary["A_BEFORE_B"] == 1 and summary["NEITHER"] == 1 and summary["off_topic"] == 1
    assert summary["soft"] == 1 and summary["hard"] == 0


def test_template_is_balanced_and_from_another_domain():
    template = llm_discovery.load_prompt(V3).lower()
    for word in ("tree", "stack", "queue", "heap", "graph", "recursion", "gradient", "matrix"):
        assert not re.search(rf"\b{word}", template), word
    examples = re.findall(r"answer: (\w+), (\w+), (\w+)\.", template)
    assert len(examples) == 6
    answers = [a for a, _, _ in examples]
    assert answers.count("a_before_b") == answers.count("b_before_a") == 2
    assert answers.count("neither") == 2
    assert {s for _, s, _ in examples} == {"hard", "soft", "none"}
    assert {c for _, _, c in examples} == {"high", "medium", "low"}


def many_chunks(prefix, count):
    return [
        {"chunk_id": f"{prefix}{i}", "doc": "x.pdf", "page": 1, "text": f"{prefix} " + "w " * 1500}
        for i in range(count)
    ]


def test_prompt_stays_well_under_the_context_window(llm_mock):
    """ds101's worst discover_v2 prompt was 58,961 characters from 41 chunks."""
    chunks = many_chunks("a", 30) + many_chunks("b", 30)
    a = concept("aa", "d" * 243, [c["chunk_id"] for c in chunks[:30]])
    b = concept("bb", "d" * 243, [c["chunk_id"] for c in chunks[30:]])
    run([Candidate("aa", "bb", [])], [a, b], chunks)
    assert len(llm_mock.prompts[0]) < 9000
    assert llm_mock.prompts[0].count("Chunk ID: ") == llm_discovery.MAX_EVIDENCE_CHUNKS


def test_evidence_prefers_chunks_naming_both_then_alternates():
    only_a = [{"chunk_id": f"a{i}", "text": "apple only"} for i in range(5)]
    only_b = [{"chunk_id": f"b{i}", "text": "zebra only"} for i in range(5)]
    both = {"chunk_id": "both", "text": "a zebra eats an apple"}
    chunks = [*only_a, *only_b, both]
    a = concept("apple", sources=[c["chunk_id"] for c in [*only_a, both]])
    b = concept("zebra", sources=[c["chunk_id"] for c in only_b])
    picked = {
        c["chunk_id"]
        for c in llm_discovery.select_neutral_evidence(a, b, {c["chunk_id"]: c for c in chunks})
    }
    assert "both" in picked
    assert any(i.startswith("a") for i in picked) and any(i.startswith("b") for i in picked)


def test_excerpt_keeps_the_mention_when_it_cuts():
    text = "x " * 2000 + "binary tree " + "y " * 2000
    excerpt = llm_discovery._excerpt(text, ["binary tree"], 500)
    assert len(excerpt) == 500 and "binary tree" in excerpt


def test_cli_v3_output_matches_contract(tmp_path, monkeypatch, capsys):
    def no_llm(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", no_llm)
    monkeypatch.setattr(llm, "chat_json", no_llm)
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())

    def echo(prompt, **kwargs):
        a, b = re.findall(r"^ID: (\S+)$", prompt, re.M)[-2:]
        return {"a": a, "b": b, "answer": "B_BEFORE_A", "strength": "SOFT", "confidence": "LOW"}

    monkeypatch.setattr(llm_discovery, "chat_json", echo)
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(tmp_path), "--prompt-version", V3, "--one-order"],
        ]
    )
    assert check_file(tmp_path / "relationships.json") == []
    err = capsys.readouterr().err
    assert "one neutral question each" in err and "discover_v3 answers:" in err


def test_v3_1_is_the_default_and_older_prompts_are_kept():
    assert llm_discovery.PROMPT_VERSION == V31
    assert "SOURCE CONCEPT" in llm_discovery.load_prompt("discover_v2")
    assert "ordered alphabetically by ID" in llm_discovery.load_prompt(V3)


# ---- the order of A and B ---------------------------------------------------------


def run_v31(candidate_list, concepts=CONCEPTS, chunks=CHUNKS):
    return llm_discovery.discover_candidates(candidate_list, concepts, chunks, prompt_version=V31)


def pair_needing_swap() -> tuple[dict, dict]:
    """Two concepts the hash puts higher ID first, so A is not the lower ID."""
    for i in range(100):
        low, high = concept(f"c{i:03}"), concept(f"d{i:03}")
        if llm_discovery.neutral_order(low, high, V31)[0] is high:
            return low, high
    raise AssertionError("no swapped pair found")


def test_v3_1_prompt_differs_from_v3_in_only_the_order_sentence():
    old = llm_discovery.load_prompt(V3).splitlines()
    new = llm_discovery.load_prompt(V31).splitlines()
    assert len(old) == len(new)
    changed = [(a, b) for a, b in zip(old, new, strict=True) if a != b]
    assert len(changed) == 1
    assert "alphabetically" in changed[0][0] and "alphabetically" not in changed[0][1]


def test_hash_order_does_not_depend_on_how_the_pair_arrives():
    a, b = concept("apple"), concept("zebra")
    assert llm_discovery.neutral_order(a, b, V31) == llm_discovery.neutral_order(b, a, V31)


def test_hash_order_is_the_same_in_a_new_process_with_another_hash_seed():
    """Python's own hash() changes per process, which would change every prompt and cache key."""
    code = (
        "from cdlp.discovery.llm_discovery import neutral_order as n\n"
        "pairs = [({'id': f'a{i}'}, {'id': f'b{i}'}) for i in range(50)]\n"
        "print([n(x, y, 'discover_v3_1')[0]['id'] for x, y in pairs])"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2")
    }
    assert len(outputs) == 1


def test_hash_order_splits_pairs_about_evenly():
    """A fair coin gives 150 +/- about 26 (3 standard deviations) in 300 pairs."""
    ids = [f"concept_{i}" for i in range(25)]
    pairs = [(concept(x), concept(y)) for x, y in combinations(ids, 2)][:300]
    first_is_lower = sum(
        llm_discovery.neutral_order(x, y, V31)[0] is min((x, y), key=lambda c: c["id"])
        for x, y in pairs
    )
    assert 124 <= first_is_lower <= 176


def test_v3_keeps_the_lower_id_first():
    a, b = concept("zebra"), concept("apple")
    assert [c["id"] for c in llm_discovery.neutral_order(a, b, V3)] == ["apple", "zebra"]


def test_direction_follows_the_answer_when_a_is_the_higher_id(llm_mock):
    low, high = pair_needing_swap()
    llm_mock.answer = reply("A_BEFORE_B", a=high["id"], b=low["id"])
    (record,) = run_v31([Candidate(low["id"], high["id"], [])], [low, high], [])
    assert (record["source"], record["target"]) == (high["id"], low["id"])
    assert (record["pair_a"], record["pair_b"]) == (high["id"], low["id"])

    llm_mock.answer = reply("B_BEFORE_A", a=high["id"], b=low["id"])
    (record,) = run_v31([Candidate(low["id"], high["id"], [])], [low, high], [])
    assert (record["source"], record["target"]) == (low["id"], high["id"])
    prompt = llm_mock.prompts[-1]
    assert prompt.index(f"ID: {high['id']}") < prompt.index(f"ID: {low['id']}")


def test_order_rule_does_not_change_the_evidence(llm_mock):
    """Evidence is chosen by ID, so comparing v3 with v3_1 tests the order and nothing else."""
    low, high = pair_needing_swap()
    chunks = many_chunks("a", 5) + many_chunks("b", 5)
    low["sources"] = [{"chunk_id": c["chunk_id"]} for c in chunks[:5]]
    high["sources"] = [{"chunk_id": c["chunk_id"]} for c in chunks[5:]]
    candidate = Candidate(low["id"], high["id"], [])
    llm_discovery.discover_candidates([candidate], [low, high], chunks, prompt_version=V3)
    run_v31([candidate], [low, high], chunks)
    v3_prompt, v31_prompt = llm_mock.prompts
    assert re.findall(r"Chunk ID: (\S+)", v3_prompt) == re.findall(r"Chunk ID: (\S+)", v31_prompt)


def test_edges_record_which_concept_was_a(llm_mock):
    low, high = pair_needing_swap()
    llm_mock.answer = reply("B_BEFORE_A", a=high["id"], b=low["id"])
    records = run_v31([Candidate(low["id"], high["id"], [])], [low, high], [])
    (edge,) = llm_discovery.build_contract_relationships(records, [low, high], [], V31)
    assert edge["method"] == "llm_discover_v3_1"
    assert edge["pair_order"] == {
        "a": high["id"],
        "b": low["id"],
        "rule": "sha256_of_pair_v1",
        "answer": "B_BEFORE_A",
    }


def test_cli_default_is_v3_1_and_the_file_records_the_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(candidates, "_embedding_pairs", lambda concepts, threshold=0.55: set())

    def echo(prompt, **kwargs):
        assert kwargs["prompt_version"] == V31
        a, b = re.findall(r"^ID: (\S+)$", prompt, re.M)[-2:]
        return {"a": a, "b": b, "answer": "A_BEFORE_B", "strength": "SOFT", "confidence": "LOW"}

    monkeypatch.setattr(llm_discovery, "chat_json", echo)
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--chunks", f"{EX}/chunks.jsonl"],
            *["--out-dir", str(tmp_path), "--one-order"],
        ]
    )
    assert check_file(tmp_path / "relationships.json") == []
    output = json.loads((tmp_path / "relationships.json").read_text())
    assert output["discovery"]["prompt_version"] == V31
    assert output["discovery"]["pair_order_rule"] == "sha256_of_pair_v1"
    # the counts cover every answer, including those that leave no edge
    assert output["discovery"]["answers"]["A_BEFORE_B"] == len(output["relationships"])
    assert {e["pair_order"]["rule"] for e in output["relationships"]} == {"sha256_of_pair_v1"}


def test_pairs_both_directions_keeps_v2_by_default(tmp_path, monkeypatch):
    asked = []

    def record(prompt, **kwargs):
        asked.append(kwargs["prompt_version"])
        return {}

    monkeypatch.setattr(llm_discovery, "chat_json", record)
    pairs = tmp_path / "pairs.csv"
    pairs.write_text("source,target\ntrees,binary_tree\n")
    cli.main(
        [
            *["--concepts", f"{EX}/concepts.json", "--pairs", str(pairs)],
            *["--out-dir", str(tmp_path)],
        ]
    )
    assert asked == ["discover_v2", "discover_v2"]
