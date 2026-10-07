# Task 3 — SPP + dynamic I-RRIP: every decision, and the reason for it

This continues `TASK2B_DESIGN_DECISIONS.md`. Task 2b built a dynamic
instruction-conscious L2 policy and was honest that it could not beat the best
*static* choice on IPC, because the traces have no intra-trace phases to exploit.
Task 3 is where that policy is supposed to earn an IPC win — not by finding
phases, but by **combining two orthogonal mechanisms**: SPP (a data prefetcher,
Task 1) and dynamic I-RRIP (instruction-aware replacement, Task 2b). The PDF's
bar is explicit: the combined design must **beat both standalones in IPC**.

Everything here is decided from measurements we already have (Task 1 and Task 2
logs) and from a sweep run for this task; where a number is quoted it comes from
a log, and §7 records the predictions *before* the Task 3 runs so they can be
checked honestly afterwards.

## 1. What the PDF actually asks for

> "modify your dynamic I-RRIP policy to incorporate awareness of lines brought
> in by SPP (hint: check packet type as PREFETCH or not), outperforming both
> dynamic I-RRIP and standalone SPP in IPC."
> Deliverables: IPC, speedup, prefetch accuracy, coverage, and Load MPKI of
> L1D, L2C, L2 Instruction and L2 Data, tabulated and plotted; and the rationale
> for how the replacement policy handles the prefetch packet.

Two things to notice. First, the step says modify **`replacement/dyn_irrip.l2c_repl`
itself** — the same file as Task 2b, not a new policy. Second, the bar is a
*comparison against two standalones*, not against LRU; beating LRU would prove
nothing, since both standalones already do.

## 2. The bar, measured from our own earlier runs

| standalone | geomean speedup vs LRU | source |
|---|---:|---|
| SPP alone (`spp` + LRU) | **1.0149** | Task 1, `results/task1/spp_*` |
| dynamic I-RRIP alone (`no` + `dyn_irrip`) | **1.0068** | Task 2b, `results/task2b/dyn_irrip_*` |

The combined design must clear **1.0149** — SPP alone is the stronger of the two,
so the hard part is adding I-RRIP's instruction protection *without surrendering
SPP's data-miss gains to cache pollution*. That single sentence is the whole
engineering problem of Task 3.

## 3. Why the combination *can* win — per-trace SPP behaviour

From `results/task1/task1.csv` (SPP standalone):

| trace | SPP accuracy | SPP L1D coverage | who carries this trace |
|---|---:|---:|---|
| trace1 | 56.7% | 10.5% | mild — both help a little |
| trace2 | 54.6% | **4.0%** | **I-RRIP** — SPP barely helps; Task 2b ran 82.9% I-RRIP here |
| trace3 | 47.7% | **18.5%** | **SPP** — the big prefetch win |

The two standalones win *different* traces: SPP carries trace3, instruction
protection carries trace2. A policy that keeps both behaviours collects both
wins, and that is how the combined design can beat each standalone — which wins
only its own regime. Crucially this does **not** require intra-trace phases
(the thing Task 2b lacked): the two mechanisms act on different traffic
(prefetched data vs demanded instructions) within the *same* steady state.

## 4. The central tension — accuracy is ~50%, not ~10% and not ~90%

SPP's accuracy is 47.7–56.7%. That number decides the design:

- If accuracy were ~90%, prefetches are almost always useful → protect them like
  demand lines. If it were ~10%, prefetches are almost always junk → insert them
  at evict-next and never look back.
- At ~50% both halves matter. Standalone SPP+LRU inserts every prefetch at MRU
  (fully protected), so the useless ~half sits in the cache evicting demand
  lines — that is the pollution the combined policy can remove. **But** the
  useful ~half must survive long enough to get its demand hit, so inserting all
  prefetches at `MAX_RRPV` (evict-next) risks throwing the good half away and
  *losing* to SPP+LRU.

So the prefetch insertion depth is not a value to argue about — it is a
measured trade-off. §5 makes it a knob; §7 sweeps it; the shipped value is set
from the logs.

## 5. The design: prefetch-aware insertion, and nothing more

The edit to `dyn_irrip.l2c_repl` is deliberately small — the Task 2a lesson was
that a one-idea change should be a one-idea diff.

**On insertion**, a fill with `type == PREFETCH` is a speculative line. When
`DYN_SPP_AWARE` is on it is inserted at `DYN_PF_INSERT`, a single RRPV value,
*the same in both duel modes*. A speculative line is speculative whether or not
this window is prioritising instructions, so the prefetch depth does not depend
on the mode — which keeps the change from interacting with the duel.

**On a demand hit** to a line still flagged as prefetched (`block.prefetch == 1`,
read before `src/cache.cc:1849` clears it), the prefetch has just proven correct;
it then promotes exactly like a demand line. **Protection is earned by proven
use, never granted on speculation.** This is the PACMan (Wu et al., MICRO'11)
insight applied to our duel: insert speculative, promote on demand.

**In the duel**, prefetch fills are unchanged — they do not vote. Task 2b
already restricted the PSEL vote and the leader-set counters to demand `LOAD`s,
precisely because a writeback or a prefetch is not what the core is waiting on.
So the duel still chooses RRIP vs I-RRIP from *demand* behaviour, and prefetch
awareness is a pure insertion-policy layer on top. The three mechanisms never
fight: SPP cuts data-miss latency, the duel protects instruction reuse, and
prefetch-aware insertion stops SPP from polluting what the duel protects.

**Two knobs, one of them an ablation:**

- `DYN_SPP_AWARE` (default 1). When 0, a prefetch is treated as ordinary data —
  i.e. "dynamic I-RRIP that ignores prefetch origin". The sweep runs this so we
  can prove that *awareness*, not merely *adding SPP*, is what moves IPC. A
  combined policy that only added the prefetcher and did nothing in the
  replacement logic would be indistinguishable from this ablation.
- `DYN_PF_INSERT` (an RRPV, swept). The insertion depth from §4.

**Inert without a prefetcher — why the PDF can ask us to edit the same file.**
Task 2b builds with `no` L1D prefetcher, so no `PREFETCH` fill ever reaches the
L2, `pf` is always 0, the aware branch and the two counters never execute, and
the only additions to the output are one new config field and one new stats
line. The Task 2b L2 behaviour is therefore unchanged — `verify_task3.py` §3
checks this by requiring the standalone `dyn_irrip_t3` (no prefetcher) logs to
reproduce the Task 2b `dyn_irrip` logs line-for-line. That check is the proof,
not this paragraph.

## 6. The rationale the PDF asks for — handling the prefetch packet

Stated as plainly as possible, because it is a graded deliverable:

> A prefetched line is a *prediction*. Giving a prediction the same cache
> protection as a line the program actually demanded is a bet that the
> prediction is right. SPP is right about half the time, so that bet loses half
> the time, and a lost bet means a useful demand line was evicted to hold a line
> nothing will use. The replacement policy therefore inserts a prefetched line
> shallow enough that a wrong prediction is cheap to undo (it ages out before it
> displaces much), and promotes it to full protection only when a real demand
> access confirms the prediction was right. The prefetcher proposes; the
> replacement policy refuses to pay for the proposal until the workload accepts
> it.

That is the entire philosophy, and it is why the combined design can beat
standalone SPP (which pays up front, via LRU's MRU insertion) rather than merely
equalling it.

## 7. The sweep, and predictions recorded before the runs

`scripts/sweep_task3.py` runs four variants, all built **with SPP**, all on the
shipped Task 2b duel (selector 2, 8 leaders, weight 2) so only the prefetch
handling changes:

| id | SPP_AWARE | PF_INSERT | question it answers |
|---|---|---|---|
| `unaware` | 0 | — | does awareness matter at all, vs just adding SPP? |
| `pf_max` | 1 | 3 (`MAX_RRPV`) | is maximal anti-pollution (evict-next) best? |
| `pf_max1` | 1 | 2 (`MAX-1`) | or one reprieve before eviction? |
| `pf_mid` | 1 | 1 | or does the useful half need more protection? |

Predictions (to be confirmed or refuted in §9):

1. **Every aware variant beats dynamic I-RRIP alone**, because SPP's coverage
   (4–18%) removes L1D misses the policy alone cannot. The interesting question
   is whether any variant also beats *SPP alone*.
2. **`unaware` is already non-trivial**, because in I-RRIP mode data (and hence
   an unaware prefetch) already inserts at `MAX_RRPV` — so the ablation is not
   "LRU-style protection", it is "whatever the mode does with data". If `unaware`
   alone beats both standalones, the explicit knob earns less than expected and
   I will say so.
3. **`pf_max` risks over-evicting on trace3**, where coverage is highest (18.5%)
   and the useful prefetches most need to survive to their demand hit; `pf_max1`
   or `pf_mid` may win there. The shipped `DYN_PF_INSERT` is whichever aware
   variant has the best geomean speedup *and* clears both standalones.
4. **The "collects both wins" signature**: the combined policy's mean L2
   *instruction* MPKI should stay close to dynamic-I-RRIP-alone (protection
   preserved) while its mean L2 *data* MPKI drops toward or below SPP-alone
   (prefetch benefit). If instead instruction MPKI rises, the prefetches are
   displacing instruction lines and the orthogonality claim is wrong.

## 8. Storage

Prefetch awareness adds **no per-line state**: the speculative/ demand
distinction on insertion comes from the `type` argument the simulator already
passes, and the "was this a prefetch" check on a hit reads ChampSim's existing
`block.prefetch` bit — not a bit this policy stores. The only new state is two
whole-run counters (prefetch inserts, useful-at-L2), which are reporting, not
policy. So the combined policy's footprint is the **same 2058 bytes** as the
Task 2b duel (2-bit RRPV × 8192 lines + the selector), and the storage argument
of `TASK2B_DESIGN_DECISIONS.md` §7 carries over unchanged. Prefetch awareness is
free in state; it only changes which RRPV a prefetch is given.

## 9. Results

Baseline LRU, 25M warmup + 25M simulation, GCC 7.5.0, three traces. Shipped
combined config = `spp` + dynamic I-RRIP with `DYN_SPP_AWARE 1`, `DYN_PF_INSERT 3`
(the sweep winner, §9.4). Every figure is from `results/task3/*.txt`.

### 9.1 Headline — the Task 3 bar is met

| policy | geomean speedup | mean L1D MPKI | mean L2C MPKI | mean L2 instr | mean L2 data |
|---|---:|---:|---:|---:|---:|
| LRU (baseline) | 1.0000 | 9.2064 | 16.3355 | 10.1050 | 6.2305 |
| SPP alone | 1.0149 | 8.4431 | 15.6627 | 10.1670 | 5.4957 |
| dynamic I-RRIP alone | 1.0068 | 9.2089 | 14.5693 | 7.2543 | 7.3150 |
| **SPP + dynamic I-RRIP (combined)** | **1.0218** | **8.4480** | **13.8400** | **7.2537** | **6.5863** |

Combined **1.0218** beats SPP-alone **1.0149** and dynamic-I-RRIP-alone **1.0068**
— both bars cleared, which is exactly what the PDF asks. It also has the lowest
mean L2C MPKI of any policy across all four tasks (13.8400).

### 9.2 The mechanism — it literally collects both wins (prediction #4)

Read the last two columns of the table. The combined policy's L2 **instruction**
MPKI is 7.2537, essentially identical to dynamic-I-RRIP-alone's 7.2543 — the
instruction protection is fully preserved. Its L2 **data** MPKI is 6.5863, down
from dynamic-I-RRIP-alone's 7.3150 and most of the way to SPP-alone's 5.4957 —
the prefetch benefit is captured. So the two mechanisms genuinely add on
different traffic: SPP removes data misses, the duel protects instruction reuse,
and the two do not trade against each other. That is the orthogonality claim
from §3/§5, confirmed in numbers rather than argued.

### 9.3 Per-trace honesty — where the win comes from

| trace | SPP alone | dyn I-RRIP alone | combined |
|---|---:|---:|---:|
| trace1 | 1.0094 | 0.9990 | 1.0084 |
| trace2 | 1.0120 | 1.0229 | **1.0358** |
| trace3 | 1.0232 | 0.9987 | 1.0215 |

The aggregate win is driven by **trace2**, where instruction protection matters
most (Task 2b ran 82.9% I-RRIP here): combined 1.0358 far exceeds SPP-alone's
1.0120. On the two SPP-favoured traces the combined is a hair *behind* SPP-alone
(trace1 1.0084 vs 1.0094, trace3 1.0215 vs 1.0232) — the duel's leader sets cost
a little where prefetching alone was already the right answer. The geomean
clears both bars because trace2's large win outweighs those two small costs.

The other half of the story: dynamic-I-RRIP-alone *regresses* on trace1 (0.9990)
and trace3 (0.9987) — prioritising instructions without a prefetcher hurts those
data-hungry traces. The combined policy **recovers both** (1.0084, 1.0215)
because SPP supplies the data lines the duel alone could not. So the combination
fixes each standalone's specific weakness, which is the strongest possible form
of "beats both".

### 9.4 Prediction scorecard (recorded in §7 before the runs)

- **#1 — every aware variant beats dyn-alone: CONFIRMED.** All four variants land
  ~1.021 vs dyn-alone's 1.0068.
- **#2 — the unaware ablation is non-trivial: CONFIRMED, and it is the key honest
  finding.** `unaware` scores 1.0215 vs `pf_max`'s 1.0218 — explicit awareness
  adds only **+0.0003**. The reason is exactly §5's structure: in I-RRIP mode the
  duel already inserts data (and therefore an unaware prefetch classified as
  data) at `MAX_RRPV`, so awareness only changes behaviour in RRIP-mode sets,
  where it bumps a prefetch from `MAX-1` to `MAX`. On these traces, which run
  I-RRIP-heavy where it matters, that is nearly redundant. **The combined design's
  win over both standalones is real, but it comes from the orthogonal
  *combination*, not from the prefetch-awareness *tuning*.** Said plainly so it
  can be defended: adding SPP to the duel is what wins; the `type==PREFETCH`
  refinement the PDF asks for is correct and measured but earns ~0.03% here.
- **#3 — pf_max over-evicts on the high-coverage trace3: REFUTED.** `pf_max`
  (insert at evict-next) is actually the *best* variant on trace3 (1.0215, vs
  pf_max1 1.0207, pf_mid 1.0212). Inserting prefetches at `MAX_RRPV` costs
  nothing even where coverage is 18%, because SPP's useful prefetches are timely
  — they receive their demand hit (and promote) before the aging loop reaches
  them — while the useless half is discarded fastest. Max anti-pollution is free.
- **#4 — the "collects both wins" signature: CONFIRMED** (§9.2).

### 9.5 Why `DYN_PF_INSERT 3` (pf_max) is shipped

It has the best geomean speedup (1.0218) and clears both bars. It ties the other
aware variants and the unaware ablation within 0.03% — a near-flat response, for
the reason in #2 — but it is deterministically the best, it is the simplest
choice to justify (a speculative line gets the least protection; a demand hit
earns it back), and #3 shows it carries no penalty on the high-coverage trace.
The sweep is in `results/task3_sweep/`; `spp_dyn_irrip` reproduces the `pf_max`
row bit-for-bit, since both are `DYN_PF_INSERT 3`.

## 10. How this closes the arc from Task 1

- **Task 1** built SPP and measured its accuracy and coverage. Those exact
  numbers (48–57% accuracy) are what make §4's trade-off real rather than
  hypothetical — the design is parameterised by a property we measured, not
  assumed.
- **Task 2a** found that data lines have low reuse and instruction lines high
  reuse; a prefetched data line is the *least*-proven line of all, which is why
  it is the natural candidate for the shallowest insertion.
- **Task 2b** built the duel and restricted it to demand traffic. That decision,
  made for a different reason (unbiased phase measurement), is exactly what lets
  prefetch awareness bolt on without disturbing the mode selection.
- **Task 3** is therefore not a new policy but the composition of three
  decisions each made earlier for its own reason, which is the cleanest kind of
  result: the pieces were built to fit before the fit was needed.
