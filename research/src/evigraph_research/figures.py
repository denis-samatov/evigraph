"""Paper figures from the JSON results (static PNG + SVG in reports/figures)."""

import sys

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import orjson
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

from evigraph_research import paths

# Reference palette (dataviz skill, light mode): slot 1 blue, slot 2 orange; recessive greys.
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SURFACE = "#fcfcfb"

OUT = paths.REPORTS / "figures"

SERIES = {
    # system: (label, colour, linestyle, marker)
    "C1_strong+knn": ("kNN, naive", BLUE, "-", "o"),
    "C1p_strong+knn_prov": ("kNN, provenance", BLUE, "--", "s"),
    "G1_strong+graph": ("citation graph, naive", ORANGE, "-", "o"),
    "G1p_strong+graph_prov": ("citation graph, provenance", ORANGE, "--", "s"),
}


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def risk_vs_copies(results_file: str) -> None:
    r = orjson.loads((paths.REPORTS / results_file).read_bytes())
    rows = [t for t in r["table"] if t["alpha"] == 0.1]
    copies = sorted({t["copies"] for t in rows if t["scenario"] == "dup"} | {0})
    noises = sorted({t["noise"] for t in rows if t["scenario"] == "dup"})

    def risk(system, noise, m):
        key = ("clean", 0.0, 0) if m == 0 else ("dup", noise, m)
        for t in rows:
            if (t["scenario"], t["noise"], t["copies"], t["system"]) == (*key, system):
                return t["risk_targets"], t.get("risk_targets_ci95")
        raise KeyError((system, noise, m))

    fig, axes = plt.subplots(1, len(noises), figsize=(10, 3.4), sharey=True, facecolor=SURFACE)
    for ax, noise in zip(axes, noises, strict=True):
        _style(ax)
        ax.axhline(0.10, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
        t1 = [risk("T1_strong", noise, m)[0] for m in copies]
        ax.plot(range(len(copies)), t1, color=MUTED, linewidth=1.5, linestyle=":")
        for system, (label, colour, ls, marker) in SERIES.items():
            vals = [risk(system, noise, m) for m in copies]
            ys = [v[0] for v in vals]
            lo = [v[1][0] if v[1] else v[0] for v in vals]
            hi = [v[1][1] if v[1] else v[0] for v in vals]
            ax.fill_between(range(len(copies)), lo, hi, color=colour, alpha=0.06, linewidth=0)
            ax.plot(
                range(len(copies)),
                ys,
                color=colour,
                linestyle=ls,
                linewidth=2,
                marker=marker,
                markersize=5,
                markeredgecolor=SURFACE,
                markeredgewidth=1.5,
                label=label,
            )
        ax.set_xticks(range(len(copies)), [str(m) for m in copies])
        title = "exact copies" if noise == 0 else f"copies with {noise:.0%} tokens deleted"
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.set_xlabel("copies per source document", fontsize=8, color=INK_2)
        ax.text(len(copies) - 1, 0.102, "certified α = 10%", fontsize=7, color=INK_2, ha="right")
    axes[0].set_ylabel("realised risk on targeted documents", fontsize=8, color=INK_2)
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(Line2D([], [], color=MUTED, linestyle=":", linewidth=1.5))
    labels.append("text only (no pool)")
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    _save(fig, "risk_vs_copies")


def automation_frontier() -> None:
    r = orjson.loads((paths.REPORTS / "comparison_v1.json").read_bytes())
    alphas = ["0.01", "0.02", "0.05", "0.1"]
    systems = {
        "T0_tfidf": ("TF-IDF", MUTED, ":", "o"),
        "T1_strong": ("LEGAL-BERT", INK_2, "-", "o"),
        "C1_strong+knn": ("LEGAL-BERT + kNN", BLUE, "-", "s"),
        "G1_strong+graph": ("LEGAL-BERT + citation graph", ORANGE, "--", "D"),
    }
    fig, ax = plt.subplots(figsize=(5, 3.4), facecolor=SURFACE)
    _style(ax)
    for name, (label, colour, ls, marker) in systems.items():
        ys = [r["systems"][name]["policy"][a]["auto_recall"] for a in alphas]
        ax.plot(
            range(len(alphas)),
            ys,
            color=colour,
            linestyle=ls,
            linewidth=2,
            marker=marker,
            markersize=5,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            label=label,
        )
    ax.set_xticks(range(len(alphas)), ["1%", "2%", "5%", "10%"])
    ax.set_xlabel("certified risk level α (δ = 0.1)", fontsize=8, color=INK_2)
    ax.set_ylabel("certified AutoRecall on risk_cert", fontsize=8, color=INK_2)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_ylim(-0.02, 0.64)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    _save(fig, "automation_frontier")


def detection_curve() -> None:
    """Protocol 4.0, H3: attribution and harm vs edit level (final_test targets, seed 0)."""
    r = orjson.loads((paths.REPORTS / "protocol_v4_results.json").read_bytes())
    h3 = r["h3"]["final_test"]
    attribution = {(a["kind"], a["rate"]): a for a in h3["attribution"]}
    table = h3["seeds"]["0"]["table"]
    methods = {
        "minhash": ("MinHash", MUTED, ":"),
        "cosine": ("cosine", ORANGE, "--"),
        "containment": ("containment", BLUE, "-"),
    }
    fig, axes = plt.subplots(2, 2, figsize=(8, 5.2), sharex=True, sharey="row")
    for col, (kind, title) in enumerate((("del", "tokens deleted"), ("sub", "tokens substituted"))):
        rates = sorted(rt for k, rt in attribution if k == kind)
        top, bottom = axes[0, col], axes[1, col]
        for m, (label, colour, ls) in methods.items():
            top.plot(
                rates,
                [attribution[kind, rt][m]["attributed"] for rt in rates],
                color=colour,
                linestyle=ls,
                marker="o",
                markersize=3,
                label=label,
            )
            change = [
                next(
                    t["risk_change"]
                    for t in table
                    if (t["kind"], t["rate"], t["system"], t["attribution"])
                    == (kind, rt, "C1p_strong+knn_prov", m)
                )
                for rt in rates
            ]
            bottom.plot(rates, change, color=colour, linestyle=ls, marker="o", markersize=3)
        naive = [
            next(
                t["risk_change"]
                for t in table
                if (t["kind"], t["rate"], t["system"]) == (kind, rt, "C1_strong+knn")
            )
            for rt in rates
        ]
        bottom.plot(rates, naive, color=INK, linewidth=2.2, alpha=0.25, label="naive kNN (harm)")
        top.set_title(title, fontsize=9, color=INK)
        bottom.set_xlabel("edit level", fontsize=8, color=INK_2)
        bottom.set_xscale("log")
        for ax in (top, bottom):
            _style(ax)
            ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        top.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        bottom.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[0, 0].set_ylabel("copies attributed", fontsize=8, color=INK_2)
    axes[1, 0].set_ylabel("change in targeted risk", fontsize=8, color=INK_2)
    axes[0, 0].legend(fontsize=7, frameon=False)
    axes[1, 0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    _save(fig, "detection_curve")


def _save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(OUT / f"{name}.png")


if __name__ == "__main__":
    risk_vs_copies(sys.argv[1] if len(sys.argv) > 1 else "h2_results.json")
    automation_frontier()
    if (paths.REPORTS / "protocol_v4_results.json").exists():
        detection_curve()
