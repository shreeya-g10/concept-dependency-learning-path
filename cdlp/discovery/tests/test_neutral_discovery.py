"""discover_v3 with the LLM mocked: neutral question, direction from the answer, small prompt."""

import re

import pytest

from cdlp.discovery import __main__ as cli
from cdlp.discovery import candidates, llm_discovery
from cdlp.discovery.candidates import Candidate
from cdlp.shared import llm
from cdlp.shared.validate import check_file

V3 = "discover_v3"
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
        assert kwargs["prompt_version"] == V3
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
            *["--out-dir", str(tmp_path), "--prompt-version", V3],
        ]
    )
    assert check_file(tmp_path / "relationships.json") == []
    err = capsys.readouterr().err
    assert "one neutral question each" in err and "discover_v3 answers:" in err


def test_v2_prompt_is_kept_and_stays_the_default():
    assert llm_discovery.PROMPT_VERSION == "discover_v2"
    assert "SOURCE CONCEPT" in llm_discovery.load_prompt("discover_v2")
