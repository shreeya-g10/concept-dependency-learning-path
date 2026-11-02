"""Validator stages for Colab (notebooks/colab_validator.ipynb), runnable anywhere.

    python scripts/colab_run.py env      [--model llama3.1:8b] [--out-dir outputs]
    python scripts/colab_run.py speed    [--model llama3.1:8b] [--calls 10]
    python scripts/colab_run.py run      --stage night2|night3|real [--force]
    python scripts/colab_run.py progress --stage night2|night3|real

Stages (validator model only; discovery and extraction ran locally on qwen):
  night2  benchmarks: single judge and the reported agent (semantic + graph checks,
          --skip-evidence --skip-necessity) on every proposed edge of each graph.
  night3  benchmarks: self-consistency on the 100-pair subset's proposed edges, and the
          single judge on the same subset (cache hits after night 2).
  real    ds101 / ml101: the full agent with necessity on a seeded sample of 40 proposed
          edges (report-only), then the same agent with necessity at weight 1 (cache hits).

Every step whose output already exists is skipped, and every LLM call is cached, so a
Colab disconnect loses at most the call in flight: run the same stage again to resume.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python scripts/colab_run.py` puts only scripts/ on the path
    sys.path.insert(0, str(ROOT))
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
STAGES = ("night2", "night3", "real")


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


# --- stage plans ----------------------------------------------------------------------
def plan(stage: str, root: Path = ROOT) -> list[dict]:
    """Ordered steps: {label, argv, out, prepare (callable or None)}."""
    py = [sys.executable, "-m"]
    steps = []
    if stage in ("night2", "night3"):
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


def run_stage(stage: str, root: Path = ROOT, force: bool = False, runner=subprocess.run) -> list:
    """Run the plan in order. Missing inputs are reported and skipped; done steps too."""
    report = []
    for i, step in enumerate(plan(stage, root), 1):
        head = f"[{i}/{len(plan(stage, root))}] {step['label']}"
        if not step["needs"].exists():
            print(f"{head}: SKIP, input missing: {step['needs']}", flush=True)
            report.append((step["label"], "missing input"))
            continue
        if step["out"].exists() and not force:
            print(f"{head}: done already ({step['out'].name})", flush=True)
            report.append((step["label"], "done"))
            continue
        if step.get("prepare"):
            step["prepare"]()
        start = time.monotonic()
        print(f"{head}: running", flush=True)
        result = runner(step["argv"], cwd=root)
        status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        print(f"{head}: {status} in {time.monotonic() - start:.0f} s", flush=True)
        report.append((step["label"], status))
    return report


def progress(stage: str, root: Path = ROOT) -> dict:
    steps = plan(stage, root)
    done = [s["label"] for s in steps if s["out"].exists()]
    cache = root / ".cache" / "llm"
    return {
        "stage": stage,
        "steps_done": len(done),
        "steps_total": len(steps),
        "done": done,
        "todo": [s["label"] for s in steps if not s["out"].exists()],
        "cached_llm_calls": len(list(cache.glob("*.json"))) if cache.exists() else 0,
    }


# --- environment and speed ------------------------------------------------------------
def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def model_digest(model: str, tags: dict | None = None) -> str | None:
    """Digest of an Ollama model from /api/tags (passed in for tests)."""
    if tags is None:
        try:
            import requests

            base = os.getenv("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
            tags = requests.get(f"{base}/api/tags", timeout=10).json()
        except Exception:
            return None
    for m in tags.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return m.get("digest")
    return None


def environment(model: str, stage: str | None = None) -> dict:
    gpu = _out(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    )
    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        "gpu": gpu or None,
        "ollama_version": _out(["ollama", "--version"]) or None,
        "model": model,
        "model_digest": model_digest(model),
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


def measure_speed(model: str, calls: int = 10, chat_json=None) -> dict:
    """Seconds per short call, with a throwaway cache so nothing real is touched."""
    tmp = tempfile.mkdtemp(prefix="speedtest-cache-")
    from cdlp.shared import llm

    old = llm.CACHE_DIR
    llm.CACHE_DIR = Path(tmp)
    ask = chat_json or llm.chat_json
    times = []
    try:
        for i in range(calls):
            prompt = f'Reply only JSON {{"n": {i}}}: what is {i} + 1?'
            start = time.monotonic()
            ask(prompt, model=model, prompt_version="speedtest")
            times.append(time.monotonic() - start)
    finally:
        llm.CACHE_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)
    warm = times[1:] or times
    return {
        "model": model,
        "calls": len(times),
        "first_call_s": round(times[0], 2) if times else None,
        "warm_mean_s": round(sum(warm) / len(warm), 2) if warm else None,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["env", "speed", "run", "progress"])
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--model", default=os.getenv("LLM_VALIDATOR_MODEL", "llama3.1:8b"))
    parser.add_argument("--calls", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--force", action="store_true", help="rerun steps whose output exists")
    args = parser.parse_args(argv)
    if args.command in ("run", "progress") and not args.stage:
        parser.error(f"{args.command} needs --stage")

    if args.command == "env":
        env = environment(args.model, args.stage)
        print(json.dumps(env, indent=2))
        print(f"-> {record_environment(env, args.out_dir)}")
    elif args.command == "speed":
        print(json.dumps(measure_speed(args.model, args.calls), indent=2))
    elif args.command == "run":
        env = environment(args.model, args.stage)
        print(f"recorded environment -> {record_environment(env, args.out_dir)}")
        report = run_stage(args.stage, force=args.force)
        failed = [label for label, status in report if status.startswith("exit")]
        print(json.dumps(progress(args.stage), indent=2))
        if failed:
            sys.exit(f"failed steps: {failed}")
    else:
        print(json.dumps(progress(args.stage), indent=2))


if __name__ == "__main__":
    main()
