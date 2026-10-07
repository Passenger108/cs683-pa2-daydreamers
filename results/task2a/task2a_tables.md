# Task 2a - Instruction-Conscious L2 Replacement (I-RRIP): results

All runs: 25M warmup + 25M simulation, single core, no L1D prefetcher,
built with GCC 7 at `-O3`. Speedup is against **LRU (baseline)**, i.e.
`IPC(policy) / IPC(no prefetcher + LRU at L2)`.

### IPC

| policy | trace1 | trace2 | trace3 | arith. mean |
|---|---|---|---|---|
| LRU (baseline) | 0.23234 | 0.25116 | 0.38206 | **0.28852** |
| RRIP (supplied) | 0.23223 | 0.25181 | 0.38174 | **0.28859** |
| I-RRIP (ours) | 0.23157 | 0.26081 | 0.38466 | **0.29234** |

### Speedup over LRU baseline

Geometric mean, because speedup is a ratio.

| policy | trace1 | trace2 | trace3 | geomean |
|---|---|---|---|---|
| LRU (baseline) | 1.0000 | 1.0000 | 1.0000 | **1.0000** |
| RRIP (supplied) | 0.9995 | 1.0026 | 0.9991 | **1.0004** |
| I-RRIP (ours) | 0.9967 | 1.0384 | 1.0068 | **1.0138** |

### L2C load MPKI

Lower is better. All L2 load misses.

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 17.6956 | 27.3568 | 3.9542 | **16.3356** |
| RRIP (supplied) | 17.6387 | 25.7458 | 4.0395 | **15.8080** |
| I-RRIP (ours) | 19.2338 | 21.0584 | 3.9847 | **14.7590** |

### L2 INSTRUCTION load MPKI

Lower is better. **This is the metric Task 2a asks us to reduce.**

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 10.3377 | 18.8533 | 1.1241 | **10.1050** |
| RRIP (supplied) | 10.5618 | 17.7813 | 1.1970 | **9.8467** |
| I-RRIP (ours) | 9.2375 | 8.7147 | 0.7134 | **6.2219** |

### L2 DATA load MPKI

Lower is better. Watch this one for the starvation side effect that Task 2b exists to fix.

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 7.3580 | 8.5035 | 2.8302 | **6.2305** |
| RRIP (supplied) | 7.0769 | 7.9645 | 2.8424 | **5.9613** |
| I-RRIP (ours) | 9.9964 | 12.3437 | 3.2713 | **8.5371** |

### What changed, per trace

Instruction-MPKI reduction is the goal; data-MPKI change is the cost.
Both are shown against the LRU baseline so the trade-off is visible.

| policy | trace | instr MPKI | vs LRU | data MPKI | vs LRU | L2C load MPKI | vs LRU |
|---|---|---|---|---|---|---|---|
| RRIP (supplied) | trace1 | 10.5618 | +2.17% | 7.0769 | -3.82% | 17.6387 | -0.32% |
| RRIP (supplied) | trace2 | 17.7813 | -5.69% | 7.9645 | -6.34% | 25.7458 | -5.89% |
| RRIP (supplied) | trace3 | 1.1970 | +6.49% | 2.8424 | +0.43% | 4.0395 | +2.16% |
| I-RRIP (ours) | trace1 | 9.2375 | -10.64% | 9.9964 | +35.86% | 19.2338 | +8.69% |
| I-RRIP (ours) | trace2 | 8.7147 | -53.78% | 12.3437 | +45.16% | 21.0584 | -23.02% |
| I-RRIP (ours) | trace3 | 0.7134 | -36.53% | 3.2713 | +15.59% | 3.9847 | +0.77% |

### Eviction conflicts (ChampSim's own counters)

`data->instr` is the number of times a data fill threw out an instruction
line. That is the quantity I-RRIP is built to reduce, so it is the direct
evidence that the mechanism did what it was designed to do, independently
of whether the MPKI happened to move.

| policy | trace | instr victims | data->instr | instr->instr | transl->instr | data victims |
|---|---|---|---|---|---|---|
| LRU (baseline) | trace1 | 257967 | 120225 | 112800 | 24942 | 281495 |
| LRU (baseline) | trace2 | 462640 | 136147 | 298635 | 27858 | 310745 |
| LRU (baseline) | trace3 | 30733 | 19415 | 8097 | 3221 | 103976 |
| RRIP (supplied) | trace1 | 261441 | 118342 | 118276 | 24823 | 273029 |
| RRIP (supplied) | trace2 | 431648 | 120581 | 284190 | 26877 | 289934 |
| RRIP (supplied) | trace3 | 31970 | 19352 | 9309 | 3309 | 105044 |
| I-RRIP (ours) | trace1 | 200049 | 103643 | 77919 | 18487 | 397525 |
| I-RRIP (ours) | trace2 | 189603 | 70729 | 103316 | 15558 | 457725 |
| I-RRIP (ours) | trace3 | 16064 | 8580 | 5650 | 1834 | 127095 |

### I-RRIP internals

Configuration read back out of the run's own log:

```
MAX_RRPV 1 | INSERT instr 0 data 1 transl 1 | PROMOTE instr 0 data 1 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
```

| trace | inserts instr | inserts data | inserts transl | promotes instr | promotes data | evict-pref fired | storage (B) |
|---|---|---|---|---|---|---|---|
| trace1 | 417393 | 892582 | 112808 | 225126 | 118882 | 0 | 1024 |
| trace2 | 350048 | 1096733 | 101840 | 1071853 | 203383 | 0 | 1024 |
| trace3 | 153758 | 517930 | 67884 | 172336 | 64516 | 0 | 1024 |

