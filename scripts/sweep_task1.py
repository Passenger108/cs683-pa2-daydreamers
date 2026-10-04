#!/usr/bin/env python3
"""
CS683 PA2 - Task 1 design-parameter sweep.

Re-runs every SPP design decision as a real experiment: the SAME toolchain and
the SAME run length as the reported results (GCC 7 -O3, 25M warmup + 25M
simulation), on ALL THREE traces rather than a slice of one.

Four sweeps:
  A  IP-table geometry        (docs/TASK1_SPP.md 2.1)
  B  degree cap / throttling  (docs/TASK1_SPP.md 7.2)
  C  accuracy window          (docs/TASK1_SPP.md 7.1)
  D  uniform-stride threshold (docs/TASK1_SPP.md 3.2)

Each variant is produced by rewriting #define lines in prefetcher/spp.l1d_pref,
so the only thing that differs between variants is the knob under test.

usage:
    ./build_champsim.sh spp lru spp          # once, to lay down the other generated files
    python3 scripts/sweep_task1.py ../traces 3

Arguments: <trace-dir> <parallel-jobs>.  Resumable - a variant whose logs already
contain a Region-of-Interest section is skipped, so you can stop and restart.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from parse_results import parse_log, geomean                      # noqa: E402

BASE_SRC = os.path.join(ROOT, "prefetcher", "spp.l1d_pref")
GEN_SRC = os.path.join(ROOT, "prefetcher", "l1d_prefetcher.cc")
OUT_DIR = os.path.join(ROOT, "results", "task1_sweep")
BIN_DIR = os.path.join(ROOT, "bin")
BASE_RESULTS = os.path.join(ROOT, "results", "task1")

TRACES = ["trace1", "trace2", "trace3"]
N_WARM = 25_000_000
N_SIM = 25_000_000


# --------------------------------------------------------------------------
# A variant is just a set of #define overrides, plus (for the degree sweep) the
# four assignments inside the throttle.
# --------------------------------------------------------------------------
def V(name, sweep, note, defines=None, degree_map=None, storage_note=None):
    return {"name": name, "sweep": sweep, "note": note,
            "defines": defines or {}, "degree_map": degree_map,
            "storage_note": storage_note}


VARIANTS = [
    # ---- the design as submitted; it is the shared reference for every sweep
    V("base_64x4", "reference", "the submitted design: 64x4 IP table, degree 1-4, window 512"),

    # ---- A: IP-table geometry ------------------------------------------------
    V("ipA_256x1", "A  IP geometry", "direct mapped, same entry count as base",
      {"IP_TABLE_SETS": 256, "IP_INDEX_BITS": 8, "IP_TABLE_WAYS": 1}),
    V("ipA_128x2", "A  IP geometry", "same entries as base, less associativity",
      {"IP_TABLE_SETS": 128, "IP_INDEX_BITS": 7, "IP_TABLE_WAYS": 2}),
    V("ipA_128x4", "A  IP geometry", "2x entries of base",
      {"IP_TABLE_SETS": 128, "IP_INDEX_BITS": 7, "IP_TABLE_WAYS": 4}),
    V("ipA_64x8", "A  IP geometry", "2x entries of base, via associativity",
      {"IP_TABLE_SETS": 64, "IP_INDEX_BITS": 6, "IP_TABLE_WAYS": 8}),
    V("ipA_128x8", "A  IP geometry", "4x entries of base",
      {"IP_TABLE_SETS": 128, "IP_INDEX_BITS": 7, "IP_TABLE_WAYS": 8}),

    # ---- B: degree cap and whether throttling earns its keep -----------------
    V("degB_1to3", "B  degree", "shallower cap", {"MAX_DEGREE": 3},
      degree_map=("3", "3", "2", "MIN_DEGREE")),
    V("degB_1to6", "B  degree", "deeper cap", {"MAX_DEGREE": 6},
      degree_map=("6", "4", "2", "MIN_DEGREE")),
    V("degB_1to8", "B  degree", "much deeper cap", {"MAX_DEGREE": 8},
      degree_map=("8", "6", "3", "MIN_DEGREE")),
    V("degB_fixed4", "B  degree", "NO throttling, always degree 4",
      degree_map=("4", "4", "4", "4")),
    V("degB_fixed2", "B  degree", "NO throttling, always degree 2",
      degree_map=("2", "2", "2", "2")),

    # ---- C: accuracy window -------------------------------------------------
    V("winC_256", "C  acc window", "faster adaptation, more measurement bias",
      {"ACC_WINDOW": 256}),
    V("winC_1024", "C  acc window", "less bias, slower adaptation",
      {"ACC_WINDOW": 1024}),

    # ---- D: uniform threshold (3.2 argues 3 is forced; measure 2 and 4) ------
    V("unifD_2", "D  uniform thr", "threshold 2 - provably misclassifies the PDF pattern",
      {"UNIFORM_CONF_MAX": 2}),
    V("unifD_4", "D  uniform thr", "threshold 4 - slower to enter uniform mode",
      {"UNIFORM_CONF_MAX": 4}),
]


def make_variant_source(v):
    """Rewrite the #define lines (and, if asked, the throttle's degree map)."""
    src = open(BASE_SRC).read()

    for key, val in v["defines"].items():
        pat = re.compile(r"^(#define\s+%s\s+)(\S+)" % re.escape(key), re.M)
        src, n = pat.subn(lambda m: m.group(1) + str(val), src, count=1)
        if n != 1:
            raise RuntimeError("could not set #define %s in %s" % (key, v["name"]))

    if v["degree_map"]:
        hi, mid, lo, fl = v["degree_map"]
        pairs = [("if      (acc >= 75) spp_degree = 4;",
                  "if      (acc >= 75) spp_degree = %s;" % hi),
                 ("else if (acc >= 50) spp_degree = 3;",
                  "else if (acc >= 50) spp_degree = %s;" % mid),
                 ("else if (acc >= 25) spp_degree = 2;",
                  "else if (acc >= 25) spp_degree = %s;" % lo),
                 ("else                spp_degree = MIN_DEGREE;",
                  "else                spp_degree = %s;" % fl)]
        for old, new in pairs:
            if old not in src:
                raise RuntimeError("throttle anchor missing in %s: %s" % (v["name"], old))
            src = src.replace(old, new)

    return src


def storage_bytes(v):
    """Hardware cost of this variant, using the same accounting as TASK1_SPP.md 6.

    Field widths are not fixed - they follow the knob under test, which is the
    whole point of comparing variants on cost as well as performance:
      - LRU needs ceil(log2(ways)) bits (1 way needs none at all)
      - uniform_conf must hold UNIFORM_CONF_MAX, so threshold 4 needs 3 bits
      - the degree register must hold MAX_DEGREE
    """
    sets = v["defines"].get("IP_TABLE_SETS", 64)
    ways = v["defines"].get("IP_TABLE_WAYS", 4)
    uconf_max = v["defines"].get("UNIFORM_CONF_MAX", 3)
    max_deg = v["defines"].get("MAX_DEGREE", 4)
    if v["degree_map"]:                       # a fixed-degree variant may cap higher
        for x in v["degree_map"]:
            if x.isdigit():
                max_deg = max(max_deg, int(x))

    win = v["defines"].get("ACC_WINDOW", 256)
    lru_bits = max(0, (ways - 1).bit_length())        # 1->0, 2->1, 4->2, 8->3
    uconf_bits = max(1, uconf_max.bit_length())       # 3->2, 4->3
    ip_bits = 16 + 1 + 12 + 6 + 7 + uconf_bits + 10 + lru_bits
    ip_total = sets * ways * ip_bits

    pattern_total = 1024 * 9                          # 7b signed stride + 2b confidence
    # the two window counters only have to span ACC_WINDOW plus the <=32 prefetches
    # that can still be in flight when the window closes
    ctr_bits = max(1, (win + 32).bit_length())
    throttle_bits = max(1, max_deg.bit_length()) + 2 * ctr_bits
    return (ip_total + pattern_total + throttle_bits + 7) // 8


def build(v):
    binary = os.path.join(BIN_DIR, "sweep_" + v["name"])
    if os.path.exists(binary):
        print("  [build] cached:", os.path.basename(binary))
        return binary
    open(GEN_SRC, "w").write(make_variant_source(v))
    obj = os.path.join(ROOT, "obj", "prefetcher", "l1d_prefetcher.o")
    if os.path.exists(obj):
        os.remove(obj)
    print("  [build] compiling", v["name"], "...", flush=True)
    r = subprocess.run(["make", "-j%d" % (os.cpu_count() or 2)], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    champ = os.path.join(BIN_DIR, "champsim")
    if r.returncode != 0 or not os.path.exists(champ):
        print(r.stdout.decode()[-2500:])
        raise SystemExit("build failed for " + v["name"])
    os.replace(champ, binary)
    os.chmod(binary, 0o755)
    return binary


def run_all(variants, trace_dir, jobs):
    os.makedirs(OUT_DIR, exist_ok=True)
    for v in variants:
        print("[variant]", v["name"], "-", v["note"], flush=True)
        todo = []
        for t in TRACES:
            log = os.path.join(OUT_DIR, "%s_%s.txt" % (v["name"], t))
            if os.path.exists(log) and "Region of Interest" in open(log, errors="ignore").read():
                print("  [skip]", os.path.basename(log))
                continue
            todo.append((t, log))
        if not todo:
            continue
        binary = build(v)
        procs = []
        for t, log in todo:
            cmd = [binary, "-warmup_instructions", str(N_WARM),
                   "-simulation_instructions", str(N_SIM),
                   "-traces", os.path.join(trace_dir, t + ".gz")]
            print("  [run ]", v["name"], t, flush=True)
            procs.append(subprocess.Popen(cmd, stdout=open(log, "w"),
                                          stderr=subprocess.STDOUT, cwd=ROOT))
            while len([p for p in procs if p.poll() is None]) >= jobs:
                procs[0].wait()
                procs = [p for p in procs if p.poll() is None]
        for p in procs:
            p.wait()


def summarise(variants):
    """Aggregate exactly the way 8.7.0 says each metric should be aggregated."""
    base = {}
    for t in TRACES:
        f = os.path.join(BASE_RESULTS, "baseline_%s.txt" % t)
        if os.path.exists(f):
            base[t] = parse_log(f)

    rows = []
    for v in variants:
        recs = {}
        for t in TRACES:
            log = os.path.join(OUT_DIR, "%s_%s.txt" % (v["name"], t))
            if os.path.exists(log):
                r = parse_log(log)
                if r:
                    recs[t] = r
        if len(recs) != len(TRACES):
            print("[warn] %s incomplete (%d/%d traces)" % (v["name"], len(recs), len(TRACES)))
            continue

        speedups, mpkis, ip_hits = [], [], []
        miss_b = miss_v = useful = pulled = 0
        for t, r in recs.items():
            if base.get(t, {}).get("ipc"):
                speedups.append(r["ipc"] / base[t]["ipc"])
                miss_b += base[t]["l1d_load_miss"]
            miss_v += r.get("l1d_load_miss", 0)
            mpkis.append(r.get("l1d_load_mpki", 0))
            useful += r.get("l1d_pf_useful", 0)
            pulled += r.get("l1d_pf_lower_level", 0)
            if r.get("spp_ip_hit_rate") is not None:
                ip_hits.append(r["spp_ip_hit_rate"])

        rows.append({
            "name": v["name"], "sweep": v["sweep"], "note": v["note"],
            "bytes": storage_bytes(v),
            "speedup": geomean(speedups),
            "mpki": sum(mpkis) / len(mpkis),
            "acc": 100.0 * useful / pulled if pulled else 0.0,
            "cov": 100.0 * (miss_b - miss_v) / miss_b if miss_b else 0.0,
            "iphit": sum(ip_hits) / len(ip_hits) if ip_hits else 0.0,
        })

    ref = next((r for r in rows if r["name"] == "base_64x4"), None)

    hdr = (f"{'variant':14s} {'sweep':16s} {'bytes':>6s} {'geo spd':>9s} "
           f"{'d vs base':>10s} {'avgMPKI':>8s} {'pooled acc':>11s} "
           f"{'pooled cov':>11s} {'IP hit':>7s}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        d = ""
        if ref and r is not ref:
            d = "%+.4f" % (r["speedup"] - ref["speedup"])
        print(f"{r['name']:14s} {r['sweep']:16s} {r['bytes']:6d} "
              f"{r['speedup']:9.4f} {d:>10s} {r['mpki']:8.3f} "
              f"{r['acc']:10.2f}% {r['cov']:10.2f}% {r['iphit']:6.2f}%")

    out = os.path.join(OUT_DIR, "sweep_summary.md")
    with open(out, "w") as f:
        f.write("# Task 1 design sweep (GCC 7 -O3, 25M+25M, all three traces)\n\n")
        f.write("Speedup is a geometric mean (it is a ratio); MPKI an equal-weight mean\n"
                "(equal instruction counts); accuracy and coverage are pooled\n"
                "(sum of numerators over sum of denominators). See TASK1_SPP.md 8.7.0.\n\n")
        f.write("| variant | sweep | what it changes | storage B | geomean speedup | "
                "d vs base | avg L1D load MPKI | pooled accuracy | pooled coverage | "
                "mean IP-table hit rate |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            d = "--" if (ref and r is ref) else ("%+.4f" % (r["speedup"] - ref["speedup"])
                                                 if ref else "--")
            f.write(f"| `{r['name']}` | {r['sweep']} | {r['note']} | {r['bytes']} | "
                    f"{r['speedup']:.4f} | {d} | {r['mpki']:.3f} | {r['acc']:.2f} % | "
                    f"{r['cov']:.2f} % | {r['iphit']:.2f} % |\n")
    print("\n[ok] wrote", out)


def main():
    trace_dir = sys.argv[1] if len(sys.argv) > 1 else "../traces"
    jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    if not os.path.exists(os.path.join(ROOT, "obj")):
        raise SystemExit("No obj/ directory - run './build_champsim.sh spp lru spp' once first.")

    try:
        run_all(VARIANTS, trace_dir, jobs)
    finally:
        # always leave the generated file matching the submitted design
        open(GEN_SRC, "w").write(open(BASE_SRC).read())
    summarise(VARIANTS)


if __name__ == "__main__":
    main()
