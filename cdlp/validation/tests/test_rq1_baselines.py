"""Single judge and self-consistency with the LLM mocked at the HTTP layer.

Mocking requests.post (not chat_json) keeps the real cache and call counters in the
loop, so write_stats() is tested end to end. No network, no Ollama.
"""

import json
import re
from pathlib import Path

import pytest

from cdlp.shared import llm
from cdlp.validation import evaluate as ev
from cdlp.validation import self_consistency as sc
from cdlp.validation import single_judge as sj

EXAMPLES = Path(__file__).resolve().parents[2] / "shared" / "examples"
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

# A stand-in semantic_v2 prompt with the same placeholders as the real prompts.
FAKE_V2 = (
    'FAKE V2. Teach "{source_name}" ({source_aliases}: {source_description}) '
    'before "{target_name}" ({target_aliases}: {target_description})?'
)

# Mocked validator: grade by edge (names as in concepts.json), optionally by seed.
GRADES = {
    ("Trees", "Binary Trees"): "strong",
    ("Binary Trees", "Binary Search Trees"): "strong",
    ("Binary Search Trees", "AVL Trees"): "medium",
    ("Recursion", "Binary Trees"): "weak",
    ("Trees", "Graphs"): {42: "strong", 43: "medium", 44: "none"},  # 2 of 3 accept
    ("Graphs", "AVL Trees"): "NOT JSON",
}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self.content}}


@pytest.fixture
def mock_llm(monkeypatch, tmp_path):
    """Answers every request from GRADES; records the request bodies."""
    bodies = []

    def fake_post(url, json=None, **kwargs):
        bodies.append(json)
        prompt = json["messages"][-1]["content"]
        source, target = re.search(r'Teach "([^"]+)".*before "([^"]+)"', prompt).groups()
        grade = GRADES[(source, target)]
        if isinstance(grade, dict):
            grade = grade[json["options"]["seed"]]
        if grade == "NOT JSON":
            return FakeResponse("I think so, probably.")
        return FakeResponse(f'{{"semantic": "{grade}", "rationale": "{source} -> {target}."}}')

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "semantic_v2.txt").write_text(FAKE_V2)
    monkeypatch.setattr(sj, "PROMPT_DIR", prompts)
    monkeypatch.setattr(llm, "PROVIDER", "ollama")
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.delenv("LLM_VALIDATOR_MODEL", raising=False)
    llm.reset_stats()
    yield bodies
    llm.reset_stats()


@pytest.fixture
def inputs(tmp_path):
    rels, concepts = tmp_path / "relationships.json", tmp_path / "concepts.json"
    rels.write_text((EXAMPLES / "relationships.json").read_text())
    concepts.write_text((EXAMPLES / "concepts.json").read_text())
    return ["--relationships", str(rels), "--concepts", str(concepts)]


def decisions(result):
    return {e["id"]: e["decision"] for e in result["edges"]}


# ---- single judge --------------------------------------------------------------
def test_single_judge_accepts_strong_and_medium_only(mock_llm, inputs, tmp_path):
    out = tmp_path / "run" / "validated_single_judge.json"
    result = sj.main([*inputs, "--out", str(out)])

    assert decisions(result) == {
        "r1": "ACCEPT",
        "r2": "ACCEPT",
        "r3": "ACCEPT",  # medium
        "r4": "REJECT",  # weak
        "r5": "ACCEPT",  # seed 42 -> strong
        "r6": "REJECT",  # reply is not JSON -> none
    }
    r6 = next(e for e in result["edges"] if e["id"] == "r6")
    assert r6["semantic"] == "none"
    assert "confidence" not in r6  # one call gives no confidence; none is made up
    assert json.loads(out.read_text()) == result
    assert result["prompt_version"] == "semantic_v2" and result["model"] == "llama3.1:8b"
    assert result["temperature"] == 0.0 and result["seed"] == 42


def test_single_judge_sends_one_call_per_edge_with_version_and_seed(mock_llm, inputs, tmp_path):
    sj.main([*inputs, "--out", str(tmp_path / "out.json"), "--model", "judge-model"])
    assert len(mock_llm) == 6
    assert {b["model"] for b in mock_llm} == {"judge-model"}
    assert {(b["options"]["temperature"], b["options"]["seed"]) for b in mock_llm} == {(0.0, 42)}
    assert all(b["format"] == "json" for b in mock_llm)
    assert "FAKE V2" in mock_llm[0]["messages"][-1]["content"]


def test_single_judge_writes_stats_and_counts_cache_hits(mock_llm, inputs, tmp_path):
    out = tmp_path / "run" / "validated_single_judge.json"
    sj.main([*inputs, "--out", str(out)])
    stats = json.loads((out.parent / "single_judge.stats.json").read_text())
    assert stats == {
        "llm_calls": 6,
        "cache_hits": 0,
        "model": "llama3.1:8b",
        "prompt_versions": ["semantic_v2"],
    }

    llm.reset_stats()  # a new process, same cache
    sj.main([*inputs, "--out", str(out), "--stats", str(tmp_path / "again.json")])
    again = json.loads((tmp_path / "again.json").read_text())
    assert (again["llm_calls"], again["cache_hits"]) == (0, 6)
    assert len(mock_llm) == 6  # nothing new was sent


def test_missing_v2_prompt_stops_with_a_clear_message(mock_llm, inputs, tmp_path):
    (sj.PROMPT_DIR / "semantic_v2.txt").unlink()
    with pytest.raises(SystemExit, match="semantic_v1"):
        sj.main([*inputs, "--out", str(tmp_path / "out.json")])
    assert mock_llm == []


def test_real_semantic_v1_prompt_fills_every_placeholder():
    concepts = {
        c["id"]: c for c in json.loads((EXAMPLES / "concepts.json").read_text())["concepts"]
    }
    rel = json.loads((EXAMPLES / "relationships.json").read_text())["relationships"][0]
    prompt = sj.build_prompt((PROMPTS / "semantic_v1.txt").read_text(), rel, concepts)
    assert not re.search(r"\{(source|target)_\w+\}", prompt)
    assert "Trees" in prompt and "Binary Trees" in prompt


# ---- self-consistency ------------------------------------------------------------
def test_majority_vote():
    assert sc.majority(["ACCEPT", "ACCEPT", "REJECT"]) == ("ACCEPT", pytest.approx(0.6667))
    assert sc.majority(["REJECT", "REJECT", "ACCEPT"]) == ("REJECT", pytest.approx(0.6667))
    assert sc.majority(["ACCEPT", "REJECT"]) == ("REJECT", 0.5)  # tie rejects
    assert sc.majority(["ACCEPT"] * 3) == ("ACCEPT", 1.0)


def test_self_consistency_three_seeded_samples_and_majority(mock_llm, inputs, tmp_path):
    out = tmp_path / "run" / "validated_self_consistency.json"
    result = sc.main([*inputs, "--out", str(out)])

    assert len(mock_llm) == 18  # 6 edges x 3 seeds
    assert sorted({b["options"]["seed"] for b in mock_llm}) == [42, 43, 44]
    assert {b["options"]["temperature"] for b in mock_llm} == {0.7}

    r5 = next(e for e in result["edges"] if e["id"] == "r5")
    assert [s["decision"] for s in r5["samples"]] == ["ACCEPT", "ACCEPT", "REJECT"]
    assert r5["decision"] == "ACCEPT" and r5["confidence"] == pytest.approx(0.6667)
    assert decisions(result)["r4"] == "REJECT"
    assert result["seeds"] == [42, 43, 44] and result["temperature"] == 0.7

    stats = json.loads((out.parent / "self_consistency.stats.json").read_text())
    assert (stats["llm_calls"], stats["cache_hits"]) == (18, 0)


def test_self_consistency_tie_rejects(mock_llm, inputs, tmp_path):
    result = sc.main([*inputs, "--out", str(tmp_path / "o.json"), "--seeds", "42", "44"])
    r5 = next(e for e in result["edges"] if e["id"] == "r5")
    assert [s["decision"] for s in r5["samples"]] == ["ACCEPT", "REJECT"]
    assert r5["decision"] == "REJECT" and r5["confidence"] == 0.5


def test_self_consistency_rejects_repeated_seeds(mock_llm, inputs, tmp_path):
    with pytest.raises(ValueError, match="differ"):
        sc.main([*inputs, "--out", str(tmp_path / "o.json"), "--seeds", "42", "42", "43"])


# ---- evaluate.py reads both outputs ------------------------------------------------
def test_evaluate_scores_both_baselines_with_their_stats(mock_llm, inputs, tmp_path):
    run_dir = tmp_path / "outputs/rq1/ds101"
    sj.main([*inputs, "--out", str(run_dir / "validated_single_judge.json")])
    llm.reset_stats()
    sc.main([*inputs, "--out", str(run_dir / "validated_self_consistency.json")])
    (tmp_path / "data/gold").mkdir(parents=True)
    (tmp_path / "data/gold/gold_edges.csv").write_text(
        "source,target,label\ntrees,binary_tree,hard\nbinary_tree,binary_search_tree,hard\n"
        "binary_search_tree,avl_tree,hard\nrecursion,binary_tree,soft\ngraphs,avl_tree,none\n"
    )
    (tmp_path / "outputs/ds101").mkdir(parents=True)
    (tmp_path / "outputs/ds101/concepts.json").write_text((EXAMPLES / "concepts.json").read_text())

    config = ev.load_config(Path(ev.__file__).parent / "configs/rq1/ds101.json")
    rows = {
        r["setting"]: r for r in ev.evaluate_course(config, config["courses"][0], tmp_path)["rows"]
    }

    judge = rows["single_judge"]
    assert judge["status"] == "ok"
    # accepts r1 r2 r3 (gold hard) and r5 (unlabelled -> FP); rejects r4 (gold soft -> FN)
    assert (judge["true_positive"], judge["false_positive"], judge["false_negative"]) == (3, 1, 1)
    assert judge["human_review_rate"] == 0.0
    assert judge["llm_calls"] == 6
    vote = rows["self_consistency"]
    assert vote["status"] == "ok" and vote["llm_calls"] == 18
