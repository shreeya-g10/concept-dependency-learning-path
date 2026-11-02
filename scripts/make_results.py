"""Collect every results/*.json into the paper's tables and figures.

    python scripts/make_results.py [--root .] [--out docs/paper/results]

Writes, all regenerated on every run (no timestamps, so a rerun on unchanged results
changes nothing):
- tables.md   markdown tables, one section per paper table
- tables.tex  the same tables as LaTeX (booktabs)
- figures/*.png  matplotlib figures (only for results that exist)
- manifest.json  every results file found, the table/figure that used it, and what is
  still missing

A result that does not exist yet is never invented: its cells read [RESULT], the table
note names the missing file, and its figure is skipped and listed as missing.
Read-only on the results; no LLM call.

Sources (all optional):
- RQ1        cdlp/validation/results/rq1_<course>.json and rq1_<dataset>_micro.json; the
             expected courses and settings come from cdlp/validation/configs/rq1/
- RQ2, RQ4   cdlp/learning_path/results/rq2_rq4_results.json
- RQ3        cdlp/root_cause/results/*.json whose dataset is the gold test set
             (data/gold/root_cause_testset.json); dev-set runs are listed, never tabled
- κ          data/gold/merged/agreement.json (data/gold/merge_gold.py)
- extraction cdlp/extraction/results/evaluation_metrics.json
- necessity  cdlp/validation/results/necessity_stability*/summary.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

TESTSET = "data/gold/root_cause_testset.json"
CELL = "[RESULT]"  # a value whose results file does not exist yet

# Light-mode categorical slots 1-3 of the dataviz reference palette (validated all-pairs
# for <= 3 series); text and grid in neutral inks. Every figure has at most 3 series.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def placeholder(what: str) -> str:
    return f"[RESULT: {what}]"


def fmt(value, digits: int = 2, pct: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return (
            f"{value:.1f}%"
            if pct
            else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))
        )
    return str(value)


@dataclass
class Table:
    key: str
    title: str
    columns: list[str]
    rows: list[list[str]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    note: str = ""

    def add(self, cells: list, what: str) -> None:
        """None cells become the [RESULT] placeholder."""
        self.rows.append(
            [CELL if c is None else str(c) for c, col in zip(cells, self.columns, strict=True)]
        )


@dataclass
class Report:
    root: Path
    tables: list[Table] = field(default_factory=list)
    figures: dict[str, list[str]] = field(default_factory=dict)  # png -> sources
    missing: list[str] = field(default_factory=list)

    def load(self, rel: str) -> dict | None:
        path = self.root / rel
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


# ---- tables -------------------------------------------------------------------------


def rq1_tables(r: Report) -> list[tuple[Table, dict | None]]:
    cfg_dir = r.root / "cdlp/validation/configs/rq1"
    settings_file = cfg_dir / "settings.json"
    settings = (
        [s["name"] for s in json.loads(settings_file.read_text())["settings"]]
        if settings_file.is_file()
        else []
    )
    expected = []  # (label, result file)
    for cfg in sorted(cfg_dir.glob("*.json")) if cfg_dir.is_dir() else []:
        data = json.loads(cfg.read_text())
        courses = data.get("courses")
        if not courses:
            continue
        if len(courses) == 1:
            expected.append((courses[0]["course_id"], f"rq1_{courses[0]['course_id']}.json"))
        else:
            expected.append((f"{data['dataset']} (micro)", f"rq1_{data['dataset']}_micro.json"))
    # our own courses first, then the public benchmarks
    expected.sort(key=lambda e: (e[0] not in ("ds101", "ml101"), e[0]))
    out = []
    for label, name in expected:
        rel = f"cdlp/validation/results/{name}"
        data = r.load(rel)
        t = Table(
            f"rq1_{name[4:-5]}",
            f"RQ1 — edge quality on {label}",
            ["Setting", "P", "R", "F1", "HUMAN_REVIEW rate", "LLM calls / edge"],
        )
        if data is None:
            r.missing.append(rel)
            t.note = f"Missing: `{rel}` (python -m cdlp.validation.evaluate)."
            for s in settings:
                t.add([s, None, None, None, None, None], f"RQ1 {label} {s}")
        else:
            t.sources.append(rel)
            t.note = f"Scoring: {data.get('scoring')}."
            for row in data["rows"]:
                t.add(
                    [
                        row["setting"],
                        fmt(row.get("precision")),
                        fmt(row.get("recall")),
                        fmt(row.get("f1")),
                        fmt(row.get("human_review_rate")),
                        fmt(row.get("llm_calls_per_edge"), 1),
                    ],
                    f"RQ1 {label} {row['setting']}",
                )
        out.append((t, data))
    return out


RQ24 = "cdlp/learning_path/results/rq2_rq4_results.json"


def rq2_table(r: Report) -> tuple[Table, dict | None]:
    data = r.load(RQ24)
    t = Table(
        "rq2", "RQ2 — diagnosis on simulated students", ["Strategy", "Avg. questions", "Accuracy"]
    )
    names = {
        "adaptive": "Graph-guided adaptive",
        "ask_all": "Ask every concept",
        "random": "Random order (matched budget)",
    }
    diag = (data or {}).get("rq2_diagnosis", {})
    if data is None:
        r.missing.append(RQ24)
        t.note = f"Missing: `{RQ24}` (python -m cdlp.learning_path.evaluate)."
    else:
        t.sources.append(RQ24)
        t.note = (
            f"{data.get('num_students')} simulated students, target {data.get('target_concept')}, "
            f"mastery threshold {data.get('mastery_threshold', placeholder('mastery threshold'))}."
        )
    for key, label in names.items():
        row = diag.get(key, {})
        t.add([label, fmt(row.get("avg_questions")), fmt(row.get("accuracy"))], f"RQ2 {label}")
    return t, data


def rq4_table(r: Report, data: dict | None) -> Table:
    t = Table("rq4", "RQ4 — personalized vs. generic paths", ["Measure", "Value"])
    p = (data or {}).get("rq4_learning_path", {})
    if data is not None:
        t.sources.append(RQ24)
    for label, key, pct in [
        ("Generic path length (avg.)", "generic_avg_length", False),
        ("Personalized path length (avg.)", "personalized_avg_length", False),
        ("Path length reduction", "path_length_reduction_pct", True),
        ("Gap coverage", "avg_gap_coverage", False),
        ("Order violations (total)", "total_order_mistakes", False),
    ]:
        t.add([label, fmt(p.get(key), pct=pct)], f"RQ4 {label}")
    return t


def rq3_table(r: Report) -> Table:
    t = Table(
        "rq3",
        "RQ3 — root-cause tracing on the gold test set",
        ["Method", "Mastery", "n", "Top-1", "Top-3", "LLM fallbacks"],
    )
    dev = []
    for path in sorted((r.root / "cdlp/root_cause/results").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dataset = str(data.get("config", {}).get("dataset", ""))
        if not dataset.endswith(TESTSET):
            dev.append(r.rel(path))
            continue
        t.sources.append(r.rel(path))
        mastery = "yes" if data["config"].get("use_mastery") else "no"
        for row in data["results"]:
            t.add(
                [
                    row["method"],
                    mastery,
                    row.get("n"),
                    fmt(row.get("top1_accuracy")),
                    fmt(row.get("top3_accuracy")),
                    fmt(row.get("llm_fallbacks")),
                ],
                f"RQ3 {row['method']}",
            )
    if not t.rows:
        r.missing.append(f"cdlp/root_cause/results/<run on {TESTSET}>.json")
        t.note = f"Missing: a cdlp.root_cause.evaluate run on `{TESTSET}`. "
        for method in ["llm", "target", "nearest"]:
            t.add([method, None, None, None, None, None], f"RQ3 {method}")
    if dev:
        t.note += (
            "Not tabled (dev set, never reported as test): "
            + ", ".join(f"`{d}`" for d in dev)
            + "."
        )
    return t


AGREEMENT = "data/gold/merged/agreement.json"


def kappa_table(r: Report) -> tuple[Table, dict | None]:
    data = r.load(AGREEMENT)
    t = Table(
        "kappa",
        "Inter-annotator agreement (Cohen's κ, before adjudication)",
        ["Annotators", "Scope", "Pairs", "κ raw", "κ shortcut rule"],
    )
    if data is None:
        r.missing.append(AGREEMENT)
        t.note = f"Missing: `{AGREEMENT}` (python data/gold/merge_gold.py)."
        for scope in ["all", "ds101", "ml101"]:
            t.add([None, scope, None, None, None], f"κ {scope}")
        return t, None
    t.sources.append(AGREEMENT)
    for row in data["pairs"]:
        t.add(
            [
                " vs ".join(row["annotators"]),
                row["scope"],
                row["n_pairs"],
                fmt(row["kappa_raw"]),
                fmt(row["kappa_shortcut_rule"]),
            ],
            f"κ {row['scope']}",
        )
    changed = {
        a: sum(len(v) for v in per.values())
        for a, per in data["labels_changed_by_rule"].items()
        if any(per.values())
    }
    t.note = (
        f"Shortcut rule: {data['shortcut_rule']} Labels changed by the rule: "
        + (", ".join(f"annotator {a}: {n}" for a, n in changed.items()) or "none")
        + f". Unresolved ties before adjudication: {len(data['merge']['unresolved'])}."
    )
    return t, data


EXTRACTION = "cdlp/extraction/results/evaluation_metrics.json"


def extraction_table(r: Report) -> Table:
    data = r.load(EXTRACTION)
    t = Table(
        "extraction",
        "Concept extraction vs. hand-annotated concepts",
        ["Extracted", "Gold", "P", "R", "F1"],
    )
    c = (data or {}).get("concept_evaluation", {})
    if data is None:
        r.missing.append(EXTRACTION)
        t.note = f"Missing: `{EXTRACTION}`."
    else:
        t.sources.append(EXTRACTION)
    t.add(
        [
            c.get("extracted_count"),
            c.get("gold_count"),
            fmt(c.get("precision")),
            fmt(c.get("recall")),
            fmt(c.get("f1")),
        ],
        "extraction",
    )
    return t


def necessity_table(r: Report) -> tuple[Table, list[tuple[str, dict]]]:
    t = Table(
        "necessity",
        "Necessity-test stability (gap mean ± sd over seeds)",
        ["Run", "Format", "n", "Edge", "Gap mean", "Gap sd", "Order holds (means)"],
    )
    runs = []
    for path in sorted(
        (r.root / "cdlp/validation/results").glob("necessity_stability*/summary.json")
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        run = path.parent.name
        t.sources.append(r.rel(path))
        runs.append((run, data))
        for s in data.get("settings", []):
            for edge in s.get("edges", {}).values():
                t.add(
                    [
                        run,
                        s["question_format"],
                        s["n_questions"],
                        edge["edge"],
                        fmt(edge.get("mean")),
                        fmt(edge.get("sd")),
                        fmt(s.get("order_holds_on_means")),
                    ],
                    f"necessity {run}",
                )
    if not runs:
        r.missing.append("cdlp/validation/results/necessity_stability*/summary.json")
        t.add([None] * 7, "necessity stability")
    else:
        t.note = (
            "Examples graph (3 edges); expected order: "
            + str(runs[0][1].get("expected_order", ""))
            + "."
        )
    return t, runs


# ---- rendering ----------------------------------------------------------------------


def to_markdown(t: Table) -> str:
    lines = [f"## {t.title}", ""]
    lines.append("| " + " | ".join(t.columns) + " |")
    lines.append("|" + "---|" * len(t.columns))
    lines += ["| " + " | ".join(c.replace("|", "\\|") for c in row) + " |" for row in t.rows]
    if t.note:
        lines += ["", t.note]
    lines += ["", "Sources: " + (", ".join(f"`{s}`" for s in t.sources) or "none yet"), ""]
    return "\n".join(lines)


def tex_escape(text: str) -> str:
    out = text.replace("\\", "\x00")  # placeholder, so later escapes are not re-escaped
    for a, b in [
        ("{", r"\{"),
        ("}", r"\}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        out = out.replace(a, b)
    out = out.replace("\x00", r"\textbackslash{}")
    return (
        out.replace("±", r"$\pm$")
        .replace("κ", r"$\kappa$")
        .replace("—", "---")
        .replace("→", r"$\rightarrow$")
    )


def to_latex(t: Table) -> str:
    spec = "l" * len(t.columns)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{{tex_escape(t.title)}}}",
        rf"\label{{tab:{t.key}}}",
        r"\small",
        rf"\begin{{tabular}}{{{spec}}}",
        r"\toprule",
        " & ".join(tex_escape(c) for c in t.columns) + r" \\",
        r"\midrule",
    ]
    lines += [" & ".join(tex_escape(c) for c in row) + r" \\" for row in t.rows]
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


# ---- figures ------------------------------------------------------------------------


def _axes(plt, width=5.0, height=3.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig, out: Path, name: str, r: Report, sources: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out / name, facecolor=SURFACE, metadata={"Software": None})
    r.figures[f"figures/{name}"] = sources


def make_figures(
    r: Report, out: Path, rq1: list, rq24: dict | None, kappa: dict | None, necessity: list
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"font.size": 8, "text.color": INK, "axes.labelcolor": INK_2, "svg.hashsalt": "cdlp"}
    )

    diag = (rq24 or {}).get("rq2_diagnosis", {})
    if all("accuracy" in diag.get(k, {}) for k in ("adaptive", "ask_all", "random")):
        fig, ax = _axes(plt)
        for i, (key, label) in enumerate(
            [("adaptive", "Adaptive"), ("ask_all", "Ask every concept"), ("random", "Random order")]
        ):
            ax.scatter(
                diag[key]["avg_questions"],
                diag[key]["accuracy"],
                s=60,
                color=SERIES[i],
                edgecolors=SURFACE,
                linewidths=2,
                zorder=3,
                label=label,
            )
        ax.set_xlabel("Average questions asked")
        ax.set_ylabel("Diagnosis accuracy")
        ax.set_ylim(0, 1)
        ax.legend(frameon=False, fontsize=8, labelcolor=INK)
        _save(fig, out, "rq2_accuracy_vs_questions.png", r, [RQ24])
        plt.close(fig)
    else:
        r.missing.append("figures/rq2_accuracy_vs_questions.png")

    for table, data in rq1:
        name = f"{table.key}_precision_recall.png"
        rows = [x for x in (data or {}).get("rows", []) if x.get("status") == "ok"]
        if not rows:
            r.missing.append(f"figures/{name}")
            continue
        fig, ax = _axes(plt)
        ax.scatter(
            [x["recall"] for x in rows],
            [x["precision"] for x in rows],
            s=60,
            color=SERIES[0],
            edgecolors=SURFACE,
            linewidths=2,
            zorder=3,
        )
        for x in rows:
            ax.annotate(
                x["setting"],
                (x["recall"], x["precision"]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7,
                color=INK_2,
            )
        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_xlim(0, 1.05)
        ax.set_ylim(0, 1.05)
        _save(fig, out, name, r, table.sources)
        plt.close(fig)

    if kappa:
        scopes = [p for p in kappa["pairs"] if p["kappa_raw"] is not None]
        labels = [f"{'–'.join(p['annotators'])}\n{p['scope']}" for p in scopes]
        fig, ax = _axes(plt, width=max(4.0, 0.7 * len(scopes) + 1.5))
        xs = range(len(scopes))
        w = 0.38
        ax.bar(
            [x - w / 2 - 0.01 for x in xs],
            [p["kappa_raw"] for p in scopes],
            w,
            color=SERIES[0],
            label="raw",
        )
        ax.bar(
            [x + w / 2 + 0.01 for x in xs],
            [p["kappa_shortcut_rule"] or 0 for p in scopes],
            w,
            color=SERIES[1],
            label="shortcut rule",
        )
        ax.set_xticks(list(xs), labels, fontsize=7)
        ax.set_ylabel("Cohen's κ")
        ax.set_ylim(min(0, *(p["kappa_raw"] for p in scopes)), 1.05)
        ax.legend(frameon=False, fontsize=8, labelcolor=INK)
        _save(fig, out, "kappa_raw_vs_rule.png", r, [AGREEMENT])
        plt.close(fig)
    else:
        r.missing.append("figures/kappa_raw_vs_rule.png")

    if necessity:
        run, data = necessity[0]
        settings = data.get("settings", [])
        edges = list(settings[0]["edges"]) if settings else []
        if edges and len(edges) <= 3:
            fig, ax = _axes(plt, width=5.5)
            xs = range(len(settings))
            w = 0.8 / len(edges)
            for j, eid in enumerate(edges):
                vals = [s["edges"][eid] for s in settings]
                ax.bar(
                    [x + (j - (len(edges) - 1) / 2) * w for x in xs],
                    [v["mean"] for v in vals],
                    w * 0.92,
                    yerr=[v["sd"] for v in vals],
                    color=SERIES[j],
                    ecolor=INK_2,
                    capsize=2,
                    label=vals[0]["edge"],
                )
            ax.axhline(0, color=INK_2, linewidth=0.8)
            ax.set_xticks(
                list(xs), [f"{s['question_format']}, n={s['n_questions']}" for s in settings]
            )
            ax.set_ylabel("Necessity gap (mean ± sd)")
            ax.legend(frameon=False, fontsize=7, labelcolor=INK)
            _save(
                fig,
                out,
                "necessity_gap_stability.png",
                r,
                [f"cdlp/validation/results/{run}/summary.json"],
            )
            plt.close(fig)
    else:
        r.missing.append("figures/necessity_gap_stability.png")


# ---- main ---------------------------------------------------------------------------


def build(root: Path, out: Path, figures: bool = True) -> dict:
    r = Report(root)
    rq1 = rq1_tables(r)
    rq2, rq24 = rq2_table(r)
    kappa, agreement = kappa_table(r)
    necessity, runs = necessity_table(r)
    r.tables = [t for t, _ in rq1] + [
        rq2,
        rq3_table(r),
        rq4_table(r, rq24),
        kappa,
        extraction_table(r),
        necessity,
    ]
    if figures:
        make_figures(r, out / "figures", rq1, rq24, agreement, runs)

    out.mkdir(parents=True, exist_ok=True)
    header = (
        "<!-- Generated by scripts/make_results.py; do not edit by hand. -->\n"
        "# Paper tables\n\nCells reading [RESULT] have no results file yet.\n\n"
    )
    figs = "\n## Figures\n\n" + "".join(f"![{p}]({p})\n\n" for p in sorted(r.figures))
    (out / "tables.md").write_text(
        header + "\n".join(to_markdown(t) for t in r.tables) + figs, encoding="utf-8"
    )
    (out / "tables.tex").write_text(
        "% Generated by scripts/make_results.py; needs \\usepackage{booktabs}.\n\n"
        + "\n".join(to_latex(t) for t in r.tables),
        encoding="utf-8",
    )
    found = sorted(r.rel(p) for p in root.glob("cdlp/*/results/**/*.json")) + (
        [AGREEMENT] if (root / AGREEMENT).is_file() else []
    )
    used = {s for t in r.tables for s in t.sources} | {s for v in r.figures.values() for s in v}
    manifest = {
        "tables": {
            t.key: {
                "title": t.title,
                "sources": t.sources,
                "placeholders": sum(c == CELL for row in t.rows for c in row),
            }
            for t in r.tables
        },
        "figures": r.figures,
        "missing": sorted(set(r.missing)),
        "results_found": found,
        "results_not_used": [f for f in found if f not in used],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None, help="default: <root>/docs/paper/results")
    parser.add_argument("--no-figures", action="store_true", help="tables only (no matplotlib)")
    args = parser.parse_args(argv)
    out = args.out or args.root / "docs/paper/results"
    m = build(args.root, out, figures=not args.no_figures)
    holes = sum(t["placeholders"] for t in m["tables"].values())
    print(
        f"{len(m['tables'])} tables ({holes} [RESULT] cells), {len(m['figures'])} figures -> {out}"
    )
    for item in m["missing"]:
        print(f"  missing: {item}")


if __name__ == "__main__":
    main()
