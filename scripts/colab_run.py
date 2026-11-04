"""Every LLM stage, for Colab (notebooks/colab_validator.ipynb), with no tunnel.

    python scripts/colab_run.py env
    python scripts/colab_run.py stage speed
    python scripts/colab_run.py stage course --course ds101 --steps extract,discover
    python scripts/colab_run.py stage night1|night2|night3|real [--force]
    python scripts/colab_run.py progress --stage course --course ds101
    python scripts/colab_run.py report --course ds101
    python scripts/colab_run.py zip --course ds101 --dest /content/drive/MyDrive/cdlp
    python scripts/colab_run.py pack --course ds101 --concepts F --chunks F --cache D --zip F

Stages:
  speed   10 short and 5 long calls for each model, in a throwaway cache.
  course  extract,discover,validate,quiz,path, or any of them in that order, so discovery can
          stop for review. Both-order discovery under order_rule_v1 and quiz_v3 are checked after
          they run. ds101 and ml101 run necessity on a seeded sample of 40 edges; any other
          course skips necessity. Nothing is shortened or made up: every step runs for real.
  night1  benchmarks: discovery_only and the baseline call, as scripts/rq1_night1.sh runs them.
  night2  benchmarks: single judge and the reported agent (semantic + graph checks,
          --skip-evidence --skip-necessity) on every proposed edge of each graph.
  night3  benchmarks: self-consistency on the 100-pair subset's proposed edges, and the
          single judge on the same subset (cache hits after night 2).
  real    ds101 / ml101: the full agent with necessity on a seeded sample of 40 proposed
          edges (report-only), then the same agent with necessity at weight 1 (cache hits).

A stage also stops if the embedding model is not downloaded at the pinned revision (notebook step
3): extraction refuses to run without it, and another revision could merge concepts differently
from the existing 85-concept list. Stages run with HF_HUB_OFFLINE=1, so no step can fetch another.

A step whose output is already there and valid is skipped, and every LLM call is cached, so
a Colab disconnect loses the call in flight and whatever Drive had not yet saved. Run the same
stage again to resume. Stages stop if there is no GPU or a model has no digest to record.

`pack` runs on the laptop: it makes the upload zip from files that already exist.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/colab_run.py` puts only scripts/ on the path
    sys.path.insert(0, str(ROOT))

from cdlp.shared.validate import check, check_file, schema_for  # noqa: E402

BENCHMARKS = [
    "al_cpl_data_mining",
    "al_cpl_geometry",
    "al_cpl_physics",
    "al_cpl_precalculus",
    "university_course",
]
REAL = ["ds101", "ml101"]
NECESSITY_SAMPLE = 40
NECESSITY_SEED = 42
STAGES = ("night1", "night2", "night3", "real", "course")
DISCOVERY_MODEL = "qwen2.5:7b-instruct"
VALIDATOR_MODEL = "llama3.1:8b"
MODELS = (DISCOVERY_MODEL, VALIDATOR_MODEL)
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# The revision that produced the existing 85-concept ds101 list. Notebook step 3 pins the same.
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ORDER_RULE = "order_rule_v1"
QUIZ_PROMPT = "quiz_v3"
COURSE_STEPS = ("extract", "discover", "validate", "quiz", "path")
COURSE_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")  # the same rule as website/jobs.py
# What the website needs to list a course (website/common.py) and to use every page.
WEBSITE_FILES = ("concepts.json", "validated_graph.json", "chunks.jsonl", "quiz_items.json")
# Room for the embedding model and each model's context, beside the two sets of weights.
GPU_MARGIN_MIB = 2500
SHORT_CALLS, LONG_CALLS = 10, 5


# --- inputs ---------------------------------------------------------------------------
def subset_pairs(sample_csv: Path) -> set[tuple[str, str]]:
    with Path(sample_csv).open(newline="") as f:
        return {(r["source"], r["target"]) for r in csv.DictReader(f) if r.get("in_subset") == "1"}


def write_subset_relationships(run_dir: Path, sample_csv: Path) -> Path:
    """Proposed edges whose pair (either order) is in the 100-pair subset."""
    keep = subset_pairs(sample_csv)
    keep |= {(b, a) for a, b in keep}
    data = json.loads((run_dir / "relationships.json").read_text())
    data["relationships"] = [r for r in data["relationships"] if (r["source"], r["target"]) in keep]
    out = run_dir / "subset_relationships.json"
    out.write_text(json.dumps(data, indent=2) + "\n")
    return out


def empty_chunks(run_dir: Path) -> Path:
    """Benchmarks have no course text: the validator still needs a chunks file."""
    path = run_dir / "no_chunks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def require_course_files(raw: Path) -> None:
    """cdlp.extraction writes the shared examples for an empty folder: never let that happen."""
    from cdlp.extraction.parse import is_course_file

    if not raw.is_dir() or not any(is_course_file(p) for p in raw.iterdir()):
        raise SystemExit(f"No course files in {raw}: nothing to extract (docs/colab_steps.md).")


# --- checks on what a step wrote -----------------------------------------------------
def check_both_orders(path: Path) -> str | None:
    """Why this relationships.json is not a both-order run under the order rule, or None."""
    both = json.loads(path.read_text()).get("discovery", {}).get("both_orders", {})
    if both.get("rule_version") != ORDER_RULE:
        return f"{path} is not a both-order run under {ORDER_RULE}; rerun discover with --force"
    return None


def check_quiz_prompt(path: Path) -> str | None:
    used = json.loads(path.read_text()).get("generation", {}).get("prompt_version")
    if used != QUIZ_PROMPT:
        return f"{path} was written by {used}, not {QUIZ_PROMPT}; rerun quiz with --force"
    return None


def usable(path: Path) -> bool:
    """A step is done only if its file is whole: a disconnect can leave half a file."""
    if not path.exists():
        return False
    try:
        if path.suffix == ".jsonl":
            [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            return True
        data = json.loads(path.read_text())
        return not check(data, schema_for(path)) if _has_contract(path) else True
    except ValueError:
        return False


def _has_contract(path: Path) -> bool:
    try:
        schema_for(path)
        return True
    except ValueError:
        return False


# --- stage plans ----------------------------------------------------------------------
def parse_steps(text: str | None) -> list[str]:
    """Chosen steps, always in pipeline order."""
    wanted = [s.strip() for s in (text or ",".join(COURSE_STEPS)).split(",") if s.strip()]
    unknown = set(wanted) - set(COURSE_STEPS)
    if unknown or not wanted:
        raise ValueError(f"unknown steps {sorted(unknown)}; choose from {COURSE_STEPS}")
    return [s for s in COURSE_STEPS if s in wanted]


def course_plan(root: Path, course: str, steps: list[str], raw: Path | None = None) -> list[dict]:
    """The course stage. Later steps need earlier outputs, so a missing one stops the run."""
    if not COURSE_ID.match(course):
        raise ValueError(f"bad course id {course!r}")
    d = root / "outputs" / course
    raw = raw or root / "data" / "raw" / course
    concepts, chunks = d / "concepts.json", d / "chunks.jsonl"
    relationships, graph = d / "relationships.json", d / "validated_graph.json"
    quiz = d / "quiz_items.json"
    py = [sys.executable, "-m"]
    necessity = (
        ["--necessity-sample", str(NECESSITY_SAMPLE), "--necessity-seed", str(NECESSITY_SEED)]
        if course in REAL
        else ["--skip-necessity"]
    )

    def path_argv() -> list[str]:
        from pipeline import default_target

        return py + [
            "cdlp.learning_path",
            "--graph",
            str(graph),
            "--quiz",
            str(quiz),
            "--target",
            default_target(graph),
            "--out-dir",
            str(d),
        ]

    def apply_teacher_decisions() -> list[str] | None:
        if not (d / "review_decisions.json").exists():
            return None
        return py + [
            "cdlp.validation.apply_review",
            "--graph",
            str(graph),
            "--decisions",
            str(d / "review_decisions.json"),
        ]

    all_steps = {
        "extract": {
            "argv": py
            + ["cdlp.extraction", "--input", str(raw), "--out-dir", str(d), "--course-id", course],
            "out": concepts,
            "needs": [raw],
            "prepare": partial(require_course_files, raw),
            "models": [DISCOVERY_MODEL],
        },
        "discover": {
            "argv": py
            + [
                "cdlp.discovery",
                "--concepts",
                str(concepts),
                "--chunks",
                str(chunks),
                "--out-dir",
                str(d),
                "--stats",
                str(d / "discovery.stats.json"),
            ],
            "out": relationships,
            "needs": [concepts, chunks],
            "check": check_both_orders,
            "models": [DISCOVERY_MODEL],
        },
        "validate": {
            "argv": py
            + [
                "cdlp.validation",
                "--relationships",
                str(relationships),
                "--concepts",
                str(concepts),
                "--chunks",
                str(chunks),
                "--out",
                str(graph),
                *necessity,
            ],
            "out": graph,
            "needs": [relationships, concepts, chunks],
            "then": apply_teacher_decisions,
            "models": [VALIDATOR_MODEL],
        },
        "quiz": {
            "argv": py
            + [
                "cdlp.learning_path.quiz",
                "--concepts",
                str(concepts),
                "--chunks",
                str(chunks),
                "--course-id",
                course,
                "--out",
                str(quiz),
                "--only-graph",
                str(graph),
                "--prompt-version",
                QUIZ_PROMPT,
            ],
            "out": quiz,
            "needs": [concepts, chunks, graph],
            "check": check_quiz_prompt,
            "models": list(MODELS),  # drafts, then a second model checks them
        },
        "path": {
            "argv": path_argv,
            "out": d / "learning_path.json",
            "needs": [graph, quiz],
            "models": [],
        },
    }
    return [
        {"label": f"{course}: {name}", "stop_on_failure": True, **all_steps[name]} for name in steps
    ]


def plan(
    stage: str,
    root: Path = ROOT,
    course: str | None = None,
    steps: list[str] | None = None,
    raw: Path | None = None,
) -> list[dict]:
    """Ordered steps: {label, argv, out, needs, prepare (callable or None), ...}."""
    if stage == "course":
        if not course:
            raise ValueError("the course stage needs a course")
        return course_plan(root, course, steps or list(COURSE_STEPS), raw)
    py = [sys.executable, "-m"]
    steps = []
    if stage == "night1":
        # The same calls as scripts/rq1_night1.sh: discovery_only on all 5 graphs, then baselines.
        for c in BENCHMARKS:
            bench = root / "outputs" / "benchmarks" / c
            run_dir = root / "outputs" / "rq1" / c
            base = py + [
                "cdlp.discovery",
                "--concepts",
                str(bench / "sample_concepts.json"),
                "--out-dir",
                str(run_dir),
            ]
            steps.append(
                {
                    "label": f"{c}: discovery_only",
                    "argv": base
                    + [
                        "--pairs",
                        str(bench / "sample_pairs.csv"),
                        "--pairs-direction",
                        "given",
                        "--stats",
                        str(run_dir / "discovery_only.stats.json"),
                    ],
                    "out": run_dir / "relationships.json",
                    "needs": [bench / "sample_pairs.csv", bench / "sample_concepts.json"],
                    "models": [DISCOVERY_MODEL],
                }
            )
        for c in BENCHMARKS:
            bench = root / "outputs" / "benchmarks" / c
            run_dir = root / "outputs" / "rq1" / c
            steps.append(
                {
                    "label": f"{c}: baseline_prompt",
                    "argv": py
                    + [
                        "cdlp.discovery",
                        "--concepts",
                        str(bench / "sample_concepts.json"),
                        "--out-dir",
                        str(run_dir),
                        "--baseline-only",
                        "--num-ctx",
                        "16384",
                        "--stats",
                        str(run_dir / "baseline_prompt.stats.json"),
                    ],
                    "out": run_dir / "relationships_baseline.json",
                    "needs": [bench / "sample_concepts.json"],
                    "models": [DISCOVERY_MODEL],
                }
            )
    elif stage in ("night2", "night3"):
        for c in BENCHMARKS:
            run_dir = root / "outputs" / "rq1" / c
            bench = root / "outputs" / "benchmarks" / c
            concepts = bench / "sample_concepts.json"
            if stage == "night2":
                steps.append(
                    {
                        "label": f"{c}: single_judge",
                        "argv": py
                        + [
                            "cdlp.validation.single_judge",
                            "--relationships",
                            str(run_dir / "relationships.json"),
                            "--concepts",
                            str(concepts),
                            "--out",
                            str(run_dir / "validated_single_judge.json"),
                        ],
                        "out": run_dir / "validated_single_judge.json",
                        "needs": run_dir / "relationships.json",
                    }
                )
                steps.append(
                    {
                        "label": f"{c}: agent (semantic + graph)",
                        "argv": py
                        + [
                            "cdlp.validation",
                            "--relationships",
                            str(run_dir / "relationships.json"),
                            "--concepts",
                            str(concepts),
                            "--chunks",
                            str(run_dir / "no_chunks.jsonl"),
                            "--skip-evidence",
                            "--skip-necessity",
                            "--out",
                            str(run_dir / "validated_minus_evidence_necessity.json"),
                        ],
                        "out": run_dir / "validated_minus_evidence_necessity.json",
                        "needs": run_dir / "relationships.json",
                        "prepare": lambda d=run_dir: empty_chunks(d),
                    }
                )
            else:
                subset = run_dir / "subset_relationships.json"
                prep = partial(write_subset_relationships, run_dir, bench / "sample_pairs.csv")
                for name, module in (
                    ("self_consistency", "cdlp.validation.self_consistency"),
                    ("single_judge_subset", "cdlp.validation.single_judge"),
                ):
                    out = run_dir / f"validated_{name}.json"
                    argv = py + [
                        module,
                        "--relationships",
                        str(subset),
                        "--concepts",
                        str(concepts),
                        "--out",
                        str(out),
                    ]
                    if name == "single_judge_subset":
                        argv += ["--stats", str(run_dir / "single_judge_subset.stats.json")]
                    steps.append(
                        {
                            "label": f"{c}: {name}",
                            "argv": argv,
                            "out": out,
                            "needs": run_dir / "relationships.json",
                            "prepare": prep,
                        }
                    )
    elif stage == "real":
        for c in REAL:
            d = root / "outputs" / c
            common = py + [
                "cdlp.validation",
                "--relationships",
                str(d / "relationships.json"),
                "--concepts",
                str(d / "concepts.json"),
                "--chunks",
                str(d / "chunks.jsonl"),
                "--necessity-sample",
                str(NECESSITY_SAMPLE),
                "--necessity-seed",
                str(NECESSITY_SEED),
            ]
            steps.append(
                {
                    "label": f"{c}: full agent (necessity report-only, sample 40)",
                    "argv": common + ["--out", str(d / "validated_graph.json")],
                    "out": d / "validated_graph.json",
                    "needs": d / "relationships.json",
                }
            )
            steps.append(
                {
                    "label": f"{c}: agent + necessity (weight 1, same sample)",
                    "argv": common
                    + [
                        "--necessity-weight",
                        "1",
                        "--setting",
                        "full_agent_plus_necessity",
                        "--out",
                        str(d / "validated_plus_necessity.json"),
                    ],
                    "out": d / "validated_plus_necessity.json",
                    "needs": d / "relationships.json",
                }
            )
    else:
        raise ValueError(f"unknown stage {stage!r}; choose from {STAGES}")
    return steps


def _needs(step: dict) -> list[Path]:
    needs = step["needs"]
    return needs if isinstance(needs, list) else [needs]


def _append(log: Path | None, row: dict) -> None:
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps(row) + "\n")


def run_stage(
    stage: str,
    root: Path = ROOT,
    force: bool = False,
    runner=subprocess.run,
    course: str | None = None,
    steps: list[str] | None = None,
    raw: Path | None = None,
    log: Path | None = None,
    before_step=None,
) -> list:
    """Run the plan in order. Done steps are skipped. A missing input is reported and skipped,
    except in a course, where each step needs the one before: there it stops the run."""
    report = []
    todo = plan(stage, root, course, steps, raw)
    for i, step in enumerate(todo, 1):
        head = f"[{i}/{len(todo)}] {step['label']}"
        stop = step.get("stop_on_failure")
        if usable(step["out"]) and not force:  # an uploaded result needs no input of its own
            problem = step["check"](step["out"]) if step.get("check") else None
            if problem:
                print(f"{head}: STOP, {problem}", flush=True)
                report.append((step["label"], "wrong kind of run"))
                break
            print(f"{head}: done already ({step['out'].name})", flush=True)
            report.append((step["label"], "done"))
            continue
        missing = [p for p in _needs(step) if not p.exists()]
        if missing:
            print(f"{head}: {'STOP' if stop else 'SKIP'}, input missing: {missing[0]}", flush=True)
            report.append((step["label"], "missing input"))
            if stop:
                break
            continue
        if step["out"].exists() and not force:
            print(f"{head}: {step['out'].name} is cut short or invalid: running again", flush=True)
        if step.get("prepare"):
            step["prepare"]()
        if before_step:
            before_step(step)
        start = time.monotonic()
        print(f"{head}: running", flush=True)
        argv = step["argv"]() if callable(step["argv"]) else step["argv"]
        result = runner(argv, cwd=root)
        status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        if status == "ok" and step.get("then") and (extra := step["then"]()):
            result = runner(extra, cwd=root)
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        if status == "ok" and stop and not usable(step["out"]):
            status = "no valid output"
            print(
                f"{head}: exited cleanly but {step['out'].name} is missing or invalid", flush=True
            )
        if status == "ok" and step.get("check"):
            problem = step["check"](step["out"])
            if problem:
                status = "wrong kind of run"
                print(f"{head}: {problem}", flush=True)
        seconds = time.monotonic() - start
        print(f"{head}: {status} in {seconds:.0f} s", flush=True)
        _append(
            log,
            {"kind": "step", "label": step["label"], "seconds": round(seconds), "status": status},
        )
        report.append((step["label"], status))
        if status != "ok" and stop:
            break
    return report


def progress(
    stage: str,
    root: Path = ROOT,
    course: str | None = None,
    steps: list[str] | None = None,
    raw: Path | None = None,
) -> dict:
    todo = plan(stage, root, course, steps, raw)
    done = [s["label"] for s in todo if usable(s["out"])]
    cache = root / ".cache" / "llm"
    return {
        "stage": stage,
        "steps_done": len(done),
        "steps_total": len(todo),
        "done": done,
        "todo": [s["label"] for s in todo if not usable(s["out"])],
        "cached_llm_calls": len(list(cache.glob("*.json"))) if cache.exists() else 0,
    }


# --- measured time --------------------------------------------------------------------
def timing(log: Path) -> dict:
    """Seconds per call per call type, and time per step, over every session of this stage."""
    rows = []
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:  # the last line of a session that was cut off
                continue
    types: dict[tuple, dict] = {}
    for row in (r for r in rows if r.get("kind") == "call"):
        one = types.setdefault(
            (row["prompt_version"], row["model"]), {"new_calls": 0, "cache_hits": 0, "seconds": 0.0}
        )
        one["cache_hits" if row["cached"] else "new_calls"] += 1
        one["seconds"] += 0 if row["cached"] else row["seconds"]
    steps = [r for r in rows if r.get("kind") == "step"]
    return {
        "call_types": [
            {
                "call_type": prompt_version,
                "model": model,
                **{k: v for k, v in one.items() if k != "seconds"},
                "seconds_per_new_call": (
                    round(one["seconds"] / one["new_calls"], 2) if one["new_calls"] else None
                ),
                "total_seconds": round(one["seconds"]),
            }
            for (prompt_version, model), one in sorted(types.items())
        ],
        "steps": [{k: r[k] for k in ("label", "seconds", "status")} for r in steps],
        "total_seconds": sum(r["seconds"] for r in steps),
    }


def print_timing(report: dict) -> None:
    print("\nMeasured time, over every session of this stage:")
    print(
        f"  {'call type':34s} {'model':22s} {'new':>5s} {'saved':>6s} "
        f"{'s/call':>7s} {'total s':>8s}"
    )
    for row in report["call_types"]:
        per_call = row["seconds_per_new_call"]
        print(
            f"  {row['call_type']:34s} {row['model']:22s} {row['new_calls']:5d} "
            f"{row['cache_hits']:6d} {'-' if per_call is None else f'{per_call:.2f}':>7s} "
            f"{row['total_seconds']:8d}"
        )
    for step in report["steps"]:
        print(f"  {step['label']}: {step['seconds']} s ({step['status']})")
    print(f"  total for this stage: {report['total_seconds']} s", flush=True)


def stage_log(stage: str, root: Path, course: str | None) -> Path:
    if course:
        return root / "outputs" / course / "colab_calls.jsonl"
    return root / "outputs" / f"colab_calls_{stage}.jsonl"


# --- what a course run produced -------------------------------------------------------
def course_report(root: Path, course: str) -> dict:
    """The facts to read after a course run, from the files it wrote."""
    d = root / "outputs" / course

    def read(name: str) -> dict:
        path = d / name
        return json.loads(path.read_text()) if usable(path) else {}

    discovery = read("relationships.json").get("discovery", {})
    graph = read("validated_graph.json")
    generation = read("quiz_items.json").get("generation", {})
    decisions: dict[str, int] = {}
    for edge in graph.get("edges", []):
        decisions[edge["decision"]] = decisions.get(edge["decision"], 0) + 1
    return {
        "course": course,
        "concepts": len(read("concepts.json").get("concepts", [])),
        "both_orders": discovery.get("both_orders"),
        "decisions": decisions,
        "necessity_edges_run": sum(
            e.get("necessity_gap") is not None for e in graph.get("edges", [])
        ),
        "skipped_checks": graph.get("skipped_checks"),
        "quiz_prompt_version": generation.get("prompt_version"),
        "quiz_items": len(read("quiz_items.json").get("items", [])),
        "drop_rate_by_level": generation.get("drop_rate_by_level"),
        "concepts_missing_level": generation.get("concepts_missing_level"),
        "retried_only_for_missing_level": generation.get("retried_only_for_missing_level"),
        "topics_retried": generation.get("topics_retried"),
    }


# --- moving files --------------------------------------------------------------------
def where_to_put(zip_name: str, course: str) -> str:
    """Exact steps on the laptop, so the website lists the course."""
    return f"""
On your laptop, in the repo folder:
  1. Download {zip_name} from Google Drive (My Drive > cdlp) to your Downloads folder.
  2. If outputs/{course} already exists, keep it out of the way (a name starting with _ is hidden):
       mv outputs/{course} outputs/_old_{course}
  3. Unzip it:
       unzip -o ~/Downloads/{zip_name} -d .
     The files land in outputs/{course}/. The folder name must stay {course}.
  4. The website lists the course once outputs/{course}/ holds concepts.json and
     validated_graph.json. Reload the page; pick it on Home. Ollama can stay off."""


def zip_course(root: Path, course: str, dest: Path, stamp: str | None = None) -> Path:
    """Only this course's outputs. Refuses a course the website could not fully use."""
    d = root / "outputs" / course
    broken = [name for name in WEBSITE_FILES if not usable(d / name)]
    if broken:
        raise SystemExit(f"{d} is not finished: missing or invalid {broken}. Nothing was zipped.")
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"course_{course}_{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(p for p in d.rglob("*") if p.is_file() and p.suffix != ".tmp"):
            z.write(path, Path("outputs") / course / path.relative_to(d))
    return out


def pack_start(
    course: str,
    concepts: Path,
    chunks: Path,
    caches: list[Path],
    out: Path,
    expect_concepts: int | None = None,
    extras: list[Path] | None = None,
) -> dict:
    """The upload zip: course files under outputs/<course>/, saved replies under cache/llm/.

    Checked first, because a wrong file here means paying for every call again, or results from
    the wrong list of concepts.
    """
    data = json.loads(concepts.read_text())
    n = len(data["concepts"])
    if expect_concepts is not None and n != expect_concepts:
        raise SystemExit(f"{concepts} has {n} concepts, not {expect_concepts}. Nothing was packed.")
    if data["course_id"] != course:
        raise SystemExit(f"{concepts} is for {data['course_id']}, not {course}.")
    problems = check(data, "concepts") + check_file(chunks)
    ids = {json.loads(line)["chunk_id"] for line in chunks.read_text().splitlines() if line.strip()}
    cited = {s["chunk_id"] for c in data["concepts"] for s in c["sources"] if s.get("chunk_id")}
    if cited - ids:
        problems.append(f"{len(cited - ids)} cited chunks are not in {chunks}")
    if problems:
        raise SystemExit("Nothing was packed:\n  " + "\n  ".join(problems[:5]))
    saved = {p.name: p for cache in caches for p in sorted(cache.glob("*.json"))}
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(concepts, f"outputs/{course}/concepts.json")
        z.write(chunks, f"outputs/{course}/chunks.jsonl")
        for extra in extras or []:
            z.write(extra, f"outputs/{course}/{extra.name}")
        for name, path in saved.items():
            z.write(path, f"cache/llm/{name}")
    return {"zip": str(out), "concepts": n, "chunks": len(ids), "saved_replies": len(saved)}


# --- environment and speed ------------------------------------------------------------
def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _tags() -> dict:
    try:
        import requests

        base = os.getenv("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
        return requests.get(f"{base}/api/tags", timeout=10).json()
    except Exception:
        return {}


def _model_entry(model: str, tags: dict) -> dict:
    for m in tags.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return m
    return {}


def model_digest(model: str, tags: dict | None = None) -> str | None:
    """Digest of an Ollama model from /api/tags (passed in for tests)."""
    return _model_entry(model, _tags() if tags is None else tags).get("digest")


def require_gpu() -> str:
    """Every stage needs one: on a CPU the runs would take days and look like a hang."""
    gpu = _out(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if not gpu:
        raise SystemExit("No GPU found: Runtime > Change runtime type > T4 GPU > Save, then rerun.")
    return gpu


def require_models(tags: dict | None = None) -> dict:
    """Exactly these two models, each with a digest to record, or the run does not start."""
    tags = _tags() if tags is None else tags
    found = {m: _model_entry(m, tags) for m in MODELS}
    missing = [m for m, entry in found.items() if not entry.get("digest")]
    if missing:
        raise SystemExit(f"Model not pulled, so no digest to record: {missing}. Run step 2.")
    return {m: {"digest": e["digest"], "size_bytes": e.get("size")} for m, e in found.items()}


def embedding_model_folder() -> Path:
    """Where extraction looks (cdlp/extraction/extract.py). It ignores HF_HOME, so this does too:
    a model downloaded anywhere else would pass here and then be refused inside a step."""
    name = "models--" + EMBEDDING_MODEL.replace("/", "--")
    return Path.home() / ".cache" / "huggingface" / "hub" / name


def embedding_model_revision() -> str | None:
    """The revision the modules will load, or None. They all load through refs/main, so that is
    what counts. An interrupted download has no usable weights."""
    folder = embedding_model_folder()
    try:
        revision = (folder / "refs" / "main").read_text().strip()
    except OSError:
        return None
    if not revision:
        return None
    snapshot = folder / "snapshots" / revision
    has_weights = any((snapshot / n).exists() for n in ("model.safetensors", "pytorch_model.bin"))
    return revision if has_weights and (snapshot / "modules.json").exists() else None


def require_embedding_model() -> str:
    """Caught here at the start, not inside a step. Extraction's refusal to fall back stays."""
    revision = embedding_model_revision()
    if revision == EMBEDDING_REVISION:
        return revision
    if revision:
        raise SystemExit(
            f"The embedding model {EMBEDDING_MODEL} is at revision {revision}, but this project is "
            f"pinned to {EMBEDDING_REVISION}, which produced the existing concept list. Another "
            "revision could merge concepts differently. Run step 3 of the notebook, then rerun."
        )
    message = (
        f"The embedding model {EMBEDDING_MODEL} is not downloaded in "
        f"{embedding_model_folder()}. Run step 3 of the notebook, which downloads it, then rerun."
    )
    if os.getenv("HF_HOME"):
        message += (
            f" HF_HOME is set to {os.environ['HF_HOME']}, but extraction only looks in the "
            "folder above, so unset HF_HOME and download it again."
        )
    raise SystemExit(message)


def both_models_fit(gpu: str | None, models: dict) -> bool:
    """Both sets of weights plus a margin fit in the GPU's memory. Unknown means no."""
    found = re.search(r"(\d+)\s*MiB", gpu or "")
    sizes = [m.get("size_bytes") for m in models.values()]
    if not found or None in sizes:
        return False
    return sum(sizes) / 2**20 + GPU_MARGIN_MIB <= int(found.group(1))


def unload_other_models(step: dict, fit: bool, runner=subprocess.run) -> None:
    """One model loaded at a time unless both fit. Within a quiz step Ollama swaps by itself."""
    if fit:
        return
    wanted = set(step.get("models", []))
    for line in _out(["ollama", "ps"]).splitlines()[1:]:
        model = line.split()[0] if line.split() else ""
        if model and model not in wanted:
            runner(["ollama", "stop", model])
            print(f"unloaded {model} (one model at a time)", flush=True)


def environment(model: str, stage: str | None = None, course: str | None = None) -> dict:
    gpu = _out(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    )
    tags = _tags()
    models = {
        m: {"digest": model_digest(m), "size_bytes": _model_entry(m, tags).get("size")}
        for m in MODELS
    }
    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        "course": course,
        "gpu": gpu or None,
        "ollama_version": _out(["ollama", "--version"]) or None,
        "model": model,
        "model_digest": model_digest(model),
        "models": models,
        "both_models_fit": both_models_fit(gpu, models),
        "embedding_model": {"name": EMBEDDING_MODEL, "revision": embedding_model_revision()},
        "repo_commit": _out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]) or None,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def record_environment(env: dict, out_dir: Path) -> Path:
    """Append this run's environment to <out_dir>/colab_environment.json (a list)."""
    path = Path(out_dir) / "colab_environment.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(path.read_text()) if path.exists() else []
    runs.append(env)
    path.write_text(json.dumps(runs, indent=2) + "\n")
    return path


def _speed_prompt(kind: str, i: int) -> str:
    if kind == "long":
        return (
            f"Write 3 multiple-choice questions about sorting algorithm number {i}. Give each 4 "
            'options and a reason. Reply only JSON: {"items": [{"question": "...", '
            '"options": ["..."], "answer": "...", "reason": "..."}]}'
        )
    return f'Reply only JSON {{"n": {i}}}: what is {i} + 1?'


def measure_speed(model: str, calls: int = 10, chat_json=None, kind: str = "short") -> dict:
    """Seconds per call, with a throwaway cache so nothing real is touched. The first call also
    loads the model, so it is reported apart from the rest."""
    tmp = tempfile.mkdtemp(prefix="speedtest-cache-")
    from cdlp.shared import llm

    old = llm.CACHE_DIR
    llm.CACHE_DIR = Path(tmp)
    ask = chat_json or llm.chat_json
    times = []
    try:
        for i in range(calls):
            start = time.monotonic()
            ask(_speed_prompt(kind, i), model=model, prompt_version=f"speedtest_{kind}")
            times.append(time.monotonic() - start)
    finally:
        llm.CACHE_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)
    warm = times[1:] or times
    return {
        "model": model,
        "kind": kind,
        "calls": len(times),
        "first_call_s": round(times[0], 2) if times else None,
        "warm_mean_s": round(sum(warm) / len(warm), 2) if warm else None,
    }


def speed_stage(out_dir: Path, measure=measure_speed, unload=None) -> list[dict]:
    """10 short and 5 long calls for each model, printing seconds per call."""
    rows = []
    for model in MODELS:
        if unload:
            unload({"models": [model]})
        for kind, calls in (("short", SHORT_CALLS), ("long", LONG_CALLS)):
            row = measure(model, calls, kind=kind)
            rows.append(row)
            print(
                f"{model:22s} {kind:5s} {row['calls']:2d} calls: "
                f"{row['warm_mean_s']} s per call (first call {row['first_call_s']} s)",
                flush=True,
            )
    path = Path(out_dir) / "colab_speed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(path.read_text()) if usable(path) else []
    history.append({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows})
    path.write_text(json.dumps(history, indent=2) + "\n")
    return rows


def _run_stage_command(args, parser) -> None:
    stage, course = args.stage, args.course
    if stage == "course" and not course:
        parser.error("the course stage needs --course")
    try:
        steps = parse_steps(args.steps) if stage == "course" else None
    except ValueError as exc:
        parser.error(str(exc))
    require_gpu()
    models = require_models()
    require_embedding_model()
    env = environment(VALIDATOR_MODEL, stage, course)
    out_dir = ROOT / "outputs" / course if course else args.out_dir
    print(f"recorded environment -> {record_environment(env, out_dir)}")
    print(f"GPU: {env['gpu']}")
    for name, info in models.items():
        print(f"{name}: {info['digest']}")
    print(f"{EMBEDDING_MODEL}: {env['embedding_model']['revision']}")
    print(f"both models fit on the GPU: {env['both_models_fit']}")
    log = stage_log(stage, ROOT, course)
    log.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        LLM_MODEL=DISCOVERY_MODEL,
        LLM_VALIDATOR_MODEL=VALIDATOR_MODEL,
        LLM_CALL_LOG=str(log),
        # Discovery and validation load the embedding model by name, so online they could fetch a
        # newer revision if the hub moves. Offline they can only use the pinned copy just checked.
        HF_HUB_OFFLINE="1",
    )
    report = run_stage(
        stage,
        force=args.force,
        course=course,
        steps=steps,
        raw=args.raw_dir,
        log=log,
        before_step=partial(unload_other_models, fit=env["both_models_fit"]),
    )
    summary = timing(log)
    (log.with_suffix(".summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
    print_timing(summary)
    print(json.dumps(progress(stage, ROOT, course, steps, args.raw_dir), indent=2))
    if course:
        print(json.dumps(course_report(ROOT, course), indent=2))
    failed = [label for label, status in report if status not in ("ok", "done", "missing input")]
    stopped = course and any(status == "missing input" for _, status in report)
    if failed or stopped:
        sys.exit(f"failed steps: {[label for label, s in report if s not in ('ok', 'done')]}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["env", "speed", "run", "stage", "progress", "report", "zip", "pack"]
    )
    parser.add_argument("name", nargs="?", help="with `stage`: speed or a stage name")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--course", help="course id, for the course stage, report and zip")
    parser.add_argument("--steps", help=f"course stage: any of {','.join(COURSE_STEPS)}")
    parser.add_argument("--raw-dir", type=Path, help="course files, default data/raw/<course>/")
    parser.add_argument("--model", default=os.getenv("LLM_VALIDATOR_MODEL", VALIDATOR_MODEL))
    parser.add_argument("--calls", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--force", action="store_true", help="rerun steps whose output exists")
    parser.add_argument("--dest", type=Path, help="zip: where to write the zip")
    parser.add_argument("--concepts", type=Path, help="pack: the concepts.json to upload")
    parser.add_argument("--chunks", type=Path, help="pack: the chunks.jsonl to upload")
    parser.add_argument("--extra", type=Path, action="append", help="pack: another course file")
    parser.add_argument("--cache", type=Path, action="append", help="pack: a folder of LLM replies")
    parser.add_argument("--zip", type=Path, help="pack: the zip to write")
    parser.add_argument("--expect-concepts", type=int, help="pack: stop unless this many concepts")
    args = parser.parse_args(argv)

    if args.command == "stage":
        if args.name == "speed":
            args.command = "speed"
        elif args.name in STAGES:
            args.command, args.stage = "run", args.name
        else:
            parser.error(f"stage: choose from speed, {', '.join(STAGES)}")
    if args.command in ("run", "progress") and not args.stage:
        parser.error(f"{args.command} needs --stage")
    if args.command in ("report", "zip") and not args.course:
        parser.error(f"{args.command} needs --course")

    if args.command == "env":
        env = environment(args.model, args.stage, args.course)
        print(json.dumps(env, indent=2))
        print(f"-> {record_environment(env, args.out_dir)}")
    elif args.command == "speed":
        require_gpu()
        models = require_models()
        require_embedding_model()
        fit = both_models_fit(environment(args.model)["gpu"], models)
        speed_stage(args.out_dir, unload=partial(unload_other_models, fit=fit))
    elif args.command == "run":
        _run_stage_command(args, parser)
    elif args.command == "report":
        print(json.dumps(course_report(ROOT, args.course), indent=2))
    elif args.command == "zip":
        out = zip_course(ROOT, args.course, args.dest or ROOT)
        print(f"Wrote {out} (only outputs/{args.course}/)")
        print(where_to_put(out.name, args.course))
    elif args.command == "pack":
        if not (args.course and args.concepts and args.chunks and args.zip):
            parser.error("pack needs --course, --concepts, --chunks and --zip")
        done = pack_start(
            args.course,
            args.concepts,
            args.chunks,
            args.cache or [],
            args.zip,
            args.expect_concepts,
            args.extra,
        )
        print(json.dumps(done, indent=2))
    else:
        steps = parse_steps(args.steps) if args.stage == "course" else None
        print(json.dumps(progress(args.stage, ROOT, args.course, steps, args.raw_dir), indent=2))


if __name__ == "__main__":
    main()
