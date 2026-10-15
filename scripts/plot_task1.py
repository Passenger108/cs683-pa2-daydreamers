#!/usr/bin/env python3
"""
CS683 PA2 - Task 1 plots, in the shape the assignment PDF shows examples of:
speedup, L1D load MPKI, prefetch accuracy, L1D coverage.  One grouped bar per
trace, plus a geometric-mean (speedup) or average (the rest) group on the right.

usage:  python3 scripts/plot_task1.py results/task1/task1.csv results/task1
"""
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ---------------------------------------------------------------------------
# Palette: categorical slots 1-3 of the validated default palette.
# Checked with the data-viz validator (light surface #fcfcfb, --pairs all):
#   lightness band PASS, chroma floor PASS,
#   CVD separation PASS (worst all-pairs dE 9.2 deutan),
#   normal-vision floor PASS (worst all-pairs dE 24.0),
#   contrast WARN on aqua (2.74:1) -> relief supplied by the direct value label
#   on every bar plus the table view in results/task1/task1_tables.md.
# Colour follows the entity (a configuration), never its rank, so the same
# config keeps the same hue across all four figures.
# ---------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#d8d7d2"

COLOR = {"baseline": "#2a78d6",   # slot 1, blue
         "ipstride": "#eb6834",   # slot 2, orange
         "spp": "#1baf7a"}        # slot 3, aqua
LABEL = {"baseline": "No prefetcher", "ipstride": "IP-stride", "spp": "SPP"}


def load(csv_path):
    data, traces = {}, []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            t, c = row["trace"], row["config"]
            data[(t, c)] = row
            if t not in traces:
                traces.append(t)
    return data, sorted(traces)


def num(data, t, c, key):
    try:
        v = float(data[(t, c)][key])
    except (KeyError, TypeError, ValueError):
        return None
    return None if v != v else v          # drop NaN (baseline accuracy is nan)


def geomean(xs):
    xs = [x for x in xs if x and x > 0]
    if not xs:
        return 0.0
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def aggregate(data, traces, c, key, how):
    """Pick the aggregate that is actually valid for this metric.

    geomean  - for SPEEDUP.  Speedup is a ratio, and the arithmetic mean of
               ratios depends on which machine you normalised to; the geometric
               mean does not (GM(a/b) = GM(a)/GM(b)).  This is the standard
               result from Fleming & Wallace, "How not to lie with statistics"
               (CACM 1986), and it is why every architecture paper reports a
               geomean speedup.
    mean     - for L1D load MPKI.  MPKI is already normalised per 1000
               instructions and every trace ran exactly 25M instructions, so the
               equal-weight arithmetic mean is identical to pooling the raw
               misses (verified: both give 9.206 / 8.958 / 8.450).
    pooled   - for ACCURACY and COVERAGE.  These are themselves ratios of event
               counts, so the honest aggregate divides summed numerators by
               summed denominators.  Averaging the per-trace percentages would
               let a trace with very few misses count as much as one with many.
    """
    if how == "geomean":
        return geomean([num(data, t, c, key) for t in traces])
    if how == "mean":
        return mean([num(data, t, c, key) for t in traces])
    if how == "pooled_cov":
        base = sum(num(data, t, "baseline", "l1d_load_miss") or 0 for t in traces)
        cfg = sum(num(data, t, c, "l1d_load_miss") or 0 for t in traces)
        return 100.0 * (base - cfg) / base if base else 0.0
    if how == "pooled_acc":
        useful = sum(num(data, t, c, "l1d_pf_useful") or 0 for t in traces)
        pulled = sum(num(data, t, c, "l1d_pf_lower_level") or 0 for t in traces)
        return 100.0 * useful / pulled if pulled else 0.0
    raise ValueError(how)


AGG_NAME = {"geomean": "geomean", "mean": "average",
            "pooled_cov": "pooled", "pooled_acc": "pooled"}


def bar_plot(data, traces, configs, key, ylabel, title, out,
             agg="mean", ref_line=None, unit="", nd=2):
    groups = traces + [AGG_NAME[agg]]
    x = list(range(len(groups)))

    # 3 bars per group with a visible surface gap between neighbours
    n = len(configs)
    width = 0.72 / n
    gap = 0.02

    fig, ax = plt.subplots(figsize=(7.6, 4.1))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    top = 0.0
    for i, c in enumerate(configs):
        vals = [num(data, t, c, key) for t in traces]
        agg_v = aggregate(data, traces, c, key, agg)
        heights = [v if v is not None else 0.0 for v in vals] + [agg_v]
        pos = [xi + (i - (n - 1) / 2.0) * (width + gap) for xi in x]
        ax.bar(pos, heights, width=width, label=LABEL.get(c, c),
               color=COLOR[c], edgecolor=SURFACE, linewidth=1.2, zorder=3)
        top = max(top, max(heights))
        for px, h, raw in zip(pos, heights, vals + [agg_v]):
            if raw is None:
                continue
            ax.annotate(f"{h:.{nd}f}", (px, h), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=6.6, color=INK_2,
                        zorder=4)

    # separate the aggregate group from the per-trace groups
    ax.axvline(len(traces) - 0.5, color=GRID, linewidth=0.8, zorder=1)

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK_2)
    ax.set_title(title, fontsize=10.5, color=INK, pad=10, loc="left")

    if ref_line is not None:
        # Speedup is a NORMALISED quantity: 1.00 is the origin of the comparison,
        # not an arbitrary crop.  Anchoring the axis at exactly 1.00 (and dropping
        # the baseline series, whose speedup is 1.00 by definition) shows each bar
        # as the gain over baseline, which is what is being compared.  A bar that
        # is invisible here really did gain nothing.
        ax.set_ylim(ref_line, top + (top - ref_line) * 0.45)
    else:
        ax.set_ylim(0, top * 1.16)          # magnitudes always start at zero
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))

    ax.grid(axis="y", color=GRID, linewidth=0.45, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=INK_2, labelsize=8, length=3, width=0.8)

    ax.legend(frameon=False, fontsize=8.5, ncol=len(configs),
              loc="upper left", bbox_to_anchor=(0, 1.02), labelcolor=INK_2,
              handlelength=1.1, handleheight=1.1, columnspacing=1.4)

    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print("[ok]", out)


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "results/task1/task1.csv"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(csv_path)
    os.makedirs(out_dir, exist_ok=True)

    data, traces = load(csv_path)
    p = lambda n: os.path.join(out_dir, n)
    ALL = ["baseline", "ipstride", "spp"]
    PF = ["ipstride", "spp"]

    bar_plot(data, traces, PF, "speedup",
             "Speedup  (no-prefetch baseline = 1.00)",
             "Task 1  -  IPC speedup  (25M warmup + 25M simulation, GCC 7)",
             p("task1_speedup.png"), agg="geomean", ref_line=1.0, nd=4)

    bar_plot(data, traces, ALL, "l1d_load_mpki",
             "L1D load MPKI  (lower is better)",
             "Task 1  -  L1D load MPKI",
             p("task1_l1d_load_mpki.png"), agg="mean", nd=3)

    bar_plot(data, traces, PF, "l1d_accuracy",
             "Prefetch accuracy (%)",
             "Task 1  -  L1D prefetch accuracy  (useful / lines actually fetched)",
             p("task1_accuracy.png"), agg="pooled_acc", nd=2)

    bar_plot(data, traces, PF, "l1d_coverage",
             "L1D load-miss coverage (%)",
             "Task 1  -  L1D coverage vs no-prefetch baseline",
             p("task1_coverage.png"), agg="pooled_cov", nd=2)


if __name__ == "__main__":
    main()
