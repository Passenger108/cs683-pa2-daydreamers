# Quarantined -- NOT a result. Do not use in the report.

Kept only as the evidence behind §13.2 of `docs/TASK2A_DESIGN_DECISIONS.md`.
Everything here was produced by a **clang/macOS** build, not GCC 7, and is
therefore not comparable with anything in `results/task2a/` or
`results/task2a_sweep/`.

## What these three logs are

`ins_i2` sets instruction insertion to 2, i.e. no instruction bias at all, so it
is **algorithmically identical to the supplied `rrip`**. Comparing it against the
GCC 7 `rrip` run therefore measures the toolchain and nothing else:

| trace | L2 instr MPKI, GCC 7 `rrip` | clang `ins_i2` | divergence |
|---|---|---|---|
| trace1 | 10.5618 | 10.5810 | 0.18 % |
| trace2 | 17.7813 | 18.4604 | **3.82 %** |
| trace3 |  1.1970 |  1.1916 | 0.45 % |

Compare `results/task2a/rrip_<trace>.txt` against `sweep_clang/ins_i2_<trace>.txt`
to reproduce that table.

Why a compiler changes simulated cache counters at all: `src/cache.cc:1885` reads
`MSHR.entry[mshr_index]` inside a branch guarded by `mshr_index == -1`, so the
read is always out of bounds. Different compilers leave different garbage there,
and for `IS_STLB` it feeds `pf_lower_level`, perturbing the translation request
stream and hence the simulated L2.

3.82 % is the same order as the knob effects the sweep exists to resolve, so the
original 51-run clang sweep was discarded and re-run under GCC 7.
`scripts/sweep_task2a.py` now refuses to start unless `sys.platform` is Linux and
`g++ --version` reports 7.x.

## What was deleted

* the other 48 clang sweep logs -- superseded by `results/task2a_sweep/`;
* `irrip_stale/` -- three runs of an unrelated earlier I-RRIP plus its 5 MB
  binary. The binary was not covered by `.gitignore`, so it would have been
  committed and shipped in the Moodle tarball. §13.1 documents it; the evidence
  there is the `strings` output and the file timestamps, both quoted in the text.
