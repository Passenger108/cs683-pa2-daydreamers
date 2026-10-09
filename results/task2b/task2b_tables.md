# Task 2b - Dynamic I-RRIP: results

25M warmup + 25M simulation, single core, no L1D prefetcher, GCC 7 `-O3`.
Speedup is against **LRU (baseline)**. Geometric mean for speedup (a ratio),
arithmetic mean for the MPKIs.

Dynamic policy configuration, read back from the runs' own logs:

```
MAX_RRPV 3 | SELECTOR 2 thresh 45 hyst 3 | LEADERS 8 stride 128 | WINDOW 8192 | INSTR_WEIGHT 2
```

### IPC

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 0.23234 | 0.25116 | 0.38206 | **0.28852** |
| RRIP | 0.23223 | 0.25181 | 0.38174 | **0.28859** |
| I-RRIP static (2a) | 0.23157 | 0.26081 | 0.38466 | **0.29234** |
| Dynamic I-RRIP (2b) | 0.23210 | 0.25692 | 0.38159 | **0.29020** |

### Speedup over LRU

Geometric mean, because speedup is a ratio.

| policy | trace1 | trace2 | trace3 | geomean |
|---|---|---|---|---|
| LRU (baseline) | 1.0000 | 1.0000 | 1.0000 | **1.0000** |
| RRIP | 0.9995 | 1.0026 | 0.9991 | **1.0004** |
| I-RRIP static (2a) | 0.9967 | 1.0384 | 1.0068 | **1.0138** |
| Dynamic I-RRIP (2b) | 0.9990 | 1.0229 | 0.9987 | **1.0068** |

### L2C load MPKI

All L2 load misses. Lower is better.

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 17.6956 | 27.3568 | 3.9542 | **16.3356** |
| RRIP | 17.6387 | 25.7458 | 4.0395 | **15.8080** |
| I-RRIP static (2a) | 19.2338 | 21.0584 | 3.9847 | **14.7590** |
| Dynamic I-RRIP (2b) | 17.7756 | 21.9398 | 3.9924 | **14.5693** |

### L2 INSTRUCTION load MPKI

**The metric Task 2a was asked to reduce.**

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 10.3377 | 18.8533 | 1.1241 | **10.1050** |
| RRIP | 10.5618 | 17.7813 | 1.1970 | **9.8467** |
| I-RRIP static (2a) | 9.2375 | 8.7147 | 0.7134 | **6.2219** |
| Dynamic I-RRIP (2b) | 10.3883 | 10.3623 | 1.0124 | **7.2543** |

### L2 DATA load MPKI

The cost of prioritising. Static I-RRIP raises this on every trace; the dynamic policy should raise it less where prioritising does not pay.

| policy | trace1 | trace2 | trace3 | mean |
|---|---|---|---|---|
| LRU (baseline) | 7.3580 | 8.5035 | 2.8302 | **6.2305** |
| RRIP | 7.0769 | 7.9645 | 2.8424 | **5.9613** |
| I-RRIP static (2a) | 9.9964 | 12.3437 | 3.2713 | **8.5371** |
| Dynamic I-RRIP (2b) | 7.3873 | 11.5776 | 2.9800 | **7.3150** |

### Did adapting help? Dynamic vs static, per trace

Task 2b exists because static I-RRIP regresses a trace. The test is whether
the dynamic policy recovers that trace **without** giving back the trace where
prioritising pays. `vs LRU` columns flag a regression against the baseline.

| trace | policy | instr MPKI | L2C MPKI | vs LRU | speedup | verdict |
|---|---|---|---|---|---|---|
| trace1 | RRIP | 10.5618 | 17.6387 | -0.3% | 0.9995 | clean |
| trace1 | I-RRIP static (2a) | 9.2375 | 19.2338 | +8.7% | 0.9967 | REGRESSES |
| trace1 | Dynamic I-RRIP (2b) | 10.3883 | 17.7756 | +0.5% | 0.9990 | REGRESSES |
| trace2 | RRIP | 17.7813 | 25.7458 | -5.9% | 1.0026 | clean |
| trace2 | I-RRIP static (2a) | 8.7147 | 21.0584 | -23.0% | 1.0384 | clean |
| trace2 | Dynamic I-RRIP (2b) | 10.3623 | 21.9398 | -19.8% | 1.0229 | clean |
| trace3 | RRIP | 1.1970 | 4.0395 | +2.2% | 0.9991 | REGRESSES |
| trace3 | I-RRIP static (2a) | 0.7134 | 3.9847 | +0.8% | 1.0068 | REGRESSES |
| trace3 | Dynamic I-RRIP (2b) | 1.0124 | 3.9924 | +1.0% | 0.9987 | REGRESSES |

### The duel: what the selector actually did

`% in I-RRIP` is the share of decision windows that chose to prioritise.
`switches` is how often the verdict flipped: a high count means the selector
is thrashing rather than tracking phases, which no MPKI table would reveal.
`sacrificed` is the fraction of the cache pinned to a leader policy -- the
price of measuring, paid in cache the followers do not get.

| trace | windows | % in I-RRIP | switches | switches/window | PSEL | sacrificed | storage (B) |
|---|---|---|---|---|---|---|---|
| trace1 | 141 | 12.1% | 20 | 0.1418 | 519 | 1.56% | 2058 |
| trace2 | 251 | 82.9% | 39 | 0.1554 | 501 | 1.56% | 2058 |
| trace3 | 75 | 68.0% | 14 | 0.1867 | 512 | 1.56% | 2058 |

Read `% in I-RRIP` against Task 2a: the dynamic policy *should* sit near 0 %
on the trace where static prioritisation lost and near 100 % where it won. If
it does not, the selector is reading the wrong signal, and that is the finding
to report rather than a number to tune away.

### Eviction conflicts

`data->instr` is a data fill throwing out an instruction line -- the conflict
instruction-consciousness exists to reduce, and direct evidence about the
mechanism independently of whether MPKI moved.

| policy | trace | instr victims | data->instr | instr->instr |
|---|---|---|---|---|
| LRU (baseline) | trace1 | 257967 | 120225 | 112800 |
| LRU (baseline) | trace2 | 462640 | 136147 | 298635 |
| LRU (baseline) | trace3 | 30733 | 19415 | 8097 |
| RRIP | trace1 | 261441 | 118342 | 118276 |
| RRIP | trace2 | 431648 | 120581 | 284190 |
| RRIP | trace3 | 31970 | 19352 | 9309 |
| I-RRIP static (2a) | trace1 | 200049 | 103643 | 77919 |
| I-RRIP static (2a) | trace2 | 189603 | 70729 | 103316 |
| I-RRIP static (2a) | trace3 | 16064 | 8580 | 5650 |
| Dynamic I-RRIP (2b) | trace1 | 255812 | 117526 | 113584 |
| Dynamic I-RRIP (2b) | trace2 | 233763 | 82994 | 130042 |
| Dynamic I-RRIP (2b) | trace3 | 25697 | 17069 | 5619 |

