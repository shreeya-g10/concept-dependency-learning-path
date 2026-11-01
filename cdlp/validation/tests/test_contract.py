"""Contract test: the CLI runs on the shared examples and its output passes the schema.
In-process, with every LLM check and the embedder mocked (grades recorded from the real
example runs: evidence outputs/evidence_check.json, semantic results/semantic_v2_examples.json,
necessity results/necessity_v1_control_examples.json). Keep this test passing."""

import json

import pytest

from cdlp.shared import llm
from cdlp.shared.io import read_json
from cdlp.shared.validate import check_file
from cdlp.validation import __main__ as cli
from cdlp.validation import evidence_check, necessity_test, semantic_check

EX = "cdlp/shared/examples"
# recorded grades for the example edges r1..r6
EVIDENCE = {
    "r1": "medium",
    "r2": "weak",
    "r3": "strong",
    "r4": "strong",
    "r5": "strong",
    "r6": "none",
}
SEMANTIC = {
    "r1": "strong",
    "r2": "strong",
    "r3": "strong",
    "r4": "strong",
    "r5": "weak",
    "r6": "none",
}
NECESSITY = {"r2": ("weak", 0.1667), "r4": ("weak", 0.1667), "r6": ("medium", 0.3333)}


def results(rels, make):
    return {"results": [{"relationship_id": r["id"], **make(r)} for r in rels["relationships"]]}


@pytest.fixture(autouse=True)
def mocked_checks(monkeypatch):
    def no_llm(*args, **kwargs):
        raise AssertionError("tests must mock the LLM")

    monkeypatch.setattr(llm, "chat", no_llm)
    monkeypatch.setattr(llm, "chat_json", no_llm)
    monkeypatch.setattr(
        evidence_check,
        "run",
        lambda rels, concepts, chunks, **kw: results(
            rels,
            lambda r: {
                "evidence": EVIDENCE[r["id"]],
                "quotes": [
                    {
                        "chunk_id": "ch_l6_p11",
                        "doc": "ds_lec6.pdf",
                        "page": 11,
                        "quote": "A binary tree is a tree",
                    }
                ]
                if EVIDENCE[r["id"]] != "none"
                else [],
            },
        ),
    )
    monkeypatch.setattr(
        semantic_check,
        "run",
        lambda rels, concepts, **kw: results(
            rels, lambda r: {"semantic": SEMANTIC[r["id"]], "rationale": "Recorded."}
        ),
    )
    monkeypatch.setattr(
        necessity_test,
        "run",
        lambda rels, concepts, chunks, **kw: results(
            rels,
            lambda r: {
                "status": "ok",
                "necessity": NECESSITY.get(r["id"], ("medium", 0.3333))[0],
                "necessity_gap": NECESSITY.get(r["id"], ("medium", 0.3333))[1],
                "score_control": 0.8333,
                "score_without": 0.5,
            },
        ),
    )


def run_cli(tmp_path, *extra):
    return cli.main(
        [
            *["--relationships", f"{EX}/relationships.json", "--concepts", f"{EX}/concepts.json"],
            *["--chunks", f"{EX}/chunks.jsonl", "--out", str(tmp_path / "validated_graph.json")],
            *extra,
        ]
    )


def test_cli_output_matches_contract(tmp_path):
    run_cli(tmp_path)

    assert check_file(tmp_path / "validated_graph.json") == []
    graph = read_json(tmp_path / "validated_graph.json")
    assert graph["course_id"] == read_json(f"{EX}/concepts.json")["course_id"]
    for edge in graph["edges"]:
        assert set(edge["checks"]) == {"evidence", "semantic", "necessity", "graph"}
        for field in (
            "necessity_gap",
            "score_control",
            "score_without",
            "n_questions",
            "question_format",
            "confidence",
            "reason",
            "evidence",
        ):
            assert field in edge, field


def test_graphs_to_avl_tree_is_rejected_on_the_examples(tmp_path):
    graph = run_cli(tmp_path)

    by_pair = {(e["source"], e["target"]): e for e in graph["edges"]}
    edge = by_pair[("graphs", "avl_tree")]
    assert edge["decision"] == "REJECT"
    assert "neither the material nor the semantic check supports it" in edge["reason"]


def test_stats_file_is_written_per_setting(tmp_path):
    run_cli(tmp_path)
    run_cli(tmp_path, "--skip-necessity")

    assert json.loads((tmp_path / "full_agent.stats.json").read_text())["llm_calls"] == 0
    assert (tmp_path / "minus_necessity.stats.json").exists()


@pytest.mark.parametrize("check", ["evidence", "semantic", "necessity", "graph"])
def test_each_skip_flag_drops_its_check(tmp_path, monkeypatch, check):
    if check in ("evidence", "semantic", "necessity"):
        module = {
            "evidence": evidence_check,
            "semantic": semantic_check,
            "necessity": necessity_test,
        }[check]

        def must_not_run(*args, **kwargs):
            raise AssertionError(f"{check} must be skipped")

        monkeypatch.setattr(module, "run", must_not_run)

    graph = run_cli(tmp_path, f"--skip-{check}")

    assert graph["skipped_checks"] == [check]
    assert all(f"skipped: {check}" in e["reason"] for e in graph["edges"])
    assert all(e["checks"][check] == "skipped" for e in graph["edges"])
    assert check_file(tmp_path / "validated_graph.json") == []


def test_review_queue_is_written(tmp_path):
    run_cli(
        tmp_path,
        "--review-queue",
        str(tmp_path / "review_queue.json"),
        "--students",
        f"{EX}/sim_students.json",
    )

    assert check_file(tmp_path / "review_queue.json") == []


def test_review_queue_needs_students(tmp_path):
    with pytest.raises(SystemExit):
        run_cli(tmp_path, "--review-queue", str(tmp_path / "review_queue.json"))


def test_necessity_is_recorded_but_report_only(tmp_path):
    graph = run_cli(tmp_path)

    for edge in graph["edges"]:
        assert edge["checks"]["necessity"] not in ("skipped", None)
        assert edge["necessity_gap"] is not None
        if "score" in edge["reason"]:  # decided by the score, not a structural rule
            assert f"necessity {edge['checks']['necessity']} (report-only)" in edge["reason"]


def test_plus_necessity_setting_lets_necessity_decide(tmp_path):
    base = {(e["source"], e["target"]): e for e in run_cli(tmp_path)["edges"]}
    plus = run_cli(tmp_path, "--necessity-weight", "1", "--setting", "full_agent_plus_necessity")

    assert (tmp_path / "full_agent_plus_necessity.stats.json").exists()
    changed = [
        e
        for e in plus["edges"]
        if e["confidence"] != base[(e["source"], e["target"])]["confidence"]
    ]
    assert changed, "with weight 1 the necessity grades must move some scores"
    by_pair = {(e["source"], e["target"]): e for e in plus["edges"]}
    assert by_pair[("graphs", "avl_tree")]["decision"] == "REJECT"
