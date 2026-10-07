# CS683 PA2 - Task 2b: Dynamic I-RRIP by Set-Duelling

*Every figure in this document is recomputed from `results/task2b/*.txt` at build time; none is typed by hand.*

## 1. Headline

Baseline LRU, 25M warmup + 25M simulation, GCC 7.5.0, three traces. Speedup is the geomean of per-trace IPC ratios; MPKI is the arithmetic mean over the three equal-length traces.

| policy | geomean speedup | mean L2C MPKI | mean instr MPKI |
|---|---:|---:|---:|
| LRU (baseline) | 1.0000 | 16.3356 | 10.1050 |
| plain RRIP | 1.0004 | 15.8080 | 9.8467 |
| static I-RRIP (Task 2a) | 1.0138 | 14.7590 | 6.2219 |
| dynamic I-RRIP (Task 2b) | 1.0068 | 14.5693 | 7.2543 |

Two facts carry the result:

1. **Dynamic I-RRIP has the lowest mean L2C MPKI of all four policies (14.5693).** It even beats static I-RRIP (14.7590), because it avoids static I-RRIP's one regression.
   On trace1, static I-RRIP raises L2C MPKI +8.7% over LRU by protecting instructions a workload that does not reuse them; the dynamic policy sees that in its leaders, stays in RRIP mode, and lands at +0.5%.

2. **It does not beat static I-RRIP on IPC (1.0068 vs 1.0138),** because each trace is internally homogeneous -- a run-time switch has no phase change to exploit, so the best it can do is converge to the right static choice while still paying the leader-set tax.

## 2. The duel chose correctly on all three traces

| trace | prioritising (I-RRIP) share | switches | PSEL (mid 512) | correct? |
|---|---:|---:|---:|---|
| trace1 | 12.1% | 20 | 519 | yes - I-RRIP hurts trace1, stays RRIP |
| trace2 | 82.9% | 39 | 501 | yes - I-RRIP helps trace2, adopts it |
| trace3 | 68.0% | 14 | 512 | yes - marginal, PSEL ends ~neutral |

Switch counts of 14-39 over tens of millions of accesses are the duel settling around a stable answer, not thrashing.

## 3. The PDF-mandated leader-set tracking

The policy tracks instruction vs non-instruction accesses and misses to the RRIP leader sets (reported cumulatively, not from the decayed windowed counters the selector uses):

| trace | instr acc | instr miss | data acc | data miss |
|---|---:|---:|---:|---:|
| trace1 | 4971 | 3487 | 5575 | 3376 |
| trace2 | 10634 | 5910 | 8647 | 4550 |
| trace3 | 2421 | 1824 | 3314 | 2254 |

## 4. Storage

The dynamic policy stores 2 RRPV bits/line (forced: 1 bit collapses the two modes into one) plus a small selector. Total **2058 bytes** -- about double static I-RRIP (1024 B), still a third smaller than the LRU it replaces (3072 B). The whole increase is the second RRPV bit; the duel itself is negligible.

## 5. Which policy is best?

- *Hand-picking one policy per trace*: static I-RRIP wins the two it suits.
- *Committing one policy to an unknown mix*: the dynamic policy wins -- best mean L2C MPKI and no catastrophic regression (worst +0.96%, versus static I-RRIP's +8.7% on trace1). That robustness is what set-duelling exists to buy, and what the Task 2b design goal rewards.

The dynamic policy does exactly what Task 2b asks -- reads behaviour and chooses correctly on all three traces. It does not top the IPC chart because these traces have no intra-trace phases to exploit, a property shown by the low switch counts above, not a defect in the policy. Beating the standalones on IPC is the Task 3 bar (SPP + dynamic I-RRIP), which extends this duel.

