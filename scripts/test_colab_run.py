"""Colab runner without Colab: plans, resume, inputs, environment, speed (LLM mocked)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("colab_run", ROOT / "scripts/colab_run.py")
cr = importlib.util.module_from_spec(spec)
sys.modules["colab_run"] = cr
spec.loader.exec_module(cr)


def rels(tmp_path, course, pairs):
    d = tmp_path / "outputs" / "rq1" / course
    d.mkdir(parents=True, exist_ok=True)
    (d / "relationships.json").write_text(
        json.dumps(
            {
                "schema_version": "1.2",
                "course_id": course,
                "relationships": [
                    {"id": f"r{i}", "source": a, "target": b} for i, (a, b) in enumerate(pairs)
                ],
            }
        )
    )
    return d


@pytest.mark.parametrize("stage, per_course", [("night2", 2), ("night3", 2)])
def test_benchmark_plans_cover_every_graph(stage, per_course, tmp_path):
    steps = cr.plan(stage, tmp_path)
    assert len(steps) == per_course * len(cr.BENCHMARKS)
    for step in steps:
        assert step["argv"][1] == "-m"
        assert str(tmp_path) in str(step["out"])


def test_night2_agent_skips_evidence_and_necessity(tmp_path):
    agent = [s for s in cr.plan("night2", tmp_path) if "agent" in s["label"]][0]
    assert "--skip-evidence" in agent["argv"] and "--skip-necessity" in agent["argv"]
    assert agent["out"].name == "validated_minus_evidence_necessity.json"


def test_real_plan_samples_40_and_reuses_the_sample(tmp_path):
    steps = cr.plan("real", tmp_path)
    assert [s["out"].name for s in steps] == [
        "validated_graph.json",
        "validated_plus_necessity.json",
    ] * 2
    for s in steps:
        i = s["argv"].index("--necessity-sample")
        assert (
            s["argv"][i + 1] == "40" and s["argv"][s["argv"].index("--necessity-seed") + 1] == "42"
        )
    assert "--necessity-weight" in steps[1]["argv"] and "--necessity-weight" not in steps[0]["argv"]


def test_subset_relationships_keep_subset_pairs_in_either_order(tmp_path):
    d = rels(tmp_path, "g", [("a", "b"), ("c", "d"), ("f", "e")])
    sample = tmp_path / "sample_pairs.csv"
    sample.write_text(
        "source,target,label,agreement,note,in_subset\na,b,hard,,,1\nc,d,none,,,0\ne,f,none,,,1\n"
    )

    out = cr.write_subset_relationships(d, sample)

    kept = [(r["source"], r["target"]) for r in json.loads(out.read_text())["relationships"]]
    assert kept == [("a", "b"), ("f", "e")]
    assert out.name.endswith("relationships.json")  # validated by the relationships schema


def test_run_stage_resumes_and_reports_missing_inputs(tmp_path):
    d = rels(tmp_path, cr.BENCHMARKS[0], [("a", "b")])
    (d / "validated_single_judge.json").write_text("{}")  # done already
    calls = []

    def fake_run(argv, cwd):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    report = dict(cr.run_stage("night2", tmp_path, runner=fake_run))

    first = cr.BENCHMARKS[0]
    assert report[f"{first}: single_judge"] == "done"
    assert report[f"{first}: agent (semantic + graph)"] == "ok"
    assert (d / "no_chunks.jsonl").exists()  # prepared for the validator
    assert report[f"{cr.BENCHMARKS[1]}: single_judge"] == "missing input"
    assert len(calls) == 1


def test_failed_step_is_reported(tmp_path):
    rels(tmp_path, cr.BENCHMARKS[0], [("a", "b")])
    report = dict(
        cr.run_stage("night2", tmp_path, runner=lambda a, cwd: subprocess.CompletedProcess(a, 3))
    )
    assert report[f"{cr.BENCHMARKS[0]}: single_judge"] == "exit 3"


def test_progress_counts_done_steps(tmp_path):
    d = rels(tmp_path, cr.BENCHMARKS[0], [("a", "b")])
    (d / "validated_single_judge.json").write_text("{}")
    p = cr.progress("night2", tmp_path)
    assert (p["steps_done"], p["steps_total"]) == (1, 2 * len(cr.BENCHMARKS))


def test_model_digest_from_tags():
    tags = {"models": [{"name": "llama3.1:8b", "digest": "46e0c10c"}, {"name": "x", "digest": "y"}]}
    assert cr.model_digest("llama3.1:8b", tags) == "46e0c10c"
    assert cr.model_digest("missing", tags) is None


def test_environment_is_appended(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cr,
        "_out",
        lambda cmd: {
            "nvidia-smi": "Tesla T4, 15360 MiB, 535",
            "ollama": "ollama version is 0.x",
        }.get(cmd[0], ""),
    )
    monkeypatch.setattr(cr, "model_digest", lambda m: "abc")
    env = cr.environment("llama3.1:8b", "night2")
    assert (env["gpu"], env["model_digest"], env["stage"]) == (
        "Tesla T4, 15360 MiB, 535",
        "abc",
        "night2",
    )

    cr.record_environment(env, tmp_path)
    path = cr.record_environment(env, tmp_path)
    assert len(json.loads(path.read_text())) == 2


def test_speed_uses_a_throwaway_cache_and_mocked_llm():
    from cdlp.shared import llm

    before = llm.CACHE_DIR
    seen = []
    result = cr.measure_speed("m", 3, chat_json=lambda p, **k: seen.append(k["model"]) or {})
    assert result["calls"] == 3 and seen == ["m"] * 3
    assert llm.CACHE_DIR == before


def test_unknown_stage_fails():
    with pytest.raises(ValueError):
        cr.plan("night9")
