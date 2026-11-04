"""Draws the paper's result figures for a one-column IEEE layout, from the results files only.

White background, serif text and a colour-blind-safe palette. Each figure shows its values.
Run from the repo root with the project venv.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / "figures"
WIDTH = 3.4
COLORS = ["#0072B2", "#D55E00", "#009E73"]  # blue, orange, green: safe for colour blindness

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "savefig.dpi": 600,
        "savefig.facecolor": "white",
    }
)


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def clean(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", linewidth=0.3, color="0.8")


def save(fig, name: str) -> None:
    fig.tight_layout(pad=0.5)
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    print("wrote", name)


def bar_labels(ax, bars, values, digits=2, size=6.5):
    for bar, value in zip(bars, values, strict=True):
        if value:
            ax.annotate(
                f"{value:.{digits}f}",
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 1.5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=size,
            )


def necessity() -> None:
    settings = []
    for run in ("necessity_stability", "necessity_stability_open5_qt07"):
        data = load(f"cdlp/validation/results/{run}/summary.json")
        settings += data["settings"]
    edges = [
        ("binary_tree -> binary_search_tree", "BT \u2192 BST (hard)"),
        ("recursion -> binary_tree", "Recursion \u2192 BT (soft)"),
        ("graphs -> avl_tree", "Graphs \u2192 AVL (none)"),
    ]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.15))
    width = 0.27
    for i, (edge, label) in enumerate(edges):
        rows = [next(e for e in st["edges"].values() if e["edge"] == edge) for st in settings]
        means = [row["mean"] for row in rows]
        sds = [row.get("sd") or 0 for row in rows]
        xs = [x + (i - 1) * width for x in range(len(settings))]
        ax.bar(
            xs,
            means,
            width,
            yerr=sds,
            label=label,
            color=COLORS[i],
            error_kw={"elinewidth": 0.7, "capsize": 1.5, "capthick": 0.7, "ecolor": "0.25"},
        )
        for x, mean, sd in zip(xs, means, sds, strict=True):
            if mean:  # a zero gap has no bar to label; the text and x axis show it
                ax.annotate(
                    f"{mean:.2f}",
                    (x, mean + sd),
                    xytext=(0, 1.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    rotation=90,
                    fontsize=6,
                )
    names = [
        f"{'Open' if st['question_format'] == 'open' else 'MCQ'}\nn={st['n_questions']}"
        for st in settings
    ]
    names[-1] += "*"
    ax.set_xticks(range(len(settings)), names)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_ylabel("Necessity gap (mean \u00b1 SD)")
    ax.set_ylim(top=0.68)
    ax.legend(
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.46, 1.0),
        handlelength=1.1,
        columnspacing=0.7,
        handletextpad=0.3,
        fontsize=7,
    )
    clean(ax)
    save(fig, "fig_necessity.png")


def rq2() -> None:
    data = load("cdlp/learning_path/results/rq2_rq4_results.json")
    conditions = [
        ("rq2_diagnosis", "Knowledge follows the graph"),
        ("rq2_diagnosis_independent", "Knowledge ignores the graph"),
    ]
    strategies = [
        ("adaptive", "Adaptive"),
        ("ask_all", "Ask every concept"),
        ("random", "Random, same budget"),
    ]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.15))
    width = 0.27
    for i, (strategy, label) in enumerate(strategies):
        rows = [data[key][strategy] for key, _ in conditions]
        xs = [x + (i - 1) * width for x in range(len(conditions))]
        accuracy = [row["accuracy"] for row in rows]
        bars = ax.bar(xs, accuracy, width, label=label, color=COLORS[i])
        bar_labels(ax, bars, accuracy, digits=3, size=6.5)
        for bar, row in zip(bars, rows, strict=True):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                0.05,
                f"{row['avg_questions']:.2f} questions",
                rotation=90,
                ha="center",
                va="bottom",
                color="white",
                fontsize=7,
            )
    ax.set_xticks(range(len(conditions)), [name for _, name in conditions])
    ax.set_ylabel("Diagnosis accuracy")
    ax.set_ylim(0, 1.0)
    ax.legend(
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.46, 1.0),
        handlelength=1.1,
        columnspacing=0.7,
        handletextpad=0.3,
        fontsize=7,
    )
    clean(ax)
    save(fig, "fig_rq2.png")


def kappa() -> None:
    pairs = load("data/gold/agreement.json")["pairs"]
    rows = [p for p in pairs if sorted(p["annotators"]) == ["a", "c"]]
    order = {"all": 0, "ds101": 1, "ml101": 2}
    rows.sort(key=lambda p: order[p["scope"]])
    names = {"all": "All (20 pairs)", "ds101": "ds101 (10)", "ml101": "ml101 (10)"}
    fig, ax = plt.subplots(figsize=(WIDTH, 1.75))
    width = 0.34
    series = [("kappa_raw", "Raw"), ("kappa_shortcut_rule", "After shortcut rule")]
    for i, (key, label) in enumerate(series):
        xs = [x + (i - 0.5) * width for x in range(len(rows))]
        values = [p[key] for p in rows]
        bars = ax.bar(xs, values, width, label=label, color=COLORS[i])
        bar_labels(ax, bars, values, size=7)
    ax.set_xticks(range(len(rows)), [names[p["scope"]] for p in rows])
    ax.set_ylabel("Cohen's \u03ba")
    ax.set_ylim(0, 1.18)
    ax.legend(frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    clean(ax)
    save(fig, "fig_kappa.png")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    necessity()
    rq2()
    kappa()
