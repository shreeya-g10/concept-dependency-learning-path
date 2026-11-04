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


NOTEBOOK = ROOT / "notebooks" / "colab_validator.ipynb"


def test_notebook_has_one_cell_per_step_and_no_outputs():
    import re

    nb = json.loads(NOTEBOOK.read_text())
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert all(
        not c.get("outputs") and c.get("execution_count") is None
        for c in nb["cells"]
        if c["cell_type"] == "code"
    )
    steps = [int(m.group(1)) for src in code if (m := re.match(r"# Step (\d+)", src))]
    assert steps == list(range(9))
    assert nb["metadata"]["accelerator"] == "GPU"


def test_notebook_pins_a_commit_with_the_runner():
    import re

    first = "".join(json.loads(NOTEBOOK.read_text())["cells"][1]["source"])
    commit = re.search(r'COMMIT = "([0-9a-f]+)"', first).group(1)
    stages = re.search(r'STAGE = "(\w+)"', first).group(1)
    assert len(commit) == 40 and stages in cr.STAGES
    found = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}:scripts/colab_run.py"],
        capture_output=True,
    )
    if found.returncode != 0:  # e.g. a shallow CI clone without that commit
        pytest.skip("pinned commit not in this clone's history")


# --- GPU and models --------------------------------------------------------------------


def test_no_gpu_stops_before_anything_runs(monkeypatch, capsys):
    monkeypatch.setattr(cr, "_out", lambda cmd: "")
    monkeypatch.setattr(cr, "run_stage", lambda *a, **k: pytest.fail("ran without a GPU"))
    with pytest.raises(SystemExit, match="No GPU"):
        cr.main(["stage", "course", "--course", "ds101"])
    with pytest.raises(SystemExit, match="No GPU"):
        cr.main(["stage", "speed"])


def test_exactly_two_models_and_each_needs_a_digest():
    assert cr.MODELS == ("qwen2.5:7b-instruct", "llama3.1:8b")
    with pytest.raises(SystemExit, match="qwen2.5"):
        cr.require_models({"models": [{"name": "llama3.1:8b", "digest": "a", "size": 1}]})
    both = {"models": [{"name": m, "digest": m[:2], "size": 5} for m in cr.MODELS]}
    assert cr.require_models(both)["llama3.1:8b"] == {"digest": "ll", "size_bytes": 5}


@pytest.mark.parametrize(
    "gpu, fits",
    [
        ("Tesla T4, 15360 MiB, 535", True),
        ("Small, 8192 MiB", False),
        (None, False),
    ],
)
def test_both_models_fit_only_with_room_to_spare(gpu, fits):
    models = {m: {"size_bytes": 5 * 2**30} for m in cr.MODELS}
    assert cr.both_models_fit(gpu, models) is fits


def test_unknown_size_counts_as_not_fitting():
    assert not cr.both_models_fit("Tesla T4, 15360 MiB", {"a": {"size_bytes": None}})


def test_other_models_are_unloaded_only_when_both_do_not_fit(monkeypatch):
    table = "NAME ID SIZE\nllama3.1:8b x 5 GB\nqwen2.5:7b-instruct y 5 GB"
    monkeypatch.setattr(cr, "_out", lambda cmd: table)
    stopped = []
    step = {"models": ["qwen2.5:7b-instruct"]}
    cr.unload_other_models(step, fit=True, runner=stopped.append)
    assert stopped == []
    cr.unload_other_models(step, fit=False, runner=stopped.append)
    assert stopped == [["ollama", "stop", "llama3.1:8b"]]


def test_environment_records_both_digests(monkeypatch, tmp_path):
    monkeypatch.setattr(cr, "_out", lambda cmd: "Tesla T4, 15360 MiB" if "nvidia" in cmd[0] else "")
    monkeypatch.setattr(
        cr,
        "_tags",
        lambda: {"models": [{"name": m, "digest": m, "size": 2**30} for m in cr.MODELS]},
    )
    env = cr.environment("llama3.1:8b", "course", "ds101")
    assert env["gpu"] and env["course"] == "ds101" and env["both_models_fit"]
    assert {m: v["digest"] for m, v in env["models"].items()} == {m: m for m in cr.MODELS}


# --- the course stage ------------------------------------------------------------------


def arg(step, flag):
    return step["argv"][step["argv"].index(flag) + 1]


def test_steps_can_be_a_subset_and_always_run_in_order(tmp_path):
    assert cr.parse_steps("quiz,extract") == ["extract", "quiz"]
    assert cr.parse_steps(None) == list(cr.COURSE_STEPS)
    with pytest.raises(ValueError):
        cr.parse_steps("extract,nonsense")
    steps = cr.plan("course", tmp_path, "ds101", ["extract", "discover"])
    assert [s["label"] for s in steps] == ["ds101: extract", "ds101: discover"]


def test_course_needs_a_valid_id(tmp_path):
    for bad in ("../ds101", "DS101", "_previews"):
        with pytest.raises(ValueError):
            cr.plan("course", tmp_path, bad)
    with pytest.raises(ValueError):
        cr.plan("course", tmp_path)


def test_course_discovery_asks_both_orders(tmp_path):
    step = cr.plan("course", tmp_path, "ds101", ["discover"])[0]
    assert "--one-order" not in step["argv"] and "--pairs" not in step["argv"]
    assert step["check"] is cr.check_both_orders


@pytest.mark.parametrize("course", ["ds101", "ml101"])
def test_ds101_and_ml101_sample_40_edges_for_necessity(tmp_path, course):
    step = cr.plan("course", tmp_path, course, ["validate"])[0]
    assert arg(step, "--necessity-sample") == "40" and arg(step, "--necessity-seed") == "42"
    assert "--skip-necessity" not in step["argv"]


def test_a_demo_course_skips_necessity_and_nothing_else(tmp_path):
    step = cr.plan("course", tmp_path, "avl_notes", ["validate"])[0]
    assert "--skip-necessity" in step["argv"] and "--necessity-sample" not in step["argv"]
    for shortcut in ("--demo-subset", "--skip-evidence", "--skip-semantic", "--skip-graph"):
        assert shortcut not in step["argv"]


def test_no_step_of_any_course_takes_a_shortcut(tmp_path):
    for step in cr.plan("course", tmp_path, "avl_notes"):
        argv = step["argv"]
        if callable(argv):  # the path step, which is only learning_path with no LLM
            continue
        for shortcut in ("--allow-rule-based", "--allow-tfidf", "--demo-subset", "--limit"):
            assert shortcut not in argv


def test_quiz_uses_quiz_v3_on_accepted_links_only(tmp_path):
    step = cr.plan("course", tmp_path, "ds101", ["quiz"])[0]
    assert arg(step, "--prompt-version") == "quiz_v3"
    assert arg(step, "--only-graph").endswith("validated_graph.json")
    assert step["check"] is cr.check_quiz_prompt
    assert set(step["models"]) == set(cr.MODELS)


def test_each_step_loads_only_the_model_it_needs(tmp_path):
    by_name = {s["label"].split(": ")[1]: s["models"] for s in cr.plan("course", tmp_path, "ds101")}
    assert by_name["extract"] == by_name["discover"] == [cr.DISCOVERY_MODEL]
    assert by_name["validate"] == [cr.VALIDATOR_MODEL]
    assert by_name["path"] == []


def course_files(root, course="ds101"):
    d = root / "outputs" / course
    d.mkdir(parents=True, exist_ok=True)
    for name in ("concepts.json", "chunks.jsonl", "validated_graph.json"):
        (d / name).write_text((cr.ROOT / "cdlp/shared/examples" / name).read_text())
    return d


BOTH_ORDERS = {
    "prompt_version": "discover_v3_1",
    "pair_order_rule": "hash",
    "answers": {},
    "both_orders": {
        "rule_version": "order_rule_v1",
        "pairs": 1,
        "stable": 1,
        "unstable": 0,
        "reversed": 0,
        "neither": 0,
        "answers_all_asks": {"A_BEFORE_B": 2},
    },
}


def good_relationships(d):
    data = json.loads((cr.ROOT / "cdlp/shared/examples/relationships.json").read_text())
    data["discovery"] = BOTH_ORDERS
    (d / "relationships.json").write_text(json.dumps(data))


def ok_runner(calls):
    def run(argv, cwd):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    return run


def test_a_missing_input_stops_a_course_and_names_the_file(tmp_path, capsys):
    calls = []
    report = cr.run_stage(
        "course", tmp_path, course="ds101", steps=["validate", "quiz"], runner=ok_runner(calls)
    )
    assert report == [("ds101: validate", "missing input")]
    assert calls == []
    assert "relationships.json" in capsys.readouterr().out


def test_an_empty_course_folder_is_refused_rather_than_filled_with_examples(tmp_path):
    (tmp_path / "data/raw/avl_notes").mkdir(parents=True)
    calls = []
    with pytest.raises(SystemExit, match="No course files"):
        cr.run_stage(
            "course", tmp_path, course="avl_notes", steps=["extract"], runner=ok_runner(calls)
        )
    assert calls == []


def test_a_failed_step_stops_a_course(tmp_path):
    d = course_files(tmp_path)
    (d / "concepts.json").unlink()
    (tmp_path / "data/raw/ds101").mkdir(parents=True)
    (tmp_path / "data/raw/ds101/notes.md").write_text("# Notes")
    calls = []

    def fail(argv, cwd):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 2)

    report = cr.run_stage("course", tmp_path, course="ds101", runner=fail)
    assert report == [("ds101: extract", "exit 2")] and len(calls) == 1


def test_uploaded_files_count_as_done_so_extract_is_skipped(tmp_path):
    course_files(tmp_path)
    calls = []
    assert not (tmp_path / "data/raw/ds101").exists()  # an uploaded result needs no input
    report = dict(
        cr.run_stage(
            "course",
            tmp_path,
            course="ds101",
            steps=["extract", "discover"],
            runner=ok_runner(calls),
        )
    )
    assert report["ds101: extract"] == "done"
    assert len(calls) == 1 and "cdlp.discovery" in calls[0]


def test_a_clean_exit_with_no_valid_output_is_a_failure_and_stops(tmp_path):
    course_files(tmp_path)
    report = cr.run_stage(
        "course", tmp_path, course="ds101", steps=["discover", "validate"], runner=ok_runner([])
    )
    assert report == [("ds101: discover", "no valid output")]


def test_a_file_cut_short_by_a_disconnect_runs_again(tmp_path, capsys):
    d = course_files(tmp_path)
    (d / "concepts.json").write_text('{"schema_version": "1.7", "conc')
    (tmp_path / "data/raw/ds101").mkdir(parents=True)
    (tmp_path / "data/raw/ds101/notes.md").write_text("# Notes")
    calls = []

    def rewrites(argv, cwd):
        calls.append(argv)
        (d / "concepts.json").write_text(
            (cr.ROOT / "cdlp/shared/examples/concepts.json").read_text()
        )
        return subprocess.CompletedProcess(argv, 0)

    report = dict(
        cr.run_stage("course", tmp_path, course="ds101", steps=["extract"], runner=rewrites)
    )
    assert report["ds101: extract"] == "ok" and len(calls) == 1
    assert "cut short" in capsys.readouterr().out


def test_a_one_order_file_is_never_used_as_done(tmp_path):
    d = course_files(tmp_path)
    data = json.loads((cr.ROOT / "cdlp/shared/examples/relationships.json").read_text())
    (d / "relationships.json").write_text(json.dumps(data))
    calls = []
    report = cr.run_stage(
        "course", tmp_path, course="ds101", steps=["discover", "validate"], runner=ok_runner(calls)
    )
    assert report == [("ds101: discover", "wrong kind of run")] and calls == []


def test_discovery_that_did_not_ask_both_orders_fails_the_step(tmp_path):
    d = course_files(tmp_path)

    def write_one_order(argv, cwd):
        (d / "relationships.json").write_text(
            (cr.ROOT / "cdlp/shared/examples/relationships.json").read_text()
        )
        return subprocess.CompletedProcess(argv, 0)

    report = cr.run_stage(
        "course", tmp_path, course="ds101", steps=["discover"], runner=write_one_order
    )
    assert report == [("ds101: discover", "wrong kind of run")]


def test_a_quiz_from_another_prompt_is_refused(tmp_path):
    d = course_files(tmp_path)
    good_relationships(d)
    old = json.loads((cr.ROOT / "cdlp/shared/examples/quiz_items.json").read_text())
    old["generation"] = {"prompt_version": "quiz_v2"}
    (d / "quiz_items.json").write_text(json.dumps(old))
    report = cr.run_stage("course", tmp_path, course="ds101", steps=["quiz"], runner=ok_runner([]))
    assert report == [("ds101: quiz", "wrong kind of run")]


def test_teacher_decisions_are_applied_after_validation(tmp_path):
    d = course_files(tmp_path)
    good_relationships(d)
    (d / "validated_graph.json").unlink()
    (d / "review_decisions.json").write_text("{}")
    calls = []
    cr.run_stage("course", tmp_path, course="ds101", steps=["validate"], runner=ok_runner(calls))
    assert [c[2] for c in calls] == ["cdlp.validation", "cdlp.validation.apply_review"]


def test_the_path_step_picks_the_deepest_topic(tmp_path):
    d = course_files(tmp_path)
    (d / "quiz_items.json").write_text(
        (cr.ROOT / "cdlp/shared/examples/quiz_items.json").read_text()
    )
    calls = []
    cr.run_stage("course", tmp_path, course="ds101", steps=["path"], runner=ok_runner(calls))
    assert calls[0][calls[0].index("--target") + 1] == "avl_tree"


def test_the_report_shows_drop_rates_for_each_level(tmp_path):
    d = course_files(tmp_path)
    good_relationships(d)
    (d / "quiz_items.json").write_text(
        (cr.ROOT / "cdlp/shared/examples/ladder_quiz_items.json").read_text()
    )
    report = cr.course_report(tmp_path, "ds101")
    assert report["quiz_prompt_version"] == "quiz_v3"
    assert report["drop_rate_by_level"]["hard"]["drafted"] == 5
    assert report["concepts_missing_level"] == {"easy": [], "medium": [], "hard": []}
    assert report["both_orders"]["rule_version"] == "order_rule_v1"
    assert report["quiz_items"] == 15
    assert report["decisions"]["ACCEPT"] > 0


# --- night 1 ---------------------------------------------------------------------------


def test_night1_makes_the_same_calls_as_the_shell_script(tmp_path):
    script = (cr.ROOT / "scripts/rq1_night1.sh").read_text()
    steps = cr.plan("night1", tmp_path)
    assert len(steps) == 2 * len(cr.BENCHMARKS)
    discovery = [s for s in steps if "discovery_only" in s["label"]]
    baseline = [s for s in steps if "baseline_prompt" in s["label"]]
    assert [s["label"].split(":")[0] for s in discovery] == cr.BENCHMARKS  # all discovery first
    assert steps[: len(discovery)] == discovery
    for flag in ("--pairs-direction given", "--baseline-only --num-ctx 16384"):
        assert flag in script
    for step in discovery:
        assert arg(step, "--pairs-direction") == "given"
        assert arg(step, "--stats").endswith("discovery_only.stats.json")
        assert step["out"].name == "relationships.json"
        assert step["models"] == ["qwen2.5:7b-instruct"]
    for step in baseline:
        assert "--baseline-only" in step["argv"] and arg(step, "--num-ctx") == "16384"
        assert arg(step, "--stats").endswith("baseline_prompt.stats.json")
        assert step["out"].name == "relationships_baseline.json"


def test_night1_without_samples_is_reported_not_run(tmp_path):
    calls = []
    report = dict(cr.run_stage("night1", tmp_path, runner=ok_runner(calls)))
    assert set(report.values()) == {"missing input"} and calls == []


# --- speed and time --------------------------------------------------------------------


def test_speed_stage_makes_10_short_and_5_long_calls_for_each_model(tmp_path, capsys):
    seen = []

    def measure(model, calls, kind):
        seen.append((model, kind, calls))
        return {"model": model, "kind": kind, "calls": calls, "first_call_s": 9, "warm_mean_s": 1.5}

    cr.speed_stage(tmp_path, measure=measure)
    assert seen == [(m, k, n) for m in cr.MODELS for k, n in (("short", 10), ("long", 5))]
    assert "1.5 s per call" in capsys.readouterr().out
    assert len(json.loads((tmp_path / "colab_speed.json").read_text())[0]["rows"]) == 4


def test_a_long_speed_call_asks_for_more_than_a_short_one():
    assert len(cr._speed_prompt("long", 1)) > 3 * len(cr._speed_prompt("short", 1))
    assert cr._speed_prompt("long", 1) != cr._speed_prompt("long", 2)


def test_timing_gives_seconds_per_call_per_type_over_every_session(tmp_path, capsys):
    log = tmp_path / "calls.jsonl"
    rows = [
        {"kind": "call", "model": "a", "prompt_version": "p1", "seconds": 4.0, "cached": False},
        {"kind": "call", "model": "a", "prompt_version": "p1", "seconds": 6.0, "cached": False},
        {"kind": "call", "model": "a", "prompt_version": "p1", "seconds": 0.0, "cached": True},
        {"kind": "call", "model": "b", "prompt_version": "p2", "seconds": 0.0, "cached": True},
        {"kind": "step", "label": "one", "seconds": 30, "status": "ok"},
        {"kind": "step", "label": "two", "seconds": 12, "status": "ok"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + '\n{"kind": "call", "mod')
    report = cr.timing(log)
    first, second = report["call_types"]
    assert (first["call_type"], first["new_calls"], first["cache_hits"]) == ("p1", 2, 1)
    assert first["seconds_per_new_call"] == 5.0 and first["total_seconds"] == 10
    assert second["seconds_per_new_call"] is None
    assert report["total_seconds"] == 42
    cr.print_timing(report)
    out = capsys.readouterr().out
    assert "5.00" in out and "total for this stage: 42 s" in out


def test_each_step_writes_its_time_to_the_log(tmp_path):
    d = course_files(tmp_path)
    log = d / "colab_calls.jsonl"
    cr.run_stage(
        "course", tmp_path, course="ds101", steps=["discover"], runner=ok_runner([]), log=log
    )
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[0]["kind"] == "step" and rows[0]["label"] == "ds101: discover"


# --- zips ------------------------------------------------------------------------------


def finished_course(root, course="my_course"):
    d = course_files(root, course)
    (d / "quiz_items.json").write_text(
        (cr.ROOT / "cdlp/shared/examples/quiz_items.json").read_text()
    )
    return d


def test_the_zip_holds_only_this_course(tmp_path):
    import zipfile

    finished_course(tmp_path)
    finished_course(tmp_path, "other_course")
    (tmp_path / "outputs/colab_environment.json").write_text("[]")
    out = cr.zip_course(tmp_path, "my_course", tmp_path / "dest", stamp="x")
    assert out.name == "course_my_course_x.zip"
    names = zipfile.ZipFile(out).namelist()
    assert names and all(n.startswith("outputs/my_course/") for n in names)
    assert "outputs/my_course/validated_graph.json" in names


@pytest.mark.parametrize("missing", cr.WEBSITE_FILES)
def test_an_unfinished_course_is_not_zipped(tmp_path, missing):
    d = finished_course(tmp_path)
    (d / missing).unlink()
    with pytest.raises(SystemExit, match=missing):
        cr.zip_course(tmp_path, "my_course", tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


def test_the_website_lists_the_course_after_following_the_printed_steps(tmp_path):
    import zipfile

    sys.path.insert(0, str(cr.ROOT / "website"))
    import common

    finished_course(tmp_path / "colab")
    out = cr.zip_course(tmp_path / "colab", "my_course", tmp_path, stamp="x")
    steps = cr.where_to_put(out.name, "my_course")
    assert f"unzip -o ~/Downloads/{out.name} -d ." in steps and "outputs/my_course/" in steps
    laptop = tmp_path / "laptop"
    laptop.mkdir()
    zipfile.ZipFile(out).extractall(laptop)
    assert common.list_courses(laptop / "outputs") == ["my_course"]


def start_files(tmp_path, n=2, course="ds101"):
    chunk = {"chunk_id": "c1", "course_id": course, "doc": "d.pdf", "page": 1, "text": "x"}
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(json.dumps(chunk) + "\n")
    concept = {"name": "A", "sources": [{"doc": "d.pdf", "page": 1, "chunk_id": "c1"}]}
    concepts = tmp_path / "picked.json"
    concepts.write_text(
        json.dumps(
            {
                "schema_version": "1.7",
                "course_id": course,
                "concepts": [{**concept, "id": f"c{i}"} for i in range(n)],
            }
        )
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "abc.json").write_text('{"response": "x"}')
    return concepts, chunks, cache


def test_pack_puts_files_where_the_notebook_expects_them(tmp_path):
    import zipfile

    concepts, chunks, cache = start_files(tmp_path)
    report_file = tmp_path / "concept_filter_report.json"
    report_file.write_text("{}")
    out = tmp_path / "ds101_start.zip"
    done = cr.pack_start("ds101", concepts, chunks, [cache], out, 2, [report_file])
    assert done["concepts"] == 2 and done["saved_replies"] == 1
    assert set(zipfile.ZipFile(out).namelist()) == {
        "outputs/ds101/concepts.json",  # renamed, so a filtered list is the course's list
        "outputs/ds101/chunks.jsonl",
        "outputs/ds101/concept_filter_report.json",
        "cache/llm/abc.json",
    }


def test_pack_refuses_the_wrong_concept_list(tmp_path):
    concepts, chunks, cache = start_files(tmp_path, n=259)
    out = tmp_path / "x.zip"
    with pytest.raises(SystemExit, match="259 concepts, not 85"):
        cr.pack_start("ds101", concepts, chunks, [cache], out, 85)
    assert not out.exists()


def test_pack_refuses_another_course_and_a_missing_chunk(tmp_path):
    concepts, chunks, cache = start_files(tmp_path)
    with pytest.raises(SystemExit, match="not ml101"):
        cr.pack_start("ml101", concepts, chunks, [cache], tmp_path / "x.zip")
    data = json.loads(concepts.read_text())
    data["concepts"][0]["sources"][0]["chunk_id"] = "gone"
    concepts.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="cited chunks"):
        cr.pack_start("ds101", concepts, chunks, [cache], tmp_path / "x.zip")


# --- the notebook ----------------------------------------------------------------------


def notebook_text():
    nb = json.loads(NOTEBOOK.read_text())
    return "\n".join("".join(c["source"]) for c in nb["cells"])


def test_the_notebook_runs_every_stage_with_both_exact_models():
    text = notebook_text()
    assert 'DISCOVERY_MODEL = "qwen2.5:7b-instruct"' in text
    assert 'VALIDATOR_MODEL = "llama3.1:8b"' in text
    assert "ollama pull {DISCOVERY_MODEL}" in text and "ollama pull {VALIDATOR_MODEL}" in text
    assert "colab_run.py stage speed" in text
    assert "stage course --course {COURSE} --steps {STEPS}" in text
    assert "zip --course {COURSE}" in text


def test_no_tunnel_and_no_shortcut_anywhere():
    words = (
        "ngrok",
        "cloudflared",
        "localtunnel",
        "--demo-subset",
        "--allow-rule-based",
        "--allow-tfidf",
    )
    docs = (cr.ROOT / "docs/colab_steps.md").read_text()
    runner = (cr.ROOT / "scripts/colab_run.py").read_text()
    for text in (notebook_text(), docs, runner):
        for word in words:
            assert word not in text


def test_the_runner_at_the_pinned_commit_is_this_runner():
    """A notebook that pins an older runner would quietly run the old stages."""
    import re

    first = "".join(json.loads(NOTEBOOK.read_text())["cells"][1]["source"])
    commit = re.search(r'COMMIT = "([0-9a-f]+)"', first).group(1)
    pinned = subprocess.run(
        ["git", "-C", str(cr.ROOT), "show", f"{commit}:scripts/colab_run.py"],
        capture_output=True,
        text=True,
    )
    if pinned.returncode != 0:  # e.g. a shallow CI clone without that commit
        pytest.skip("pinned commit not in this clone's history")
    assert pinned.stdout == (cr.ROOT / "scripts/colab_run.py").read_text()


def test_the_stage_command_records_the_run_and_sets_both_models(tmp_path, monkeypatch, capsys):
    tags = {"models": [{"name": m, "digest": f"d_{m}", "size": 2**30} for m in cr.MODELS]}
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "_out", lambda cmd: "Tesla T4, 15360 MiB" if "nvidia" in cmd[0] else "")
    monkeypatch.setattr(cr, "_tags", lambda: tags)
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: "rev1")
    for name in ("LLM_MODEL", "LLM_VALIDATOR_MODEL", "LLM_CALL_LOG"):
        monkeypatch.setenv(name, "before")
    seen = {}

    def fake_run_stage(stage, **kwargs):
        seen.update(stage=stage, **kwargs)
        return [("ds101: discover", "ok")]

    monkeypatch.setattr(cr, "run_stage", fake_run_stage)
    cr.main(["stage", "course", "--course", "ds101", "--steps", "validate,discover"])
    assert seen["stage"] == "course" and seen["steps"] == ["discover", "validate"]
    assert cr.os.environ["LLM_MODEL"] == "qwen2.5:7b-instruct"
    assert cr.os.environ["LLM_VALIDATOR_MODEL"] == "llama3.1:8b"
    assert cr.os.environ["LLM_CALL_LOG"].endswith("outputs/ds101/colab_calls.jsonl")
    env = json.loads((tmp_path / "outputs/ds101/colab_environment.json").read_text())[0]
    assert env["gpu"] and env["models"]["llama3.1:8b"]["digest"] == "d_llama3.1:8b"
    out = capsys.readouterr().out
    assert "d_qwen2.5:7b-instruct" in out and "total for this stage" in out


def test_a_failed_stage_exits_with_an_error(tmp_path, monkeypatch):
    tags = {"models": [{"name": m, "digest": "d", "size": 1} for m in cr.MODELS]}
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "_out", lambda cmd: "Tesla T4, 15360 MiB" if "nvidia" in cmd[0] else "")
    monkeypatch.setattr(cr, "_tags", lambda: tags)
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: "rev1")
    for name in ("LLM_MODEL", "LLM_VALIDATOR_MODEL", "LLM_CALL_LOG"):
        monkeypatch.setenv(name, "before")
    monkeypatch.setattr(cr, "run_stage", lambda *a, **k: [("x: discover", "exit 3")])
    with pytest.raises(SystemExit, match="failed steps"):
        cr.main(["stage", "course", "--course", "ds101"])


# --- the embedding model ---------------------------------------------------------------


def fake_home(tmp_path, monkeypatch, *, weights="model.safetensors", modules=True, ref="rev1"):
    """A Hugging Face cache laid out the way a finished download leaves it."""
    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HF_HOME", raising=False)
    folder = cr.embedding_model_folder()
    snapshot = folder / "snapshots" / "rev1"
    snapshot.mkdir(parents=True)
    (folder / "refs").mkdir()
    if ref is not None:
        (folder / "refs" / "main").write_text(f"{ref}\n")
    if weights:
        (snapshot / weights).write_text("x")
    if modules:
        (snapshot / "modules.json").write_text("[]")
    return folder


def test_a_finished_download_gives_its_revision(tmp_path, monkeypatch):
    fake_home(tmp_path, monkeypatch)
    assert cr.embedding_model_revision() == "rev1"
    assert cr.require_embedding_model() == "rev1"


def test_older_weights_file_also_counts(tmp_path, monkeypatch):
    fake_home(tmp_path, monkeypatch, weights="pytorch_model.bin")
    assert cr.embedding_model_revision() == "rev1"


def test_no_model_at_all_is_not_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    assert cr.embedding_model_revision() is None


@pytest.mark.parametrize(
    "broken", [{"weights": None}, {"modules": False}, {"ref": None}, {"ref": ""}, {"ref": "other"}]
)
def test_an_interrupted_download_is_not_downloaded(tmp_path, monkeypatch, broken):
    fake_home(tmp_path, monkeypatch, **broken)
    assert cr.embedding_model_revision() is None


def test_weights_that_point_nowhere_are_not_downloaded(tmp_path, monkeypatch):
    folder = fake_home(tmp_path, monkeypatch, weights=None)
    (folder / "snapshots" / "rev1" / "model.safetensors").symlink_to(folder / "blobs" / "gone")
    assert cr.embedding_model_revision() is None


def test_the_message_says_what_is_missing_and_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HF_HOME", raising=False)
    with pytest.raises(SystemExit) as stopped:
        cr.require_embedding_model()
    message = str(stopped.value)
    assert "sentence-transformers/all-MiniLM-L6-v2 is not downloaded" in message
    assert "step 3" in message and str(tmp_path) in message
    assert "HF_HOME" not in message


def test_the_message_explains_a_download_saved_where_extraction_never_looks(tmp_path, monkeypatch):
    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HF_HOME", "/content/elsewhere")
    with pytest.raises(SystemExit, match="HF_HOME is set to /content/elsewhere"):
        cr.require_embedding_model()


def test_it_checks_the_same_folder_extraction_refuses_on(tmp_path, monkeypatch):
    """If these drift apart, a stage could start and then fail inside extraction."""
    from cdlp.extraction import extract

    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(extract, "_EMBEDDER", None)
    monkeypatch.setattr(extract, "_EMBEDDER_ERROR", "")
    assert extract.get_embedder() is None
    assert "is not downloaded" in extract._EMBEDDER_ERROR
    assert str(cr.embedding_model_folder() / "snapshots") in extract._EMBEDDER_ERROR


@pytest.fixture
def gpu_and_models(monkeypatch):
    tags = {"models": [{"name": m, "digest": "d", "size": 1} for m in cr.MODELS]}
    monkeypatch.setattr(cr, "_out", lambda cmd: "Tesla T4, 15360 MiB" if "nvidia" in cmd[0] else "")
    monkeypatch.setattr(cr, "_tags", lambda: tags)


@pytest.mark.parametrize(
    "argv",
    [
        ["stage", "course", "--course", "ds101", "--steps", "extract"],
        ["stage", "course", "--course", "ds101", "--steps", "validate"],
        ["stage", "night1"],
        ["stage", "night2"],
        ["stage", "real"],
        ["run", "--stage", "night3"],
        ["stage", "speed"],
    ],
)
def test_no_stage_starts_without_the_model(tmp_path, monkeypatch, gpu_and_models, argv):
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: None)
    monkeypatch.setattr(cr, "run_stage", lambda *a, **k: pytest.fail("a stage started"))
    monkeypatch.setattr(cr, "speed_stage", lambda *a, **k: pytest.fail("speed started"))
    with pytest.raises(SystemExit, match="is not downloaded"):
        cr.main(argv)
    assert not list(tmp_path.rglob("colab_environment.json"))  # stopped before recording anything


def test_no_gpu_is_still_reported_first(monkeypatch):
    monkeypatch.setattr(cr, "_out", lambda cmd: "")
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: None)
    with pytest.raises(SystemExit, match="No GPU"):
        cr.main(["stage", "night1"])


def test_the_revision_is_recorded_beside_the_gpu_and_digests(
    tmp_path, monkeypatch, gpu_and_models, capsys
):
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: "rev1")
    for name in ("LLM_MODEL", "LLM_VALIDATOR_MODEL", "LLM_CALL_LOG"):
        monkeypatch.setenv(name, "before")
    monkeypatch.setattr(cr, "run_stage", lambda *a, **k: [("ds101: discover", "ok")])
    cr.main(["stage", "course", "--course", "ds101", "--steps", "discover"])
    env = json.loads((tmp_path / "outputs/ds101/colab_environment.json").read_text())[0]
    assert env["embedding_model"] == {"name": cr.EMBEDDING_MODEL, "revision": "rev1"}
    assert env["gpu"] and env["models"]["llama3.1:8b"]["digest"] == "d"
    assert f"{cr.EMBEDDING_MODEL}: rev1" in capsys.readouterr().out


def test_the_env_command_reports_a_missing_model_without_stopping(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "_out", lambda cmd: "")
    monkeypatch.setattr(cr, "embedding_model_revision", lambda: None)
    cr.main(["env", "--out-dir", str(tmp_path)])
    env = json.loads((tmp_path / "colab_environment.json").read_text())[0]
    assert env["embedding_model"]["revision"] is None


def test_the_course_stage_never_asks_extraction_to_fall_back(tmp_path):
    for step in cr.plan("course", tmp_path, "ds101"):
        if not callable(step["argv"]):
            assert not any("tfidf" in part for part in step["argv"])


def test_extraction_still_refuses_to_fall_back():
    """This work adds a check at the start. It does not change extraction's own refusal."""
    source = (cr.ROOT / "cdlp/extraction/extract.py").read_text()
    assert 'SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)' in source
    assert "if not allow_tfidf:" in source


def test_step_3_downloads_the_model_after_the_installs_and_prints_its_dimension():
    cells = ["".join(c["source"]) for c in json.loads(NOTEBOOK.read_text())["cells"]]
    step = next(c for c in cells if c.startswith("# Step 3"))
    last_install = step.rindex("!pip install")
    download = step.index('"sentence-transformers/all-MiniLM-L6-v2"')
    assert last_install < download
    assert "SentenceTransformer(" in step and "get_sentence_embedding_dimension()" in step
    assert 'print("embedding model ready, dimension:", dimension)' in step
    assert 'device="cpu"' in step  # the notebook must hold no GPU memory while stages run
    assert "local_files_only" not in step  # this cell is the one that downloads
    # Not behind a condition, so it runs in every session.
    assert not any(
        line.startswith(("if ", "    "))
        for line in step[step.index("from sentence_transformers") :].splitlines()
        if "SentenceTransformer(" in line
    )


def test_the_notebook_and_runner_name_the_same_model():
    assert cr.EMBEDDING_MODEL in notebook_text()
    assert cr.EMBEDDING_MODEL in (cr.ROOT / "docs/colab_steps.md").read_text()
