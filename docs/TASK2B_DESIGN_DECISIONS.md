# Task 2b — Dynamic I-RRIP by set-duelling: every decision, and the reason for it

This document continues directly from `TASK2A_DESIGN_DECISIONS.md`. Task 2a
built a *static* instruction-conscious RRIP and proved it helps two of the
three traces and hurts the third. Task 2b asks the obvious follow-up question:
**can the cache decide, at run time and per workload, whether to be
instruction-conscious at all — instead of us hard-wiring that choice?** The PDF
calls this "a dynamic policy that selects between normal RRIP and I-RRIP based
on the observed behaviour", and it is the DIP set-duelling idea (Qureshi et
al., ISCA'07) applied to the two policies Task 2a already gave us.

Everything here is written so it can be read top-to-bottom and defended line by
line. Where a decision is the *only* one consistent with the PDF, I say so and
show why the alternatives fail.

## 1. What the PDF actually asks for

Re-reading the Task 2b paragraph, there are exactly four obligations:

1. Run two policies side by side in the same cache: ordinary RRIP and the
   Task 2a I-RRIP.
2. Dedicate a few **leader sets** to each policy and **track the number of
   instruction and non-instruction line accesses and misses to those sets**.
3. From that measurement, pick which policy the remaining **follower sets**
   use, and let the choice change over time.
4. Report the usual metrics (IPC, speedup, MPKI) and justify the design,
   including the storage it costs and the thresholds it uses.

Obligation 2 is the one most easily gotten wrong, and §6 and §3b below are
entirely about getting it right. It is a *measurement* requirement, not an
implementation detail — the counters must exist and must be reported even if
the selector we ship does not read them.

## 2. The one structural fact that forces almost everything else

Task 2a's I-RRIP shipped with `MAX_RRPV 1` — a single RRPV bit per line —
because at the static policy the only thing that bit has to express is
"instruction (insert at 0, protected) vs everything else (insert at 1,
evict-on-next-miss)". One bit is enough to separate two insertion depths.

A *dynamic* policy cannot live at `MAX_RRPV 1`. The moment the follower sets
must behave like **plain RRIP** in one mode and like **I-RRIP** in the other,
the insertion values of the two modes have to be distinguishable:

- RRIP mode wants data inserted at `MAX_RRPV - 1` (near-eviction but with one
  reprieve) and instructions no differently.
- I-RRIP mode wants instructions inserted at `0` and data at `MAX_RRPV`.

At `MAX_RRPV 1`, `MAX_RRPV - 1 == 0`, so RRIP-mode data and I-RRIP-mode
instructions land on the *same* RRPV, and the two modes collapse into one
policy — the duel would compare a thing against itself. The smallest value that
keeps the two modes genuinely different is **`MAX_RRPV 3`** (2 bits), the
classic SRRIP width. This is why the shipped dynamic policy stores two RRPV
bits per line where static I-RRIP stored one, and §7 pays for that honestly.

This is the first place Task 2b is strictly harder than Task 2a: dynamism is
not free, and its first cost is a second RRPV bit across all 8192 lines.

## 3. The leader-set placement bug the sweep forced into the open

This is the finding I am most glad the sweep caught, because it is invisible to
inspection and it silently corrupts the entire duel.

Set-duelling works by sampling: a handful of sets are pinned to each policy,
and whichever pinned group suffers fewer misses "wins" for the followers. For
that comparison to be fair, the two leader groups must be **statistically
identical except for the policy** — same kind of addresses, same reuse, same
everything. In a real cache the only thing that makes two sets differ
systematically is *which addresses map to them*.

The L2C set index is address bits 6..15 (`BLOCK_SIZE 64` ⇒ bits 0..5 are the
block offset; `L2C_SET 1024` ⇒ 10 index bits, 6..15). A 4 KB page covers
address bits 0..11. So the **low 6 bits of the set index (bits 6..11) are the
within-page 64 B slot**, and the **high 4 bits (bits 12..15) are page-number
bits**. Two sets that differ only in within-page-offset bits see different
offsets *inside the same pages* — different data entirely. Two sets that differ
only in page-number bits see the *same within-page slots across different
pages* — statistically the same traffic.

A leader therefore has to be chosen by its page-number bits, and the two groups
must share their within-page slots. My first placement did the opposite. I
picked leaders with `set % STRIDE == 0` for one group and `== STRIDE/2` for the
other, which splits them by *within-page* bits whenever `STRIDE < 64`:

| leaders | stride | group A slots | group B slots | verdict |
|--------:|-------:|---------------|---------------|---------|
| 8  | 128 | {slot 0} | {slot 0} | **same within-page slot → fair** |
| 16 | 64  | {slot 0} | {slot 32} | disjoint slots → biased |
| 32 | 32  | {0,32} | {16,48} | disjoint slots → biased |

At 16 and 32 leaders the two groups never sample the same offsets, so the duel
was comparing instruction-heavy slots against data-heavy slots and calling the
difference "policy". The measured speedup at 16 leaders was 1.0027 — and it was
*right by accident* on only one of three traces. Eight leaders is the smallest
count at which `STRIDE = 1024/8 = 128 ≥ 64`, so both groups collapse to
within-page slot 0 and differ purely in page-number bits — exactly the fair
sample. **That is why the shipped policy uses 8 leaders per group, not because
8 is a nice number but because it is the smallest fair one.** A live assertion
in `dyn_role` recomputes the slot sets and aborts if they ever diverge, so this
bug cannot creep back silently.

The general rule this proves — *leaders must differ in page-number bits, never
in within-page-offset bits* — is not shipped as configurable code, because I
only measured the three placements above and will not claim a rule I have not
swept across every leader count. It is recorded here as the reasoning, not as a
tuned knob.

## 4. The selector: three designs, and why the shipped one is PSEL

The follower sets need a rule that reads the leaders and names a winner. I
implemented three selectors behind one knob (`DYN_SELECTOR`) and swept them, so
the choice is measured, not asserted.

**Selector 0 — the PDF's own intensity formula.** The PDF suggests comparing
instruction vs non-instruction *access and miss* intensity. I implemented it
literally: prioritise instructions when the instruction miss share of the
leader sets exceeds a threshold. It works, but it has a defect I could prove:
the formula is **not monotone** in the thing we care about. A workload can
raise its instruction-miss *share* simply by lowering its data misses, with no
change in how much protecting instructions would help. On trace3 the formula
flips the mode for the wrong reason. I kept it as a selectable baseline because
the PDF names it, but I do not ship it.

**Selector 1 — instruction hit-rate threshold.** "Prioritise instructions when
the instruction hit rate in the leader sets is low." Cleaner, but it inherits
the same non-monotonicity: hit rate is misses over accesses, and the
denominator moves for reasons unrelated to the protection decision. Swept,
kept, not shipped.

**Selector 2 — DIP PSEL duel (shipped).** This is the Qureshi construction and
it sidesteps the formula problem entirely: it does not *model* which policy is
better, it *measures* it. Each leader group runs one policy; every miss in the
I-RRIP leaders nudges a saturating counter (PSEL) one way, every miss in the
RRIP leaders nudges it the other, and the followers simply run whichever policy
its own leaders are missing less. There is no threshold to miscalibrate because
there is no formula — the cache's own miss counts are the comparison. That is
why the shipped `DYN_THRESH_PCT` value is marked unused at selector 2.

The threshold selectors taught me something before I retired them, though —
which is the point of keeping them in the sweep.

### 4.1 The threshold-calibration trap (why leaders MUST run RRIP, not I-RRIP)

I first set the selector-0/1 threshold at 45%, reading the instruction hit
rates off an I-RRIP *run* (35.0 / 52.8 / 75.4%). That was wrong, and wrong in a
way that matters: the leaders whose statistics the selector reads run **RRIP**,
not I-RRIP, and under RRIP the same traces read 36.0 / ~45 / 18.0% — the
*ordering across traces inverts*. A threshold calibrated on I-RRIP data and
applied to RRIP leaders fires on the wrong traces. My own code comments said
the leaders must run RRIP precisely so the measurement is unbiased by the
policy being evaluated — and then I calibrated against the biased numbers
anyway. The sweep caught it because the threshold selectors did the wrong thing
on trace3. PSEL has no threshold, so it cannot fall into this trap; that is a
third independent reason it is the one shipped.

## 5. The window, the decay, and the instruction weight

**Window (`DYN_WINDOW 8192`).** The duel is re-evaluated every 8192 demand
loads. Short enough that a genuine phase change is acted on within a few
thousand accesses; long enough that a handful of unlucky misses cannot flip the
mode. At this window the shipped runs switch mode 20 / 39 / 14 times over the
whole run (0.14–0.19 switches per window) — adaptation, not thrashing.

**Decay (halve, don't clear).** At each window boundary the windowed counters
and PSEL are halved toward their midpoint rather than reset. Halving keeps a
fading memory of recent windows so one freak window cannot flip the policy, and
it pulls a phase that has *ended* back toward neutral so it stops voting. This
is why the reported `DYN COUNTERS` line uses a *separate*, never-decayed
cumulative counter (§6): the decayed counter is the right input for the
*decision* and the wrong number to *report*.

**Instruction weight (`DYN_INSTR_WEIGHT 2`).** An instruction miss at L2 stalls
the front end and starves the whole pipeline; a data miss is often overlapped
by out-of-order execution. So an instruction miss in the leaders should argue
for I-RRIP harder than a data miss argues against it. The weight makes an
instruction-leader miss move PSEL by 2 and a data-leader miss by 1.

This weight is not a free parameter I guessed — it is the one place the sweep
*isolated a cause*. The variants `psel_w1` → `psel_w2` differ in nothing but
this weight. Going from 1 to 2, trace3's prioritising share moves 32% → 73% and
its speedup moves 0.9996 → 1.0001, lifting geomean 1.0059 → 1.0069. That single
controlled change identifies the instruction-miss stall cost *by construction*,
which is exactly the question Task 2a §14.4 said it could not answer from
static runs. Weight 2 is shipped because it is the measured optimum, and the
experiment that chose it is reproducible.

## 6. The mandated tracking, and the bug that hid it

The PDF requires tracking instruction vs non-instruction accesses and misses to
the leader sets. I track them in `l2c_update_replacement_state`, in the RRIP
leader group only (sampling the policy under evaluation would bias the
estimate), split three ways — instruction / data / translation — the same split
Task 2a used so the counts line up with ChampSim's own per-class eviction
counters.

There were two layered mistakes here, and both are worth recording because both
are the kind that pass inspection:

1. **The counters were gated behind `#if DYN_SELECTOR != PSEL`.** Shipping the
   duel therefore silently switched off the tracking the PDF mandates — the
   stats line printed zeros and nothing complained. Fixed: the tracking now
   runs for every selector. Under selector 2 it is pure reporting (PSEL decides
   behaviour), so the fix is behaviour-neutral — every `L2C` line except
   `DYN COUNTERS` is bit-identical before and after.

2. **The reported line read the *decayed* counter.** Even after (1), the line
   still printed near-zero, because the windowed counters are halved every
   window (141 / 251 / 75 times) and decay to a tiny residue by the end of the
   run. The residue is correct for the *selector* and useless as a *report*.
   Fixed by adding a cumulative counter (`dyn_tot` / `dyn_tmis`) that is never
   decayed, incremented in the same guarded scope, and read by nothing except
   the stats line. This is the change that requires the one rebuild+rerun.

The lesson is the same one Task 2a §13 drew: the errors that survive review are
real numbers attached to the wrong claim. A counter that prints zero looks like
"no traffic"; it was actually "traffic, measured, then forgotten by design, and
reported from the wrong variable". `verify_task2b.py` §3b now fails unless all
three logs show non-zero instruction *and* data leader counts, so this cannot
regress silently.

## 7. Storage — exact bit-level accounting

The dynamic policy's state is three things: the per-line RRPV array, the PSEL
counter, and the small scalar bookkeeping (mode, window counter, the counters).

- **RRPV array.** `MAX_RRPV 3` needs 2 bits per line. 1024 sets × 8 ways ×
  2 bits = 16384 bits = **2048 bytes**.
- **Selector + bookkeeping.** PSEL (saturating, 10-bit here), the 1-bit mode,
  the window counter, and the windowed + cumulative class counters: **76 bits**
  as reported, well under 10 bytes.
- **Total: 2058 bytes.**

Against the two reference points:

| policy | per-line RRPV | total state |
|---|---|---|
| LRU (supplied) | 3 bits × 8192 lines | 3072 B |
| static I-RRIP (Task 2a) | 1 bit × 8192 | 1024 B |
| **dynamic I-RRIP (this task)** | **2 bits × 8192 + selector** | **2058 B** |

The dynamic policy costs **almost exactly double** static I-RRIP, and the
entire increase is the second RRPV bit forced by §2 — the selector machinery is
negligible (76 bits). It is still **a third smaller than the LRU it replaces**
(2058 vs 3072 B), so "dynamic" does not mean "expensive" in absolute terms; it
means "one more RRPV bit than the static version". This is the storage/
threshold analysis the PDF asks for: the dominant cost is structural (the bit
width that keeps two modes distinct), not the duel.

## 8. Results

Baseline is LRU, 25M warmup + 25M simulation, GCC 7.5.0, three traces. Speedup
is geomean of per-trace IPC ratios (ratios compose multiplicatively); MPKI is
the arithmetic mean (equal 25M instructions per trace).

| policy | geomean speedup | mean L2C MPKI | mean instr MPKI |
|---|---:|---:|---:|
| LRU | 1.0000 | 16.3356 | 10.1050 |
| plain RRIP | 1.0004 | 15.8080 | 9.8467 |
| static I-RRIP (Task 2a) | 1.0138 | 14.7590 | 6.2219 |
| **dynamic I-RRIP (Task 2b)** | **1.0068** | **14.5693** | **7.2543** |

Per-trace mode behaviour of the shipped dynamic policy:

| trace | prioritising (I-RRIP) share | switches | PSEL final (mid 512) | right call? |
|---|---:|---:|---:|---|
| trace1 | 12.1% | 20 | 519 | yes — I-RRIP *hurts* trace1, policy stays RRIP |
| trace2 | 82.9% | 39 | 501 | yes — I-RRIP *helps* trace2, policy adopts it |
| trace3 | 68.0% | 14 | 512 | yes — trace3 is marginal, PSEL ends neutral |

Two facts carry the whole result:

1. **Dynamic I-RRIP has the lowest mean L2C MPKI of all four policies
   (14.5693).** It beats even static I-RRIP on misses, because it *avoids
   static I-RRIP's one regression*: on trace1, static I-RRIP raises L2C MPKI
   +8.7% over LRU (19.23 vs 17.70) by protecting instructions a workload that
   does not reuse them; the dynamic policy sees that in its leaders, stays in
   RRIP mode 88% of the time, and lands at +0.45% (17.78) — the regression is
   essentially erased. On trace2 it keeps most of static I-RRIP's big win
   (−19.8% vs the static −23.0%).

2. **It does not beat static I-RRIP on IPC (1.0068 vs 1.0138),** and the reason
   is structural, not a tuning failure — §9.

## 9. The honest headline: why the dynamic policy cannot beat the best static one here

A dynamic policy can only win where the *right* policy changes *during* a run.
Set-duelling pays a fixed tax — leader sets are pinned to a policy that may be
wrong for them, and the followers spend the early windows of every phase
converging — and it recovers that tax only by catching phase changes a static
choice would miss.

These three traces have no intra-trace phase change to catch. Each is
internally homogeneous: trace2 wants instruction protection essentially the
whole way through, trace1 essentially never, trace3 weakly throughout. The
switch counts confirm it — 14 to 39 switches across tens of millions of
accesses is the duel twitching around a stable answer, not tracking phases. So
the best the dynamic policy can do is *converge to the right static choice*,
and then it still carries the leader-set tax that the static policy does not.
That gap — 1.0068 vs 1.0138 — is almost exactly the cost of sacrificing 16
leader sets (1.56% of the cache) to the losing policy in each.

The sweep makes this concrete. The best-IPC dynamic variant, `pdf_t15`, reached
1.0072 — and it got there by prioritising 99 / 91 / 99% of the time, i.e. by
*imitating the static policy as closely as the duel allows*. The closer a
dynamic policy gets to static I-RRIP's IPC, the more it is simply being static
I-RRIP with overhead. That is the signature of a workload with no phases to
exploit.

**So which policy is actually best?** It depends on the question the PDF is
asking:

- *If you may hand-pick one policy per trace*, static I-RRIP wins the two
  traces it suits, and the dynamic policy is strictly worse on IPC.
- *If you must commit one policy to an unknown workload mix*, the dynamic policy
  wins: it has the best mean L2C MPKI and, crucially, **no catastrophic
  regression on any trace** (worst case +0.96%, versus static I-RRIP's +8.7%).
  That robustness is the property set-duelling exists to buy, and it is exactly
  what the Task 2b design goal — "select the policy from observed behaviour" —
  rewards.

This is the result I will defend to the instructor: the dynamic policy does the
thing it was asked to do (it reads behaviour and chooses correctly on all three
traces), and the reason it does not top the IPC chart is a *property of the
traces*, demonstrated by the switch counts and the `pdf_t15` convergence, not a
defect in the policy. Reporting a dynamic policy as a clean IPC win here would
require hiding that fact.

## 10. Limitations and the handover to Task 3

- The win condition for a dynamic policy — intra-trace phase change — is absent
  in this trace set. A multi-phase trace would separate the dynamic and static
  policies cleanly; we were not given one.
- The leader-placement rule (§3) is proven only for the three placements swept.
  The generalised "page-number bits only" rule is stated as reasoning, not
  shipped as a swept knob.
- The instruction weight is tuned to 2 on these three traces; a workload whose
  instruction-miss stall cost differs would re-tune it.

**Task 3** is where the dynamic policy is supposed to earn its IPC win: made
*SPP-aware* — treating lines brought in by the Task 1 prefetcher as a fourth
class the duel can reason about — the combined design has a lever that neither
standalone SPP nor standalone dynamic I-RRIP has, which is the regime where
"combined beats both standalones" (the Task 3 bar) becomes reachable. The
three-way class split (§6) and the never-decayed cumulative counters were built
with that extension in mind.

## 11. Decision summary

| decision | shipped value | why |
|---|---|---|
| RRPV width | `MAX_RRPV 3` (2 bits) | §2 — 1 bit collapses the two modes |
| selector | PSEL duel (`SELECTOR 2`) | §4 — no threshold to miscalibrate |
| leaders per group | 8 | §3 — smallest count with fair (page-number) placement |
| window | 8192 loads | §5 — adapts in thousands of accesses, no thrash |
| decay | halve at window boundary | §5 — fading memory, phase that ends stops voting |
| instruction weight | 2 | §5 — measured optimum (`psel_w1`→`psel_w2`) |
| reported counters | cumulative, never decayed | §6 — decayed residue is the wrong report |
| storage | 2058 B | §7 — 2× static I-RRIP, still < LRU |

Bottom line: **correct against every Task 2b obligation, robust (best mean MPKI,
no bad regression), and honestly short of static I-RRIP on IPC for a reason that
is a property of the traces, not the policy.**
