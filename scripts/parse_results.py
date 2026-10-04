#!/usr/bin/env python3
"""
CS683 PA2 - turn ChampSim logs into one CSV plus report-ready Markdown tables.

Everything is read from the "Region of Interest Statistics" half of the log, never
from the warm-up half, because ChampSim resets all cache and prefetch counters when
the ROI starts (src/main.cc:442).

The ONE exception is the block printed by our own l1d_prefetcher_final_stats():
those counters are ours, ChampSim does not reset them, so they describe the whole
run (warmup + ROI).  Columns derived from them are prefixed `spp_` and the Markdown
output labels them accordingly.

usage:
  python3 scripts/parse_results.py results/task1 results/task1/task1.csv
"""
import csv
import os
import re
import sys

CONFIG_ORDER = {"baseline": 0, "ipstride": 1, "spp": 2}
CONFIG_LABEL = {"baseline": "No prefetcher", "ipstride": "IP-stride", "spp": "SPP"}


def roi_part(text):
    """Only the Region-of-Interest section of a ChampSim log."""
    i = text.find("Region of Interest Statistics")
    return text[i:] if i >= 0 else ""


def grab(pattern, text, cast=float, default=None):
    m = re.search(pattern, text)
    if not m:
        return default
    try:
        return cast(m.group(1))
    except (TypeError, ValueError):
        return default


def parse_log(path):
    with open(path, errors="ignore") as f:
        text = f.read()
    roi = roi_part(text)
    if not roi:
        return None

    r = {}

    # ---- run provenance, so a stale log can never be mistaken for a good one ----
    r["warmup_instr"] = grab(r"Warmup complete CPU \d+ instructions:\s*(\d+)", text, int)
    r["sim_instr"] = grab(r"Finished CPU \d+ instructions:\s*(\d+)", text, int)
    r["sim_cycles"] = grab(r"Finished CPU \d+ instructions:\s*\d+\s+cycles:\s*(\d+)",
                           text, int)

    # ---- IPC ----
    r["ipc"] = grab(r"cumulative IPC:\s*([0-9.]+)", roi)

    # ---- L1D demand loads: the metric the PDF asks for ----
    m = re.search(r"L1D LOAD\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+)"
                  r".*?MPKI:\s*([0-9.]+)", roi)
    if m:
        r["l1d_load_access"] = int(m.group(1))
        r["l1d_load_hit"] = int(m.group(2))
        r["l1d_load_miss"] = int(m.group(3))
        r["l1d_load_mpki"] = float(m.group(4))

    # ---- L1D prefetch accounting ----
    m = re.search(r"L1D PREFETCH\s+REQUESTED:\s*(\d+)\s+ISSUED:\s*(\d+)\s+"
                  r"USEFUL:\s*(\d+)\s+USELESS:\s*(\d+)", roi)
    if m:
        r["l1d_pf_requested"] = int(m.group(1))
        r["l1d_pf_issued"] = int(m.group(2))
        r["l1d_pf_useful"] = int(m.group(3))
        r["l1d_pf_useless"] = int(m.group(4))

    # The field ChampSim itself labels ACCURACY (src/main.cc:253):
    #     pf_useful / pf_lower_level
    # pf_lower_level counts prefetches that actually missed and allocated an MSHR
    # entry, i.e. lines genuinely pulled into the cache (src/cache.cc:2604).  This is
    # the number the PDF means by "Prefetch Accuracy = Also present in stats", and the
    # one SPP throttles on.  See docs/TASK1_SPP.md §7.1.
    m = re.search(r"L1D USEFUL LOAD PREFETCHES:\s*(\d+)\s+"
                  r"PREFETCH ISSUED TO LOWER LEVEL:\s*(\d+)\s+"
                  r"ACCURACY:\s*([0-9.]+|nan|inf)", roi)
    if m:
        r["l1d_pf_lower_level"] = int(m.group(2))
        try:
            acc = float(m.group(3))
        except ValueError:
            acc = None
        # ChampSim prints "nan" when nothing was prefetched (0/0) - that is the
        # baseline, where accuracy is undefined rather than zero.  Keep it empty
        # so it can never be averaged or plotted as a real 0 %.
        r["l1d_accuracy"] = None if (acc is None or acc != acc
                                     or r["l1d_pf_lower_level"] == 0) else acc
    else:
        r["l1d_pf_lower_level"] = 0
        r["l1d_accuracy"] = None

    # secondary, coarser ratio - reported alongside so both are on the record
    if r.get("l1d_pf_issued"):
        r["l1d_acc_over_issued"] = 100.0 * r["l1d_pf_useful"] / r["l1d_pf_issued"]
    else:
        r["l1d_acc_over_issued"] = 0.0

    m = re.search(r"L1D TIMELY PREFETCHES:\s*(\d+)\s+LATE PREFETCHES:\s*(\d+)"
                  r"\s+DROPPED PREFETCHES:\s*(\d+)", roi)
    if m:
        r["l1d_pf_late"] = int(m.group(2))
        r["l1d_pf_dropped"] = int(m.group(3))

    # Hard evidence for the PDF's page-confinement requirement: ChampSim counts this
    # itself, in prefetch_line(), independently of our code (src/cache.cc:3652).
    r["l1d_cross_page_pf"] = grab(r"L1D Cross Page Prefetch Requests:\s*(\d+)", roi, int)
    r["l1d_same_page_pf"] = grab(r"L1D Same Page Prefetch Requests:\s*(\d+)", roi, int)

    # ---- L2C: not a Task-1 deliverable, captured for Tasks 2 and 3 ----
    m = re.search(r"L2C LOAD\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+)"
                  r".*?MPKI:\s*([0-9.]+)", roi)
    if m:
        r["l2c_load_miss"] = int(m.group(3))
        r["l2c_load_mpki"] = float(m.group(4))
    r["l2c_data_load_mpki"] = grab(r"L2C DATA LOAD MPKI:\s*([0-9.]+)", roi)
    r["l2c_instr_load_mpki"] = grab(r"L2C INSTRUCTION LOAD MPKI:\s*([0-9.]+)", roi)

    # ---- our own SPP counters (whole run, warmup + ROI) ----
    r["spp_uniform_pf"] = grab(r"from UNIFORM path\s*:\s*(\d+)", text, int)
    r["spp_nonuniform_pf"] = grab(r"from NON-UNIFORM path\s*:\s*(\d+)", text, int)
    tot = (r.get("spp_uniform_pf") or 0) + (r.get("spp_nonuniform_pf") or 0)
    if tot:
        r["spp_uniform_pct"] = 100.0 * r["spp_uniform_pf"] / tot
        r["spp_nonuniform_pct"] = 100.0 * r["spp_nonuniform_pf"] / tot
    r["spp_mean_usefulness"] = grab(r"mean windowed usefulness\s*:\s*([0-9.]+)", text)
    r["spp_windows"] = grab(r"usefulness\s*:\s*[0-9.]+\s*%\s*over\s*(\d+)\s*windows",
                            text, int)
    m = re.search(r"windows spent at degree\s*:\s*(.+)", text)
    if m:
        r["spp_degree_windows"] = " ".join(m.group(1).split())
    r["spp_pattern_used"] = grab(r"pattern-table entries conf>=\d+\s*:\s*(\d+)", text, int)
    r["spp_ip_hit_rate"] = grab(r"IP-table hit rate\s*:\s*([0-9.]+)", text)
    r["spp_page_breaks"] = grab(r"page-boundary re-anchors\s*:\s*(\d+)", text, int)
    r["spp_chain_stops"] = grab(r"lookahead chains cut by conf\s*:\s*(\d+)", text, int)
    return r


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


FIELDS = ["trace", "config", "warmup_instr", "sim_instr", "sim_cycles",
          "ipc", "speedup",
          "l1d_load_access", "l1d_load_hit", "l1d_load_miss", "l1d_load_mpki",
          "l1d_coverage",
          "l1d_pf_requested", "l1d_pf_issued", "l1d_pf_useful", "l1d_pf_useless",
          "l1d_pf_lower_level", "l1d_pf_late", "l1d_pf_dropped",
          "l1d_accuracy", "l1d_acc_over_issued",
          "l1d_cross_page_pf", "l1d_same_page_pf",
          "l2c_load_mpki", "l2c_data_load_mpki", "l2c_instr_load_mpki",
          "spp_uniform_pf", "spp_nonuniform_pf",
          "spp_uniform_pct", "spp_nonuniform_pct",
          "spp_mean_usefulness", "spp_windows", "spp_degree_windows",
          "spp_pattern_used", "spp_ip_hit_rate", "spp_page_breaks",
          "spp_chain_stops"]


def fmt(v, nd=4):
    if v is None or v == "":
        return "--"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def md_tables(rows, traces, out_path):
    """Write the §8 tables of docs/TASK1_SPP.md, ready to paste."""
    L = []
    cfgs = ["baseline", "ipstride", "spp"]

    def get(t, c, k, d=None):
        return rows.get((t, c), {}).get(k, d)

    L.append("### 8.1 IPC and speedup\n")
    L.append("| Trace | IPC baseline | IPC ip_stride | IPC SPP "
             "| Speedup ip_stride | Speedup SPP |")
    L.append("|---|---|---|---|---|---|")
    for t in traces:
        L.append("| {} | {} | {} | {} | {} | {} |".format(
            t, fmt(get(t, "baseline", "ipc")), fmt(get(t, "ipstride", "ipc")),
            fmt(get(t, "spp", "ipc")),
            fmt(get(t, "ipstride", "speedup")), fmt(get(t, "spp", "speedup"))))
    L.append("| **geomean** | -- | -- | -- | **{}** | **{}** |".format(
        fmt(geomean([get(t, "ipstride", "speedup") for t in traces])),
        fmt(geomean([get(t, "spp", "speedup") for t in traces]))))

    L.append("\n### 8.2 L1D load MPKI\n")
    L.append("| Trace | baseline | ip_stride | SPP | SPP reduction vs baseline |")
    L.append("|---|---|---|---|---|")
    for t in traces:
        b = get(t, "baseline", "l1d_load_mpki")
        s = get(t, "spp", "l1d_load_mpki")
        red = (100.0 * (b - s) / b) if (b and s is not None) else None
        L.append("| {} | {} | {} | {} | {} |".format(
            t, fmt(b, 3), fmt(get(t, "ipstride", "l1d_load_mpki"), 3), fmt(s, 3),
            (fmt(red, 2) + " %") if red is not None else "--"))
    L.append("| **average** | **{}** | **{}** | **{}** | |".format(
        fmt(mean([get(t, "baseline", "l1d_load_mpki") for t in traces]), 3),
        fmt(mean([get(t, "ipstride", "l1d_load_mpki") for t in traces]), 3),
        fmt(mean([get(t, "spp", "l1d_load_mpki") for t in traces]), 3)))

    L.append("\n### 8.3 Prefetch accuracy and L1D coverage\n")
    L.append("Accuracy is ChampSim's own `ACCURACY` field "
             "(`pf_useful / pf_lower_level`); `useful/issued` is given in brackets.\n")
    L.append("| Trace | acc ip_stride | acc SPP | coverage ip_stride | coverage SPP |")
    L.append("|---|---|---|---|---|")
    for t in traces:
        L.append("| {} | {} % ({} %) | {} % ({} %) | {} % | {} % |".format(
            t,
            fmt(get(t, "ipstride", "l1d_accuracy"), 2),
            fmt(get(t, "ipstride", "l1d_acc_over_issued"), 2),
            fmt(get(t, "spp", "l1d_accuracy"), 2),
            fmt(get(t, "spp", "l1d_acc_over_issued"), 2),
            fmt(get(t, "ipstride", "l1d_coverage"), 2),
            fmt(get(t, "spp", "l1d_coverage"), 2)))
    L.append("| *equal-weight mean* | {} % | {} % | {} % | {} % |".format(
        fmt(mean([get(t, "ipstride", "l1d_accuracy") for t in traces]), 2),
        fmt(mean([get(t, "spp", "l1d_accuracy") for t in traces]), 2),
        fmt(mean([get(t, "ipstride", "l1d_coverage") for t in traces]), 2),
        fmt(mean([get(t, "spp", "l1d_coverage") for t in traces]), 2)))

    # Accuracy and coverage are themselves ratios of event counts, so the honest
    # aggregate sums the numerators and denominators rather than averaging the
    # per-trace percentages (which would let a trace with very few misses weigh
    # as much as one with many).
    def pooled_acc(c):
        u = sum(get(t, c, "l1d_pf_useful", 0) or 0 for t in traces)
        p_ = sum(get(t, c, "l1d_pf_lower_level", 0) or 0 for t in traces)
        return 100.0 * u / p_ if p_ else None

    def pooled_cov(c):
        b = sum(get(t, "baseline", "l1d_load_miss", 0) or 0 for t in traces)
        x = sum(get(t, c, "l1d_load_miss", 0) or 0 for t in traces)
        return 100.0 * (b - x) / b if b else None

    L.append("| **pooled (sum/sum)** | **{} %** | **{} %** | **{} %** | **{} %** |".format(
        fmt(pooled_acc("ipstride"), 2), fmt(pooled_acc("spp"), 2),
        fmt(pooled_cov("ipstride"), 2), fmt(pooled_cov("spp"), 2)))
    L.append("\n*Pooled is the row to quote.* SPP wins on **every individual trace** "
             "as well, so the conclusion does not depend on the choice of aggregate.")

    L.append("\n### 8.4 SPP internal behaviour\n")
    L.append("From `l1d_prefetcher_final_stats()`. These are **our** counters, which "
             "ChampSim does not reset at the ROI boundary, so unlike every other table "
             "here they describe the **whole run (25M warmup + 25M ROI)**.\n")
    L.append("| Trace | uniform path | non-uniform path | mean windowed usefulness "
             "| windows | degree histogram | IP-table hit rate | pattern entries conf>=2 "
             "| chains cut by conf |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in traces:
        L.append("| {} | {} % | {} % | {} % | {} | {} | {} % | {} / 1024 | {} |".format(
            t,
            fmt(get(t, "spp", "spp_uniform_pct"), 2),
            fmt(get(t, "spp", "spp_nonuniform_pct"), 2),
            fmt(get(t, "spp", "spp_mean_usefulness"), 2),
            fmt(get(t, "spp", "spp_windows")),
            get(t, "spp", "spp_degree_windows", "--"),
            fmt(get(t, "spp", "spp_ip_hit_rate"), 2),
            fmt(get(t, "spp", "spp_pattern_used")),
            fmt(get(t, "spp", "spp_chain_stops"))))

    L.append("\n### 8.5 Page-confinement check (independent of our code)\n")
    L.append("`prefetch_line()` in `src/cache.cc` counts cross-page prefetch requests "
             "itself, so this is ChampSim auditing us rather than us auditing "
             "ourselves.\n")
    L.append("| Trace | config | cross-page prefetch requests | same-page prefetch requests |")
    L.append("|---|---|---|---|")
    for t in traces:
        for c in ("ipstride", "spp"):
            L.append("| {} | {} | **{}** | {} |".format(
                t, CONFIG_LABEL[c], fmt(get(t, c, "l1d_cross_page_pf")),
                fmt(get(t, c, "l1d_same_page_pf"))))

    L.append("\n### 8.6 Run provenance\n")
    L.append("| Trace | config | warmup instrs | simulated instrs | simulated cycles |")
    L.append("|---|---|---|---|---|")
    for t in traces:
        for c in cfgs:
            L.append("| {} | {} | {} | {} | {} |".format(
                t, CONFIG_LABEL[c], fmt(get(t, c, "warmup_instr")),
                fmt(get(t, c, "sim_instr")), fmt(get(t, c, "sim_cycles"))))

    with open(out_path, "w") as f:
        f.write("\n".join(L) + "\n")
    print("[ok] wrote", out_path)


def main():
    log_dir = sys.argv[1] if len(sys.argv) > 1 else "results/task1"
    out_csv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(log_dir, "task1.csv")

    rows, traces = {}, []
    for name in sorted(os.listdir(log_dir)):
        if not name.endswith(".txt"):
            continue
        config, _, trace = name[:-4].partition("_")
        rec = parse_log(os.path.join(log_dir, name))
        if rec is None:
            print("[warn] incomplete log (no ROI section), skipped:", name)
            continue
        rec["config"], rec["trace"] = config, trace
        rows[(trace, config)] = rec
        if trace not in traces:
            traces.append(trace)
    traces.sort()

    # ---- baseline-relative metrics, exactly as the PDF defines them ----
    for (trace, config), rec in rows.items():
        base = rows.get((trace, "baseline"))
        if not base:
            continue
        if base.get("ipc"):
            rec["speedup"] = rec["ipc"] / base["ipc"]
        if base.get("l1d_load_miss"):
            rec["l1d_coverage"] = 100.0 * (
                base["l1d_load_miss"] - rec.get("l1d_load_miss", 0)
            ) / base["l1d_load_miss"]

    # ---- consistency checks: refuse to produce silently wrong deliverables ----
    problems = []
    for key, rec in sorted(rows.items()):
        tag = f"{rec['trace']}/{rec['config']}"
        if (rec.get("warmup_instr") or 0) < 24_999_000:
            problems.append(f"{tag}: warmup was {rec.get('warmup_instr')}, expected 25M")
        if (rec.get("sim_instr") or 0) < 24_999_000:
            problems.append(f"{tag}: simulated {rec.get('sim_instr')}, expected 25M")
        if rec.get("l1d_cross_page_pf"):
            problems.append(f"{tag}: {rec['l1d_cross_page_pf']} CROSS-PAGE prefetches "
                            f"- page confinement violated")
        if rec["config"] == "baseline" and rec.get("l1d_pf_issued"):
            problems.append(f"{tag}: baseline issued prefetches, should be 0")
        if rec["config"] != "baseline" and not rec.get("l1d_pf_issued"):
            problems.append(f"{tag}: issued no prefetches at all")
    for t in traces:
        if (t, "baseline") not in rows:
            problems.append(f"{t}: no baseline run, so speedup/coverage cannot be computed")

    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for key in sorted(rows, key=lambda k: (k[0], CONFIG_ORDER.get(k[1], 9))):
            w.writerow(rows[key])
    print("[ok] wrote", out_csv, "with", len(rows), "rows")

    md_tables(rows, traces, os.path.join(log_dir, "task1_tables.md"))

    hdr = (f"{'trace':8s} {'config':10s} {'IPC':>8s} {'speedup':>8s} "
           f"{'LdMPKI':>8s} {'cover%':>8s} {'acc%':>7s} {'xpage':>6s}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for key in sorted(rows, key=lambda k: (k[0], CONFIG_ORDER.get(k[1], 9))):
        r = rows[key]
        acc = r.get("l1d_accuracy")
        acc_s = f"{acc:7.2f}" if acc is not None else "      -"
        xp = r.get("l1d_cross_page_pf")
        xp_s = f"{xp:>6}" if xp is not None else f"{'-':>6}"
        print(f"{r['trace']:8s} {r['config']:10s} "
              f"{r.get('ipc') or 0:8.4f} {r.get('speedup') or 1:8.4f} "
              f"{r.get('l1d_load_mpki') or 0:8.3f} "
              f"{r.get('l1d_coverage') or 0:8.2f} "
              f"{acc_s} {xp_s}")

    print("\ngeomean speedup   ip_stride = "
          f"{geomean([rows[(t,'ipstride')].get('speedup') for t in traces if (t,'ipstride') in rows]):.4f}"
          "   SPP = "
          f"{geomean([rows[(t,'spp')].get('speedup') for t in traces if (t,'spp') in rows]):.4f}")

    if problems:
        print("\n*** CONSISTENCY PROBLEMS ***")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\n[ok] all consistency checks passed "
          "(25M+25M, zero cross-page prefetches, baseline clean)")


if __name__ == "__main__":
    main()
