"""Necessity test with every LLM role mocked (keyed by prompt_version)."""

import json
import re
import sys

import pytest

from cdlp.validation import necessity_test as nt

CONCEPTS = {
    "concepts": [
        {"id": "king_moves", "name": "How the King Moves", "sources": [{"chunk_id": "c1"}]},
        {
            "id": "rook_moves",
            "name": "How the Rook Moves",
            "aliases": ["Rook"],
            "description": "A rook slides along rows and columns.",
            "sources": [{"chunk_id": "c2"}],
        },
        {"id": "castling", "name": "Castling", "sources": [{"chunk_id": "c3"}]},
        {"id": "endgames", "name": "Endgames", "sources": [{"chunk_id": "c4"}]},
    ]
}
CHUNKS = [
    {"chunk_id": f"c{i}", "text": t}
    for i, t in enumerate(
        ["The king moves one square.", "A rook slides.", "Castling moves king and rook.", "End."],
        1,
    )
]
RELATIONSHIPS = {
    "course_id": "chess101",
    "relationships": [{"id": "r1", "source": "rook_moves", "target": "castling"}],
}
QUESTIONS = [
    {"question": f"Q{i}?", "reference_answer": f"ref {i}", "chunk_id": "c3"} for i in (1, 2, 3)
]


@pytest.fixture
def llm(monkeypatch):
    """Role replies; records every call's prompt and kwargs."""
    calls = []
    replies = {
        "necessity_questions_v1": {"questions": QUESTIONS},
        # the "without" prompt serves two runs: keyed by the forbidden concept's name
        "necessity_learner_without_v1": {
            "How the Rook Moves": {"answers": ["no idea", "the king moves", "a rook!"]},
            "Endgames": {"answers": ["ctrl 1", "ctrl 2", "ctrl 3"]},
        },
        "necessity_learner_with_v1": {"answers": ["a", "b", "c"]},
    }
    grader = {}  # answer text -> grade

    def fake_chat_json(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        version = kwargs["prompt_version"]
        if version == "necessity_grader_v1":
            students = re.findall(r'Student: "(.*)"', prompt)
            return {
                "grades": [{"grade": grader.get(s, "correct"), "reason": "r"} for s in students]
            }
        reply = replies[version]
        if isinstance(reply, Exception):
            raise reply
        if version == "necessity_learner_without_v1" and "answers" not in reply:
            forbidden = re.search(r'NEVER learned "(.+?)"', prompt).group(1)
            return reply.get(forbidden, {"answers": ["?", "?", "?"]})
        return reply

    monkeypatch.setattr(nt, "chat_json", fake_chat_json)
    fake_chat_json.calls, fake_chat_json.replies, fake_chat_json.grader = calls, replies, grader
    return fake_chat_json


def run(**kwargs):
    return nt.run(RELATIONSHIPS, CONCEPTS, CHUNKS, **kwargs)["results"][0]


def test_gap_is_control_minus_without(llm):
    llm.grader.update({"no idea": "incorrect", "the king moves": "partial", "a rook!": "incorrect"})
    llm.grader.update({"ctrl 1": "correct", "ctrl 2": "partial", "ctrl 3": "incorrect"})

    r = run()

    assert r["score_without"] == pytest.approx(1 / 6, abs=1e-4)
    assert r["score_control"] == pytest.approx(0.5, abs=1e-4)
    assert r["necessity_gap"] == pytest.approx(1 / 3, abs=1e-4)
    assert r["necessity"] == "medium"
    # "with A" stays as a diagnostic, not the gap
    assert r["score_with"] == 1.0
    assert r["gap_with_minus_without"] == pytest.approx(5 / 6, abs=1e-4)


def test_role_play_penalty_alone_gives_no_necessity(llm):
    # without A and the control do equally badly: the ban itself, not A, hurts
    for text in ["no idea", "the king moves", "a rook!", "ctrl 1", "ctrl 2", "ctrl 3"]:
        llm.grader[text] = "incorrect"

    r = run()

    assert (r["necessity_gap"], r["necessity"]) == (0.0, "none")
    assert r["gap_with_minus_without"] == 1.0  # the old definition would have said strong


@pytest.mark.parametrize(
    "gap, grade",
    [
        (-0.5, "none"),
        (0.0, "none"),
        (0.1, "none"),
        (1 / 6, "weak"),
        (1 / 3, "medium"),
        (0.5, "strong"),
        (None, "none"),
    ],
)
def test_gap_thresholds_come_from_config(gap, grade):
    assert nt.gap_grade(gap, nt.load_config()["thresholds"]) == grade


def test_seven_calls_per_edge_seeded_at_temperature_zero(llm):
    run()

    versions = [c["prompt_version"] for c in llm.calls]
    assert versions == [
        "necessity_questions_v1",
        "necessity_learner_without_v1",  # A forbidden
        "necessity_learner_without_v1",  # control: C forbidden, same prompt
        "necessity_learner_with_v1",
        "necessity_grader_v1",
        "necessity_grader_v1",
        "necessity_grader_v1",
    ]
    assert all(c["temperature"] == 0.0 and c["seed"] == 42 for c in llm.calls)


def test_learners_get_the_right_knowledge(llm):
    r = run()
    without, control, with_a = (c["prompt"] for c in llm.calls[1:4])

    assert r["known_without"] == ["king_moves"]  # taught before castling, never A or B
    assert 'NEVER learned "How the Rook Moves"' in without
    assert "Endgames" not in without  # taught after B
    assert 'You have also learned "How the Rook Moves": A rook slides' in with_a
    assert "Your lesson" not in without  # learner_sees_lesson is false by default

    # control: same prompt and same known list, only the banned concept differs
    def head(prompt):  # the part before the fixed few-shot example
        return prompt.split("Worked example")[0]

    # control: same prompt; knows A by name (no description) and bans C instead
    assert 'NEVER learned "Endgames"' in head(control)
    assert '"How the King Moves", "How the Rook Moves"' in head(control)
    assert "A rook slides" not in head(control)  # no extra context from A's description
    assert r["control_concept"] == {"id": "endgames", "name": "Endgames", "kind": "in_course"}
    assert (r["question_format"], r["n_questions"]) == ("open", 3)
    assert r["known_control"] == ["king_moves", "rook_moves"]


def test_grader_is_blind_to_the_run(llm):
    run()

    for call in llm.calls[4:]:
        assert "NEVER" not in call["prompt"] and "How the Rook Moves" not in call["prompt"]


def test_leakage_flags_forbidden_terms_and_stems(llm):
    r = run()

    assert r["leakage"]["flagged_answers"] == [2]  # "a rook!" uses the alias
    assert r["leakage"]["rate"] == pytest.approx(1 / 3, abs=1e-4)


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("Traversals are defined recursively.", ["recursively"]),  # stem
        ("A binary search tree keeps order.", []),  # target's own name is masked
        ("A binary search tree is a binary tree with order.", ["binary tree"]),
        ("Nothing relevant here.", []),
    ],
)
def test_leaks(answer, expected):
    recursion = {"id": "recursion", "name": "Recursion"}
    binary_tree = {"id": "binary_tree", "name": "Binary Tree", "aliases": ["Binary Trees"]}
    bst = {"id": "binary_search_tree", "name": "Binary Search Tree", "aliases": ["BST"]}
    forbidden = recursion if expected == ["recursively"] else binary_tree

    assert nt.leaks(answer, forbidden, bst) == expected


def test_stemming_copy_matches_discovery():
    from cdlp.discovery import candidates

    for a, b in [
        ("recursion", "recursively"),
        ("trees", "tree"),
        ("query", "queries"),
        ("recursion", "recurrence"),
        ("graph", "paragraphs"),
    ]:
        assert nt._words_match(a, b) == candidates._words_match(a, b), (a, b)


@pytest.mark.parametrize("bad", [{}, {"questions": "x"}, ValueError("not JSON")])
def test_no_questions_gives_none_without_more_calls(llm, bad):
    llm.replies["necessity_questions_v1"] = bad

    r = run()

    assert (r["status"], r["necessity"], r["necessity_gap"]) == ("no_questions", "none", None)
    assert len(llm.calls) == 1


def test_missing_answers_and_bad_grades_count_as_incorrect(llm):
    llm.replies["necessity_learner_with_v1"] = {"answers": ["only one"]}
    llm.grader["only one"] = "excellent"  # not a grade

    r = run()

    assert r["answers_with"] == ["only one", "", ""]
    assert [g["grade"] for g in r["grades_with"]] == ["incorrect"] * 3


def _concept(cid, chunk):
    return {"id": cid, "name": cid.title(), "sources": [{"chunk_id": chunk}]}


def test_control_is_never_an_ancestor_or_descendant_of_b():
    concepts = [_concept(c, f"c{i}") for i, c in enumerate("abcdex", 1)]
    # a -> b -> c -> d, e -> c ; x unconnected. Testing b -> c: c's relatives are a, b, d, e
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("e", "c")]
    rels = [{"id": f"r{i}", "source": s, "target": t} for i, (s, t) in enumerate(edges)]

    assert nt.related_to("c", rels) == {"a", "b", "d", "e"}
    control, placeholder = nt.choose_control(
        concepts[1], concepts[2], concepts, concepts[:2], rels, nt.load_config()
    )
    assert (control["id"], placeholder) == ("x", "in_course")


def test_control_falls_back_to_the_other_course_then_the_placeholder():
    concepts = [_concept("a", "c1"), _concept("b", "c2")]
    rels = [{"id": "r1", "source": "a", "target": "b"}]
    cfg = nt.load_config()

    control, kind = nt.choose_control(concepts[0], concepts[1], concepts, [], rels, cfg, "ds101")
    assert kind == "cross_course"
    assert control["id"] in {c["id"] for c in cfg["cross_course_concepts"]["ds101"]}
    assert control["id"] == "gradient_descent"  # first ml101 concept by id

    control, kind = nt.choose_control(concepts[0], concepts[1], concepts, [], rels, cfg, "xx")
    assert kind == "placeholder"
    assert control["name"] == cfg["control_placeholder"]["name"]


def test_cross_course_pools_point_at_the_other_course():
    pools = nt.load_config()["cross_course_concepts"]
    assert {c["id"] for c in pools["ds101"]}.isdisjoint({c["id"] for c in pools["ml101"]})
    assert "recursion" in {c["id"] for c in pools["ml101"]}
    assert "gradient_descent" in {c["id"] for c in pools["ds101"]}


def test_control_prefers_a_concept_the_learner_does_not_know():
    concepts = [_concept(c, f"c{i}") for i, c in enumerate(["known", "a", "b", "later"], 1)]
    rels = [{"id": "r1", "source": "a", "target": "b"}]

    control, _ = nt.choose_control(
        concepts[1], concepts[2], concepts, [concepts[0]], rels, nt.load_config()
    )
    assert control["id"] == "later"  # known stays identical in both runs


def test_n_questions_is_configurable(llm):
    cfg = nt.load_config()
    cfg["n_questions"] = 2

    r = run(cfg=cfg)

    assert len(r["questions"]) == 2 and len(r["answers_control"]) == 2
    assert "Write exactly 2 short questions" in llm.calls[0]["prompt"]


def test_cli_writes_results_and_only_filter(llm, tmp_path, monkeypatch):
    files = {}
    for name, data in [("r.json", RELATIONSHIPS), ("c.json", CONCEPTS)]:
        files[name] = tmp_path / name
        files[name].write_text(json.dumps(data))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("".join(json.dumps(c) + "\n" for c in CHUNKS))
    out = tmp_path / "necessity.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["necessity_test", "--relationships", str(files["r.json"]), "--concepts"]
        + [str(files["c.json"]), "--chunks", str(chunks), "--out", str(out), "--only", "r1"],
    )

    nt.main()

    data = json.loads(out.read_text())
    assert [r["relationship_id"] for r in data["results"]] == ["r1"]
    assert {
        "model",
        "prompt_versions",
        "seed",
        "temperature",
        "date",
        "leakage_rate",
    } <= data.keys()


def test_prompts_have_no_course_concepts():
    terms = ["tree", "recursion", "graph", "avl", "vector", "matri", "regression", "gradient"]
    placeholder = json.dumps(nt.load_config()["control_placeholder"]).lower()
    texts = [p.read_text().lower() for p in sorted(nt.PROMPT_DIR.glob("necessity_*_v1.txt"))]
    for text in [*texts, placeholder]:
        for term in terms:
            assert term not in text, term


# --- multiple choice ---------------------------------------------------------

MCQ = [
    {"question": f"M{i}?", "options": [f"right {i}", "w1", "w2", "w3"], "correct": "A"}
    for i in (1, 2, 3)
]


def mcq_cfg(**overrides):
    cfg = nt.load_config()
    cfg["question_format"] = "mcq"
    cfg.update(overrides)
    return cfg


@pytest.fixture
def mcq_llm(llm):
    llm.replies["necessity_questions_mcq_v1"] = {"questions": MCQ}

    def letters(prompt):  # pick the option whose text starts with "right" -> all correct
        return [
            re.search(r"([A-D])\) right", line).group(1)
            for line in prompt.splitlines()
            if re.match(r"\d+\. M\d\?", line)
        ]

    original = nt.chat_json

    def fake(prompt, **kwargs):
        version = kwargs["prompt_version"]
        if version == "necessity_learner_without_mcq_v1":
            llm.calls.append({"prompt": prompt, **kwargs})
            right = letters(prompt)
            banned = re.search(r'NEVER learned "(.+?)"', prompt).group(1)
            # without A: always wrong ("W"); control: all right
            return {"answers": ["W"] * 3 if banned == "How the Rook Moves" else right}
        if version == "necessity_learner_with_mcq_v1":
            llm.calls.append({"prompt": prompt, **kwargs})
            return {"answers": letters(prompt)}
        return original(prompt, **kwargs)

    nt.chat_json = fake
    yield llm
    nt.chat_json = original


def test_mcq_grades_by_exact_match_without_grader_calls(mcq_llm):
    r = run(cfg=mcq_cfg())

    versions = [c["prompt_version"] for c in mcq_llm.calls]
    assert "necessity_grader_v1" not in versions
    assert versions[0] == "necessity_questions_mcq_v1"
    assert (r["score_control"], r["score_without"], r["necessity_gap"]) == (1.0, 0.0, 1.0)
    assert r["necessity"] == "strong" and r["question_format"] == "mcq"


def test_mcq_options_are_shuffled_deterministically(mcq_llm):
    first = run(cfg=mcq_cfg())["questions"]
    again = run(cfg=mcq_cfg())["questions"]

    assert first == again  # same seed -> same order
    assert {q["answer_letter"] for q in first} != {"A"}  # not always the first option
    for q in first:
        assert q["options"][nt.LETTERS.index(q["answer_letter"])].startswith("right")


@pytest.mark.parametrize(
    "answer, letter",
    [
        ("B", "B"),
        ("(c)", "C"),
        ("D) w3", "D"),
        ("w2", "C"),  # exact option text
        ("w9", None),
        ("right 1", "A"),
        ("", None),
        ("Because", None),
    ],
)
def test_chosen_letter(answer, letter):
    assert nt.chosen_letter(answer, ["right 1", "w1", "w2", "w3"]) == letter


@pytest.mark.parametrize(
    "bad",
    [
        {"question": "Q?", "options": ["a", "b", "c"], "correct": "A"},  # 3 options
        {"question": "Q?", "options": ["a", "a", "c", "d"], "correct": "A"},  # duplicate
        {"question": "Q?", "options": ["a", "b", "c", "d"], "correct": "E"},  # bad key
        {"question": "Q?", "options": ["a", "b", "c", "d"], "correct": "zzz"},
    ],
)
def test_malformed_mcq_is_dropped(bad):
    assert nt._mcq_question(bad, mcq_cfg(), "t", 0) is None


def test_mcq_correct_may_be_given_as_option_text():
    q = nt._mcq_question(
        {"question": "Q?", "options": ["a", "b", "c", "d"], "correct": "c"}, mcq_cfg(), "t", 0
    )
    assert q["options"][nt.LETTERS.index(q["answer_letter"])] == "c"


def test_with_a_diagnostic_can_be_skipped(llm):
    cfg = nt.load_config()
    cfg["with_a_diagnostic"] = False

    r = run(cfg=cfg)

    assert "necessity_learner_with_v1" not in [c["prompt_version"] for c in llm.calls]
    assert r["score_with"] is None and r["answers_with"] == []
    assert r["necessity_gap"] is not None


def test_result_fields_fit_the_validated_graph_contract(llm):
    from cdlp.shared.io import EXAMPLES, read_json
    from cdlp.shared.validate import check

    r = run()
    graph = read_json(EXAMPLES / "validated_graph.json")
    edge = graph["edges"][1]
    for field in ("score_control", "score_without", "n_questions", "question_format"):
        edge[field] = r[field]
    edge["necessity_gap"] = r["necessity_gap"]

    assert check(graph, "validated_graph") == []
    assert r["necessity_gap"] == pytest.approx(r["score_control"] - r["score_without"], abs=1e-4)
