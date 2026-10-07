# Task 2a — I-RRIP: every decision, and the reason for it

This is the "why" document. `docs/TASK2A_IRRIP.md` walks the code line by line;
`docs/TASK2A_RUN_INSTRUCTIONS.md` is the build-and-run recipe. This file records
the reasoning, the alternatives that were rejected, and — importantly — the
predictions I am making **before** the sweep runs, so that when the numbers come
back it is obvious which of my arguments survived and which did not.

---

## 1. What the PDF actually asks for

Two requirements and two deliverables, quoted:

> You need to extend the `update_replacement_state` (used for insertion and
> promotion) function to accept a parameter, exposing your replacement policy to
> the information of whether the cache line is an instruction line or not. By
> default I-RRIP won't build until you finish this step.

> Make changes to the three parts of a replacement policy (insertion, promotion,
> and eviction) to prioritize cache lines containing instruction lines over
> non-instruction lines. Your goal should be to reduce L2 load instruction MPKI.

> * Report the IPC, speedup, and Load MPKI of L2C, L2 Instruction, and L2 Data in
>   tabular form, and plot them.
> * Explain the rationale behind modifying **or not modifying** insertion,
>   promotion, and eviction logic. Defend why your way is the best.

Three things follow from reading that carefully:

1. **The objective is named and it is not IPC.** "Your goal should be to reduce
   L2 load instruction MPKI." IPC is a *reported* metric, not the target. This
   matters, because (see §9) IPC on these traces cannot resolve differences this
   small, and a design tuned to IPC noise would be tuned to nothing.
2. **"or not modifying" is explicitly allowed**, and the deliverable asks me to
   defend the choice either way. A policy that changes all three parts because
   the sentence lists three parts has not answered the question. The question is
   *which* parts should change and why.
3. **The signature change is mandatory**, not optional, and the PDF tells us how
   we will know we have done it: the supplied I-RRIP build will start working.

---

## 2. The measurement that came first

Before designing anything I asked whether this task has any headroom at all, and
on which traces. All of this came out of the **Task 1 logs that already exist** —
no new simulation was needed, because Task 1's baseline (`no` prefetcher + `lru`
at L2) is exactly the Task 2a baseline.

### 2.1 Instruction misses dominate the L2 load stream

| trace | L2C load MPKI | instruction | data | instruction share |
|---|---|---|---|---|
| trace1 | 17.6956 | 10.3377 | 7.3580 | **58.4 %** |
| trace2 | 27.3568 | 18.8533 | 8.5035 | **68.9 %** |
| trace3 |  3.9542 |  1.1241 | 2.8302 | 28.4 % |

So the PDF's framing is real for these traces: trace1 and trace2 behave like the
server workloads it describes, where the instruction footprint has outgrown the
L1I and the L2 is carrying it. trace3 is the desktop-like case.

L2 load **hit** rates on the same runs are 29.7 % / 48.9 % / 28.5 %. The L2 is
missing most of what is asked of it, which is the regime where RRIP's whole
premise — "do not give a new line the benefit of the doubt" — applies.

### 2.2 How often a data fill destroys an instruction line

ChampSim already counts this. `src/cache.cc:375-396` classifies every L2
eviction by what the victim was and what replaced it, and `src/main.cc:306-314`
prints all nine combinations. Nobody had looked at them:

| trace | instruction victims | killed by an **instruction** fill | killed by a **data** fill | killed by a **translation** fill |
|---|---|---|---|---|
| trace1 | 257 967 (43.2 % of all evictions) | 112 800 (43.7 %) | **120 225 (46.6 %)** | 24 942 (9.7 %) |
| trace2 | 462 640 (55.9 %) | 298 635 (64.6 %) | **136 147 (29.4 %)** | 27 858 (6.0 %) |
| trace3 |  30 733 (20.1 %) |   8 097 (26.3 %) | **19 415 (63.2 %)** |  3 221 (10.5 %) |

**The bolded column is the entire addressable headroom of Task 2a.** An
instruction-conscious policy can only ever recover instruction lines that a
*non-instruction* fill would have thrown out. It can do nothing about the
instruction-evicts-instruction column, because there is no type preference to
express between two lines of the same type.

### 2.3 The non-obvious insight this produces

A high instruction MPKI does **not** imply an instruction-versus-data conflict.

trace2 has the highest instruction MPKI of the three (18.85, 69 % of its load
misses) and is therefore the trace one would naively expect I-RRIP to help most.
But **64.6 % of trace2's instruction victims are evicted by other instruction
lines.** Its problem is that the instruction working set alone does not fit in
its share of a 1024×8 L2 — a *capacity* problem. Prioritising instructions over
data cannot fix a capacity problem; there is no data to take the space from in
the sets that matter.

Meanwhile trace3 has the *lowest* instruction MPKI (1.12) but the *highest*
proportion of instruction victims killed by data (63.2 %) — the cleanest
type-conflict of the three, just in small absolute numbers.

So before running anything, the ranking I expect is **trace1 first** (large
absolute headroom, 120 K data-on-instruction conflicts, and a 46.6 % share),
then trace3 proportionally, with **trace2 gaining least relative to its
instruction MPKI**. If trace2 turns out to gain the most, one of my assumptions
is wrong and §9 says what that would mean.

trace2 is also where the *risk* lives: it has 310 745 data victims. Squeezing
data there has somewhere real to go wrong.

### 2.4 Translation lines are a third class, and they are not negligible

6–10.5 % of instruction-line evictions are caused by an address-translation
fill. An instruction page walk stalls the frontend every bit as surely as an
instruction miss does, so "instruction-conscious" arguably ought to cover them.
But ChampSim does **not** file them as instruction lines: `fill_cache()`
(`src/cache.cc:2924-2932`) sets `block.translation = 1` and leaves
`block.instruction = 0` for `LOAD_TRANSLATION`, even though the *packet* arrives
with `instruction == 1` when it is an instruction page walk.

I therefore treat translations as their own class with their own knob rather than
silently folding them into either side. §6.4 explains the default.

---

## 3. What ChampSim gives us (and what the wiki does not)

Instruction 4 said to read the ChampSim wiki's Modules page first. I did, and the
most useful thing it produced was a warning:

**The wiki documents a different generation of ChampSim than this repo.**
Upstream ChampSim has `champsim::modules::replacement`, an `access_type` enum,
`champsim::address`, and hooks named `replacement_cache_fill()` /
`replacement_update_state()`. This fork uses the older style: `CACHE::l2c_*`
member functions, a raw `uint32_t type`, raw `uint64_t` addresses, and function
pointers assigned in `src/main.cc:1329-1330`. **None of the wiki's signatures can
be copied into this tree.** What the wiki is still good for is the conceptual
model — that a replacement policy is exactly three hooks (initialise, find
victim, update state), and that the update hook serves both insertion and
promotion — and that model is what the design below is organised around.

What the repo itself gives us, which turned out to matter far more:

| facility | where | why it matters here |
|---|---|---|
| `BLOCK::instruction`, `BLOCK::translation` | `inc/block.h:9-16`, maintained for L2C by `fill_cache()` at `src/cache.cc:2922-2932` | the *resident* line's class is already stored per way, so **eviction needs no plumbing change at all** — `find_victim` receives `const BLOCK *current_set` |
| `PACKET::instruction` | `inc/block.h:74` | the *incoming* line's class, the thing the PDF's hint points at |
| `fill_packet_type` | `src/cache.cc:60-71` | the TA's own 3-way classifier (1 translation / 2 instruction / 3 data) — I reuse the identical split, see §5 |
| the nine `*_evicting_*` counters | `inc/cache.h:152-160`, printed `src/main.cc:306-314` | §2.2; free, per-run evidence about the mechanism |
| `L2C_SET 1024`, `L2C_WAY 8` | `inc/cache.h:93-94` | 8192 lines ⇒ the storage arithmetic in §7 |

The `BLOCK::instruction` discovery changes the shape of the whole task: of the
three parts of the policy, **only insertion is actually blocked** by the missing
parameter. Eviction could have been written today. §6 argues that it still
should not be.

---

## 4. The mandated plumbing change

### 4.1 The signature was not mine to choose

`replacement/rrip.l2c_repl:38` — a file the handout ships — already declares:

```c
void CACHE::l2c_update_replacement_state(uint32_t cpu, uint32_t set, uint32_t way,
        uint64_t full_addr, uint64_t ip, uint64_t victim_addr, uint32_t type,
        uint8_t hit, uint8_t isInstruction)
```

Nine parameters. Every other module in the tree, and `inc/cache.h:341-352`, had
eight. **That mismatch is the build failure the PDF predicts.** It also means the
TA has already picked the parameter's name, position and type, so I matched it
byte for byte rather than inventing `is_instr` or an enum. Anything else would
have required editing a supplied reference file to make my own code build, which
is the wrong way round.

Incidentally this explains why nobody hit the break during Task 1: Task 1 only
ever built with `lru` as the L2C policy, so `rrip.l2c_repl` was never compiled.

### 4.2 The 27 declarations

`uint8_t isInstruction` appended to every 8-parameter `update_replacement_state`
— **27 signatures across 18 files**:

| file(s) | signatures |
|---|---|
| `inc/cache.h` | 10 — the `(CACHE::*update_replacement_state)` function pointer plus the nine per-level members. The function pointer **must** change too, or `src/main.cc:1329` fails to assign `&CACHE::l2c_update_replacement_state` to it. |
| `replacement/base_replacement.cc` | 1 — hand-written, and *not* regenerated by `build_champsim.sh`, so it has to be edited directly. |
| the 8 `replacement/lru.*_repl` sources | 8 |
| the 8 generated `replacement/*_replacement.cc` files | 8 — overwritten from the `.*_repl` sources on every build, so editing them is strictly unnecessary; I did it anyway so that a bare `make` on a fresh checkout also compiles, instead of only working after a `build_champsim.sh`. |
| **total edited** | **27** |

Two files were already correct and were not touched: `replacement/rrip.l2c_repl`
(shipped at 9 parameters — §4.1) and `replacement/irrip.l2c_repl` (new). So the
tree now holds 29 nine-parameter definitions in total.

The anchor used for the edit was the exact string `uint32_t type, uint8_t hit)`.
That is safe because `find_victim` ends `uint32_t type)` with no `hit`, and the
prefetcher hooks spell theirs `uint8_t cache_hit`. A parameter-count audit
afterwards confirmed 28 declarations all at 9, and `rrip.l2c_repl` agreeing.

Every level gets the parameter even though only the L2C uses it. The alternative
— an L2C-only signature — is impossible: they all share one function pointer.
The non-L2C policies simply ignore the argument, which costs nothing.

### 4.3 The 9 call sites, and two ways to get this wrong

| site | function | `hit` | 9th argument |
|---|---|---|---|
| `src/cache.cc:140` | `handle_fill` (LLC bypass path) | 0 → insertion | `MSHR.entry[mshr_index].instruction` |
| `src/cache.cc:527` | `handle_fill` (normal path) | 0 → insertion | `MSHR.entry[mshr_index].instruction` |
| `src/cache.cc:819` | `handle_writeback` | 1 → promotion | `WQ.entry[index].instruction` |
| `src/cache.cc:1080` | `handle_writeback` | 0 → insertion | `WQ.entry[index].instruction` |
| `src/cache.cc:1766` | `handle_read` | 1 → promotion | `RQ.entry[index].instruction` |
| `src/cache.cc:2452` | `handle_read` (prefetch hit) | 1 → promotion | `PQ.entry[index].instruction` |
| `src/ooo_cpu.cc:432` | `read_from_trace` (BTB hit) | 1 | `0` |
| `src/ooo_cpu.cc:456` | `read_from_trace` (BTB hit) | 1 | `0` |
| `src/ooo_cpu.cc:983` | `fill_btb` | 0 | `0` |

**Risk one: pairing the wrong packet's bit with the `type`.** The six cache sites
were edited with a regex keyed on the queue name that already supplied `type`,
appending `.instruction` **of that same queue entry**. The two arguments are
therefore structurally incapable of describing different packets.

**Risk two — and I walked straight into it: missing a call site entirely.** The
BTB is a `CACHE` object too, and `src/ooo_cpu.cc` calls its replacement hook
through a *different* syntax — `(BTB.*BTB.update_replacement_state)(...)` rather
than `(this->*update_replacement_state)(...)`. My first pass grepped
`this->\*update_replacement_state` **in `src/cache.cc` only**, so it found six
sites, reported "exactly 6", and was simply blind to the other three. The build
failed in `src/ooo_cpu.cc` with `error: too few arguments to function`.

Two lessons, both now encoded in `scripts/verify_task2a.py`:

1. **Search for the callee, not for the calling idiom.** The audit now greps the
   whole tree for `update_replacement_state)(` and asserts **9** sites with 9
   arguments each, so a new call site anywhere cannot slip past.
2. **Front-end-compile every translation unit, not the files you changed.** A
   per-file `g++ -fsyntax-only` on `src/cache.cc` and the policy passed happily
   while `src/ooo_cpu.cc` was broken. The audit now compiles all 24 units the
   Makefile builds, for all three L2C policies.

**Why the BTB sites pass `0`.** The parameter means "is this cache line an
instruction line", a question defined by the L2's three-way split of *memory*
traffic. A BTB entry is branch-prediction metadata — a predicted target address,
not a line of fetched instructions — so there is no honest answer other than 0.
It is also behaviourally irrelevant: `lru.btb_repl` ignores the argument entirely
and just calls `lru_update`, so the BTB behaves identically before and after.
Passing `1` on the grounds that the BTB is "frontend" would have been a category
error, conflating *the structure serving the frontend* with *the line holding
instructions*.

### 4.4 Why pass the raw bit rather than a pre-cooked class

`handle_fill` already computes `fill_packet_type` (1/2/3), and it would have been
tempting to pass that instead. I passed the raw `packet.instruction` because:

* it is what the PDF's hint names ("check its `packet.instruction` field");
* `fill_packet_type` is only computed in `handle_fill`, so the three promotion
  sites would have had to compute it themselves — three more chances to diverge;
* classification is *policy*, and policy belongs in the policy file. The
  simulator's job is to hand over the facts (`type`, `isInstruction`); deciding
  that an instruction page walk counts as a translation rather than an
  instruction is a decision I want visible in `irrip.l2c_repl`, where it can be
  argued with and changed, not buried in `cache.cc`.

### 4.5 Why insertion genuinely needs the parameter — the ordering proof

In `handle_fill` the order is: `find_victim` (line 56) → `update_replacement_state`
(line 527) → **`fill_cache()` (line 553)**. `fill_cache()` is what writes
`block[set][way].instruction`. So at the moment the insertion hook runs,
`block[set][way]` still describes **the line being evicted**, not the line
arriving. The incoming line's class is genuinely unavailable without passing it
in — which is precisely why "I-RRIP won't build until you finish this step".

On the promotion path the opposite holds: the line was filled long ago, so
`block[set][way].instruction` is valid and the parameter is redundant there.
(It is still worth having: it lets the policy distinguish *what the line is* from
*who is asking for it*, which §6.3 touches on.)

### 4.6 Is the plumbing change behaviour-neutral?

It should be: every existing policy ignores the new argument. But "should be" is
not a result, so `scripts/run_task2a.sh` re-runs the LRU baseline under the new
signature as one of its three configurations, specifically so the logs can be
diffed against `results/task1/baseline_*.txt`. If they are bit-identical, the
edit is proven non-invasive and the Task 1 numbers stand unchanged. **This is a
verification step, not a redundant run.**

---

## 5. Three classes, not two — and why they match ChampSim's own split

The policy classifies every access as `TRANSL`, `INSTR` or `DATA`, in that test
order (`irrip_class()`):

```c
if (type == LOAD_TRANSLATION || type == PREFETCH_TRANSLATION || type == TRANSLATION_FROM_L1D)
    return IRRIP_TRANSL;
if ((type == LOAD || type == PREFETCH) && isInstruction)
    return IRRIP_INSTR;
return IRRIP_DATA;
```

Two decisions are embedded here.

**Test order.** An instruction page walk arrives with `packet.instruction == 1`.
If translations were not tested first it would be filed as an instruction line,
which it is not — it holds page-table data on the way to an instruction fetch.
ChampSim agrees with that reading: `fill_cache()` sets `translation`, not
`instruction`, on it. Getting this backwards would have quietly mixed two classes
and made the instruction-insertion count in the stats meaningless.

**The split is deliberately identical to `fill_packet_type`** in
`src/cache.cc:60-71` — same three classes, same order, same predicates. This is
not laziness; it is what makes the nine `*_evicting_*` counters usable as
evidence. Because my `INSTR` is bit-for-bit the simulator's "instruction", the
`Data Evicting Instructions` counter is *exactly* "a fill my policy classified as
DATA replaced a line my policy would have classified as INSTR". Had I invented my
own definition — folding translations in, say — that counter would have been
measuring something subtly different from what my policy acts on, and every
conclusion drawn from it would have needed a caveat.

`WRITEBACK` and `RFO` fall through to `DATA`, which is correct: a writeback is a
dirty data line being pushed down, and an RFO is a store. Neither can be an
instruction fetch.

---

## 6. The central argument: insertion, promotion, eviction

This is the deliverable the PDF grades. The claim is stated once and then
defended three times.

> **In RRIP, every input the policy has is funnelled through one number per
> line, the RRPV. Insertion writes it, promotion updates it, eviction reads it.
> So there are exactly three places a type hint can enter the policy. It belongs
> in insertion, because insertion is the only one of the three that makes a
> *prediction about a line the policy knows nothing else about* — and a free
> type hint is worth most exactly where there is no other information.**

### 6.1 INSERTION — changed. This is the whole policy.

**What changed:** instruction lines insert at RRPV 0; data and translation lines
keep SRRIP's own `maxRRPV - 1`. That is the only difference between default
I-RRIP and the supplied RRIP.

**Why insertion is the right lever.**

*The mechanical reason.* A line inserted at RRPV *r* cannot be chosen as a victim
until its set has been aged `maxRRPV - r` times (`find_victim` only returns a way
whose RRPV has reached `maxRRPV`). **The insertion value is literally a
protection budget, denominated in aging rounds.** With `maxRRPV = 3`, an
instruction line at 0 gets 3 rounds; a data line at 2 gets 1. Instruction lines
get **three times the deadline** in which to demonstrate reuse. "Prioritise
instruction lines" has no cleaner expression than that.

*The information-theoretic reason.* At insertion the policy has no access history
for this line whatsoever — that is the defining feature of the moment. Whatever
it writes is a prior. The type bit is the only information available, and it
costs nothing because it is already riding along in the packet. Spending it here
converts a blind guess into an informed one. This is precisely SHiP's idea
(MICRO 2011: choose the insertion RRPV from a signature), with a one-bit
signature that needs no predictor table and no training period.

*The literature reason.* SRRIP's contribution (Jaleel et al., ISCA 2010) *is* the
insertion position; promotion-to-MRU on a hit is inherited from LRU. Every
derivative — BRRIP, DRRIP, SHiP — varies insertion. iTP (ASPLOS 2025) does the
same thing in LRU terms: data entries inserted at the LRU position, instruction
entries at `MRU - N`. The field's answer to "where do you put a type hint in a
reuse-prediction policy" is consistently "in the insertion position".

**Why data keeps SRRIP's value instead of being demoted to `maxRRPV`.**
This is the subtle half of the decision, and it is deliberate.
Pushing data to `maxRRPV` (evict-next) would *also* widen the gap between the
classes, and would do so more aggressively. I did not make that the default
because of what it would mean: I-RRIP's advantage over RRIP would then come from
**penalising data** rather than from **protecting instructions**. Those are not
the same claim. Protection is added where there is a measured reason for it
(§2.2); nothing is taken away where there is not. §2.3 also predicts where
demotion would hurt: trace3, whose dominant miss stream is data (68 % of its
victims are data lines), would pay for a benefit it barely receives.
It is available as knob `IRRIP_INSERT_DATA` and sweep row `ins_d3` measures it.

**Why instructions at 0 and not 1.** Honestly uncertain. RRPV 0 is the value a
line gets when it *hits*, so inserting there says "an unproven instruction line
is as valuable as a proven reused line". iTP deliberately avoids that — it
inserts instructions at `MRU - 4`, not at MRU, reserving the top for lines with a
saturated reuse counter. That is a real argument and I cannot settle it by
reasoning. Sweep row `ins_i1` measures it, and row `ins_i2` (instructions at 2 =
no bias at all) is a control that must reproduce RRIP exactly; if it does not,
the harness is broken and nothing else in the sweep can be trusted.

### 6.2 PROMOTION — not changed, and this is the argument I most expect to be challenged

**What it does:** a hit sets RRPV to 0, for every class. Unchanged from SRRIP.

**Why.** Insertion is a *prediction*; promotion is a *response to evidence*. A
hit is the cache being informed, as a matter of recorded fact, that this line is
being re-referenced. Weakening promotion for data lines means allowing a static
type prior to overrule a measurement — letting a guess beat a fact. That is the
wrong direction for a predictor to resolve a conflict.

There is a second reason specific to *this* cache rather than caches in general.
L2 load hit rates here are 29.7 % / 48.9 % / 28.5 % (§2.1): **L2 hits are
scarce.** When evidence is scarce it should be weighted up, not discounted. A
policy that discards data hits at this hit rate is throwing away a large fraction
of the total information the L2 ever receives.

**The honest counter-argument.** iTP (ASPLOS 2025) *does* weaken data promotion —
data entries promote to `LRUpos + M` rather than to MRU — and reports a 18.9 %
geomean speedup. So the literature does not agree with me. Two things reconcile
this partially: iTP is operating on the STLB, a much smaller structure with very
different reuse distances, and it pairs weakened data promotion with a *frequency
counter* so that repeatedly-hit data still climbs. I have no frequency counter,
so weakening promotion in my design would be strictly lossy rather than graded.

Either way, an argument is not a result. `IRRIP_PROMOTE_DATA` exists, sweep rows
`pro_d1` and `pro_d2` measure it, and `pro_i1` is the reverse control. **If the
sweep says weakened data promotion wins, I will change the default and say so in
the results section.** Recording the prediction here is what makes that honest
rather than retrofitted.

### 6.3 EVICTION — not changed by default, and it is the most interesting of the three

**What it does by default:** scan for the first way at `maxRRPV`; if none, age
the whole set by one and rescan. Identical to the supplied RRIP.

This is the part that most submissions will change, because the PDF lists
eviction and because `block[].instruction` makes it easy (§3). Three reasons not
to:

**(a) It destroys the one property that makes RRIP analysable.** In RRIP the RRPV
*is* the priority — a single totally-ordered number that fully summarises what
the policy believes about a line. If eviction consults the type bit as well, then
type influences the outcome through two independent channels and the RRPV no
longer tells you what the policy will do. Every subsequent question ("why was
this line kept?") needs two answers instead of one. Task 2b then has to layer
set-dueling on top of that, and dueling two policies is only tractable if each
policy is itself simple.

**(b) It double-counts the bias.** An instruction line inserted at 0 already
reaches `maxRRPV` three aging rounds later than a data line inserted at 2. **The
preference is already in the numbers.** Reading the type again at eviction
applies the same bias a second time, through a different mechanism, with no
principled way to say how much total bias has been applied.

**(c) A hard preference disables itself exactly where it is needed.** Consider
"never evict an instruction line while some data line is also at `maxRRPV`". On
trace2, 55.9 % of L2 victims are instruction lines, so sets in which all eight
ways hold instruction lines are common — and in those sets there is no data line
to divert to, so the rule does nothing. The mechanism would be absent from
precisely the hottest sets, and present in the sets under least pressure. That is
backwards.

**But there is a defensible version, and I implemented it as a knob.** xPTP
(ASPLOS 2025) shows how: it diverts the victim away from a protected class *only
while the alternative victim stays within K positions of the true LRU victim* —
a **bounded** diversion rather than an absolute veto. Translated into RRPV terms,
that is `IRRIP_EVICT_SLACK`: consider a non-instruction way as victim if its RRPV
is within `slack` of `maxRRPV`.

* `slack = 0` — the candidate set is exactly the one RRIP would have used; we
  merely prefer a data line among the ways already due for eviction. This
  addresses objection (b) only partially but costs nothing in candidates.
* `slack = 1, 2` — willing to evict a data line that is *not yet due* in order to
  spare an instruction line that is. This is the real xPTP analogue.

The slack is also what keeps objection (c) survivable: at `slack > 0` there are
more eligible data ways, so the mechanism degrades gracefully instead of
switching off. And `IRRIP_EVICT_SLACK < IRRIP_MAX_RRPV` is enforced by a
`static_assert`, because a slack equal to `maxRRPV` would match every way in the
set and turn the policy into "always evict a data line", which is not a bounded
preference at all.

Sweep group F (`ev_s0`, `ev_s1`, `ev_s2`) measures all three. **My prediction:
`ev_s0` moves almost nothing (because of (b) — the bias is already in the RRPVs),
and `ev_s1`/`ev_s2` reduce instruction MPKI while raising data MPKI, i.e. they
trade rather than win.** The `IRRIP EVICT PREF FIRED` counter in the policy's own
stats tells us whether the mechanism ever actually changed a victim, which
distinguishes "tried it and it did nothing" from "tried it and it did not fire".

### 6.4 Translations — not changed by default

Treated as data (`IRRIP_INSERT_TRANSL = maxRRPV - 1`), i.e. unchanged from RRIP.
The case *for* changing it is in §2.4: 6–10.5 % of instruction victims die to a
translation fill, and an instruction page walk stalls the frontend. The case
against making it the default is that it would bundle two separate claims
(instruction lines matter; translation lines matter) into one measurement, and I
would not be able to tell which produced any gain. Sweep group D separates them.

### 6.5 Writeback hits — deliberately left matching the supplied RRIP

`lru.l2c_repl` skips the replacement update on a writeback hit, with the comment
"writeback hit does not update LRU state". `rrip.l2c_repl` does **not** skip it:
it promotes on any hit including a writeback. These are genuinely different
positions, and a writeback hit is arguably not a demand reference at all — it is
the L1D pushing a dirty line down.

I kept **RRIP's** behaviour (`IRRIP_WB_PROMOTES = 1`) even though I think LRU's
is more defensible, for one reason: it makes `I-RRIP − RRIP` isolate
instruction-consciousness and nothing else. If I had also changed writeback
handling, any difference between the two would have mixed two unrelated edits and
the deliverable's central comparison would have been uninterpretable. Sweep row
`wb0` measures it separately, which is the right place for it.

This is a general principle worth stating explicitly, because it drove several
choices above: **the default configuration is chosen to make the comparison
clean, not to be the best configuration.** The best configuration is what the
sweep is for.

---

## 7. Storage — exact bit-level accounting

L2C geometry: `L2C_SET 1024` × `L2C_WAY 8` = **8192 lines** (`inc/cache.h:93-94`).

### 7.1 What the policy stores

| structure | per line | total | note |
|---|---|---|---|
| RRPV, `maxRRPV = 1` | 1 bit | 8 192 bits = **1 024 B** | 1-bit RRPV |
| RRPV, `maxRRPV = 3` **(default)** | 2 bits | 16 384 bits = **2 048 B** | smallest field holding 0..3 |
| RRPV, `maxRRPV = 7` | 3 bits | 24 576 bits = **3 072 B** | |
| line-type bit | 1 bit | 8 192 bits = **1 024 B** | **only if `IRRIP_EVICT_PREFER_DATA = 1`** |

So the shipped configuration costs **2 048 B = 2 KiB**, and the policy prints
this itself at the end of every run (`IRRIP STORAGE ... total_bytes`) so the
deliverable is read off the run rather than recomputed by hand.

The `uint8_t l2_irrip_rrpv[1024][8]` array in the source is 8 KiB of simulator
memory; that is a modelling convenience, not the hardware cost. The hardware cost
is the bit field above.

### 7.2 Against what it replaces

The LRU it replaces needs a recency rank per line: `ceil(log2(8)) = 3` bits,
8 192 lines, **3 072 B = 3 KiB**.

| policy | storage | vs LRU |
|---|---|---|
| LRU (baseline) | 3 072 B | — |
| RRIP / I-RRIP, 2-bit RRPV | **2 048 B** | **−1 024 B (−33 %)** |
| I-RRIP with eviction preference on | 3 072 B | ±0 |

**I-RRIP in its default configuration is a third cheaper than the LRU it
replaces.** That is a RRIP property rather than an I-RRIP one, but it is worth
reporting because it frames the result correctly.

### 7.3 The cost of instruction-consciousness itself

| | extra storage over plain RRIP |
|---|---|
| insertion-based (the default) | **0 bits** |
| + eviction preference | 1 024 B |

Zero, in the default configuration. Insertion and promotion get the class from
`packet.instruction`, which is a field of a packet already in flight through the
MSHR — not state the cache has to keep. Only the eviction preference needs the
class of a *resident* line, which means a stored bit per line. (ChampSim happens
to maintain `BLOCK::instruction` already, so the simulator shows no cost; a real
implementation would pay the 1 024 B, and §7.1 charges it honestly.)

This is the strongest practical argument for the insertion-only design: it is the
only one of the three options that is free.

---

## 8. The knobs

Instruction 8 asked for the design to be parameterised so configurations can be
tried quickly. Every tunable lives in one block at the top of
`replacement/irrip.l2c_repl` and nowhere else, wrapped in `#ifndef` so it can
also be forced with `-D`. `scripts/sweep_task2a.py` rewrites one `#define` line
in a throwaway copy and rebuilds; it never touches the logic.

| knob | default | range | what it controls | why it is a knob |
|---|---|---|---|---|
| `IRRIP_MAX_RRPV` | 1 | 1..7 | top of the RRPV range; sets the width of the counter and the length of every deadline | the one knob you asked about by name. 1/3/7 are the storage-meaningful points (1/2/3-bit). **0 is excluded by construction**: with a maximum of 0, insertion and evict-now are the same value, so no priority can be expressed at all and the policy degenerates to "always replace way 0" |
| `IRRIP_INSERT_INSTR` | 0 | 0..max | instruction-line insertion position | §6.1 — the entire mechanism |
| `IRRIP_INSERT_DATA` | max | 0..max | data-line insertion position | §6.1 — tests protect-instructions vs demote-data |
| `IRRIP_INSERT_TRANSL` | max | 0..max | translation-line insertion position | §2.4, §6.4 |
| `IRRIP_PROMOTE_INSTR` | 0 | 0..max | RRPV written when an instruction line hits | §6.2 reverse control |
| `IRRIP_PROMOTE_DATA` | max | 0..max | RRPV written when a data line hits; >0 = weakened promotion | §6.2 — the one place the literature disagrees with me |
| `IRRIP_PROMOTE_TRANSL` | 0 | 0..max | same for translations | completeness |
| `IRRIP_EVICT_PREFER_DATA` | 0 | 0/1 | whether the victim scan reads the type bit at all | §6.3 |
| `IRRIP_EVICT_SLACK` | 0 | 0..max−1 | how far below `maxRRPV` a data way may be and still be diverted to | §6.3 — xPTP's bounded diversion; `static_assert`-ed below `maxRRPV` |
| `IRRIP_WB_PROMOTES` | 1 | 0/1 | does a writeback hit promote? | §6.5 |

Two guard rails, both deliberate:

* **Every knob is range-checked by `static_assert`.** A nonsense sweep value
  fails the build instead of quietly producing a number that looks like a
  result. All 17 sweep variants were verified to compile.
* **The policy prints its own configuration into every run's log**, and
  `sweep_task2a.py` reads it back and *refuses to tabulate* a run whose compiled
  configuration differs from the one requested. A stale binary or a silently
  failed rebuild therefore cannot be reported as a finding. This is the single
  most valuable thing in the sweep harness: in Task 1 the only errors that
  survived review were ones where a number was real but was not measuring what I
  said it was.

### 8.1 The sweep plan — 26 variants (17 in Stage 1, 9 in Stage 2)

`python3 scripts/sweep_task2a.py --list` prints the live list. Grouped:

| group | rows | question it answers |
|---|---|---|
| — | `base` | the shipped defaults |
| A | `max1`, `max7`, `max7mid` | how wide should the RRPV be? is a longer deadline better? |
| B | `ins_i1`, `ins_i2` | where exactly should an instruction line go in? (`ins_i2` is the RRIP control) |
| C | `ins_d3`, `ins_d1` | should data be demoted as well as instructions promoted? |
| D | `tr_instr`, `tr_evict` | are address translations frontend-critical? |
| E | `pro_d1`, `pro_d2`, `pro_i1` | should promotion be type-aware at all? |
| F | `ev_s0`, `ev_s1`, `ev_s2` | should eviction read the type bit, and with how much slack? |
| G | `wb0` | does a writeback hit deserve a promotion? |

One knob at a time around a fixed centre, so every row is attributable to a
single change. A full-factorial sweep over 10 knobs is not an option
(thousands of 25M+25M runs), and it would not be more informative: interactions
only matter once the main effects are known, and the main effects are what these
17 rows give. If two knobs both help individually, the obvious follow-up is the
combination — that is a second, much smaller sweep, run after this one.

---

## 9. Predictions, recorded before the runs

Writing these down now is the point. In Task 1 three arguments of mine that
sounded convincing were refuted by counters that were already being printed; the
lesson was to commit to a falsifiable statement first.

### 9.1 What can and cannot be measured here

Task 1 established, by running identical source under two toolchains, that
**every cache and prefetcher counter in this simulator is bit-identical** while
cycle counts drift by **0.078 %** (undefined behaviour at `src/cache.cc:1885`
producing different garbage under different codegen). So:

* MPKI, the nine eviction counters, and the policy's own counters are **exact**.
  Differences of any size in them are real.
* **IPC differences below roughly 0.1 % are not meaningful.**

Unlike Task 1, though, IPC here might actually move. `L2C AVERAGE MISS LATENCY`
is **140.3 cycles** on trace1, and trace1 runs 25 M instructions in 107.6 M
cycles. Removing 5 % of its 258 K instruction misses would be ~12.9 K misses ×
140 cycles ≈ 1.8 M cycles, or 1.7 % of total cycles *if fully exposed*. Memory-level
parallelism means much less than that will surface, but the order of magnitude
is ~1 %, not ~0.1 %. **So for Task 2a, IPC is worth taking seriously — while
still not being the target the PDF names.**

### 9.2 Specific, checkable predictions

1. **I-RRIP beats RRIP on instruction MPKI on all three traces**, since the
   default differs from RRIP only by giving instruction lines a longer deadline,
   and §2.2 shows a non-empty set of conflicts for it to win.
2. **The benefit ranks trace1 > trace3 > trace2 relative to each trace's own
   instruction MPKI** (§2.3). If trace2 gains most, my capacity-vs-conflict
   reading is wrong and the right explanation is something else.
3. **Data MPKI rises somewhere**, most likely trace2 and/or trace3. There is no
   free lunch: instruction lines held longer occupy ways data would have used.
   If data MPKI falls everywhere, something other than the intended mechanism is
   at work and I should go and find out what.
4. **RRIP alone beats LRU on L2C load MPKI** on at least trace1 and trace2, since
   both have low hit rates (the thrashing regime SRRIP was designed for).
5. **`ins_i2` reproduces RRIP to the last digit.** If not, the harness is broken.
6. **`ev_s0` changes almost nothing** (§6.3(b)); `ev_s1`/`ev_s2` trade instruction
   MPKI for data MPKI rather than winning outright.
7. **`max7` does not beat `max3` by much, if at all.** Jaleel et al. found 2 bits
   sufficient; a longer deadline also means a longer aging loop and a staler set.
   If `max7` wins clearly, that is a genuinely interesting finding and worth a
   paragraph of its own.
8. **`pro_d1`/`pro_d2` lose**, per §6.2. This is the prediction I hold with the
   least confidence, because iTP disagrees.

Any of 1–8 coming out false is a result, not a failure — and is more useful to
write up than a design where everything went as expected.

---

## 10. Literature this design leans on

Read for the design, not cited decoratively:

* **Jaleel, Theobald, Steely, Emer — "High Performance Cache Replacement Using
  Re-Reference Interval Prediction (RRIP)", ISCA 2010.** The source of SRRIP and
  of the insertion-is-the-lever argument, and of the finding that a 2-bit RRPV is
  enough. `replacement/rrip.l2c_repl` is an implementation of its SRRIP.
* **Wu, Jaleel, Hasenplaugh, Martonosi, Steely, Emer — "SHiP: Signature-based Hit
  Predictor for High Performance Caching", MICRO 2011.** Chooses the insertion
  RRPV from a signature. I-RRIP is the degenerate case: a one-bit signature that
  arrives free and needs no predictor table. This is the cleanest way to describe
  what the policy is.
* **Vavouliotis et al. — "Instruction-Aware Cooperative TLB and Cache Replacement
  Policies", ASPLOS 2025.** The closest current work. Two things taken from it:
  (i) iTP puts the instruction bias in *insertion and promotion* and leaves
  eviction alone, and inserts instructions at `MRU − N` rather than at MRU, which
  is the argument behind sweep row `ins_i1`; (ii) xPTP, when it *does* touch
  eviction, uses a **bounded** diversion gated on a slack parameter K rather than
  an absolute veto — which is exactly `IRRIP_EVICT_SLACK`. It also confirms that
  prioritising one class provokes misses in the other, and that the accepted fix
  is phase-adaptive switching — which is Task 2b.
* **Qureshi, Jaleel, Patt, Steely, Emer — "Adaptive Insertion Policies for High
  Performance Caching", ISCA 2007.** DIP and set-dueling. Not used in 2a; it is
  the mechanism Task 2b asks for.
* **Ferdman et al. — "Clearing the Clouds", ASPLOS 2012** and **Kanev et al. —
  "Profiling a Warehouse-Scale Computer", ISCA 2015.** The empirical basis for
  the PDF's opening claim that server workloads are frontend-bound with
  instruction footprints beyond the L1I. §2.1 is the local version of their
  finding.

One honest note: a 2025 paper titled *"Second-level Caches: Not for Instructions"*
exists and, from its title, appears to argue against the premise of this task.
**I have not read it**, so I am listing it as something to look at rather than as
support or opposition. If it is right, the interesting question is whether these
three traces are the regime it is talking about — and §2.1 says at least trace1
and trace2 clearly depend on L2 instruction hits.

---

## 11. Known limitations, and the hook for Task 2b

1. **Blind prioritisation has no phase awareness.** The policy applies the same
   bias at every instant. The PDF's Task 2b opens with exactly this objection,
   and iTP/xPTP reach the same conclusion independently. §2.3 names trace2 as the
   likely casualty. This is a limitation by design, not an oversight: 2a is the
   static policy whose weaknesses 2b is supposed to measure and fix.
2. **The design is built so 2b can be layered on cleanly.** Because the entire
   bias lives in two integers consulted at insertion, "switch to normal RRIP"
   means nothing more than using `IRRIP_INSERT_DATA` for instruction lines too.
   A set-dueling controller therefore needs no second copy of the policy and no
   change to the victim scan — which is the practical payoff of refusing to spread
   the bias across all three parts (§6.3(a)).
3. **Three traces is a small sample.** Per-trace results are reported alongside
   every aggregate for exactly this reason, and the geometric mean is used for
   speedup so one trace cannot dominate by having a large absolute IPC.
4. **The instruction-evicts-instruction conflict is untouched** and is the
   majority of trace2's problem (64.6 %). Nothing in Task 2a's remit addresses
   it; it would need either more capacity or a reuse predictor *within* the
   instruction class (SHiP-style, with a real signature).
5. **Interactions between knobs are not swept** (§8.1). Main effects only.

---

## 12. Decision summary

| part of the policy | changed? | one-line reason |
|---|---|---|
| **insertion** | **yes** — instruction lines at RRPV 0 | the only hook that makes a prediction with no other information, so a free type hint is worth most there; and it is the only option that costs 0 extra bits |
| **promotion** | no | a hit is evidence, not a guess; overruling it with a type prior lets a guess beat a fact, and L2 hits are too scarce here to discard |
| **eviction** | no | the RRPV must remain the complete summary of priority; the bias is already in the numbers, and a hard preference switches itself off in the most pressured sets |
| **data lines** | no — keep SRRIP's insertion | protect instructions rather than penalise data, so the gain is attributable |
| **translations** | no — treated as data | keeps the instruction claim separate from the translation claim |
| **writeback hits** | no — keep RRIP's behaviour | so that `I-RRIP − RRIP` isolates instruction-consciousness alone |

Every "no" in that table is a knob, and every knob is a row in the sweep. The
defaults are chosen to make the central comparison clean; the sweep is what
chooses the best configuration, and §9 is what makes that choice honest.

---

## 13. Three ways the harness lied, and what each one cost

The first full run of Task 2a produced a complete set of results that looked
entirely normal — 9 main runs, 51 sweep runs, tables, five plots — and **two
thirds of it was measuring the wrong thing.** None of the three failures
produced an error message. All three are recorded here because the defences
against them are now the most valuable part of the harness, and because the
general lesson holds well beyond this assignment: *a number being real is not
the same as a number measuring what you said it measures.*

### 13.1 A stale binary from a different implementation

`results/task2a/irrip_*.txt` was produced by
`bin/...-1core-irrip` dated **13:03**, while `replacement/irrip.l2c_repl` was
written at **14:43**. `strings` on that binary showed `=== I-RRIP Stats ===`,
`irrip_instr_victims`, `irrip_data_inserts`, `irrip_data_hits` — none of which
appear anywhere in the current policy, which prints `L2C I-RRIP config ...`
instead. It was an earlier, unrelated I-RRIP whose source is no longer in the
tree.

**Why it got through:** `run_task2a.sh` checked `[ -x "$BIN" ]` and nothing
else. A file existed at the expected path, so it ran it. The sweep had an
identity check from the start — it reads each run's configuration back out of
its own log — but the main runner, the one that produces the headline
deliverable, did not. The guard was on the careful path and missing from the
important one.

**Defences added:** the binary must be newer than every build input
(`find <policy> src inc -newer`), and `parse_task2a.py` now reconstructs the
expected `L2C I-RRIP config` line from the `#define`s on disk and **refuses to
parse an `irrip_*` log that does not contain exactly that line**. The second
check is the stronger one: an mtime can be fooled by `touch`, but that string is
emitted by the binary itself at run time, so it cannot be forged by anything
short of editing the source.

### 13.2 The sweep was built by clang on macOS, not GCC 7

All 17 sweep binaries were `Mach-O 64-bit arm64`; the container builds are
`ELF 64-bit ... statically linked`. The sweep had been launched on the host
rather than inside the GCC 7 container.

This is more than a policy violation, and the reason is worth understanding.
`src/cache.cc:1885` reads `MSHR.entry[mshr_index]` **inside a branch guarded by
`mshr_index == -1`** — so it is unconditionally out of bounds every time it is
reached. Different compilers put different garbage there, and for `IS_STLB`
that garbage feeds `pf_lower_level`, which perturbs the translation request
stream and hence the simulated L2.

Quantified with the `ins_i2` control — instruction insertion at 2 means no bias
at all, so it is algorithmically identical to the supplied RRIP — clang against
GCC 7:

| trace | L2 instr MPKI, GCC 7 `rrip` | clang `ins_i2` | divergence |
|---|---|---|---|
| trace1 | 10.5618 | 10.5810 | 0.18 % |
| trace2 | 17.7813 | 18.4604 | **3.82 %** |
| trace3 |  1.1970 |  1.1916 | 0.45 % |

**3.82 % on trace2 for identical algorithms** is the same order as the knob
effects the sweep exists to resolve, so the sweep could not have distinguished a
knob from a compiler artifact. All 51 runs were discarded.

Note this also **narrows a Task 1 claim.** Task 1 established that every cache
counter was bit-identical between g++ 11 `-O0` and GCC 7 `-O3`, with only cycles
moving (0.078 %), and concluded the counters were toolchain-independent. That
conclusion holds for the two toolchains it tested and **does not extend to
clang**. The honest statement is "deterministic across the GCC versions tested",
not "toolchain-independent".

**Defence added:** `sweep_task2a.py` refuses to run unless `sys.platform` is
Linux and `g++ --version` reports 7.x; `run_task2a.sh` refuses any binary that
`file` does not report as ELF.

The 51 clang logs were discarded apart from the three `ins_i2` runs that the
table above is computed from; those are kept in
`results/_quarantine_not_gcc7/sweep_clang/` so the divergence remains
reproducible against `results/task2a/rrip_*.txt`.

### 13.3 The policy's own statistics were never printed

`l2c_replacement_final_stats()` — which carries the per-class insert/promote
counts, the evict-preference counter and the bit-level storage accounting the
PDF asks for — produced no output in any run, including the ones built from the
correct source.

ChampSim calls it in exactly one place, `src/main.cc:1754`, and that call sits
inside `if (NUM_CPUS > 1)`. **Every run this assignment requires is single-core,
so the hook never fired.** Its prefetcher sibling,
`l1d_prefetcher_final_stats()`, is called from *both* paths — line 1752 in the
multi-core block and line 1815 in the single-core loop — which is why Task 1's
SPP counters printed normally and nothing looked wrong. The replacement hook was
simply missed in the single-core loop.

**Why it got through:** I built a deliverable on a hook without checking that
the hook was reachable. The design document even claimed the storage figure was
"read off the run rather than recomputed by hand" — which was false for every
run.

**Fix:** `ooo_cpu[i].L2C.l2c_replacement_final_stats()` added to the
single-core loop in `src/main.cc`, next to the prefetcher calls it belongs
with. This also fixes the hook for the supplied `rrip` policy and for Tasks 2b
and 3.

### 13.4 What the three have in common

Each failure was a case of **trusting a name instead of checking a fact**: the
binary was named `irrip` so it was assumed to be I-RRIP; `g++` was on the PATH
so it was assumed to be GCC 7; the function was named `final_stats` so it was
assumed to be called. The three defences all work the same way — make the
artifact prove its own identity:

| assumption | how it is now checked |
|---|---|
| this binary is the current policy | the binary prints its configuration, and the parser reconstructs that line from the source and demands an exact match |
| this was built with GCC 7 | `file` must say ELF; `g++ --version` must say 7.x; the sweep aborts otherwise |
| this hook runs | the hook's output is now a parsed, asserted field rather than something assumed to be in the log |

The one result that **survived** all of this is worth noting, because it
survived for the same reason: §4.6 predicted the signature change would be
behaviour-neutral and specified a test — re-run the LRU baseline and diff it
against Task 1's. That diff came back **bit-identical on all three traces**.
A claim with a test attached was the only claim that did not need revisiting.

---

## 14. Results, and the three arguments the measurement destroyed

All numbers: GCC 7.5.0 at `-O3`, 25M warmup + 25M simulation, single core, no L1D
prefetcher. Baseline is no prefetcher + stock LRU at L2. 26 sweep variants × 3
traces = 78 runs, plus 9 headline runs.

The shipped configuration is the sweep's `max1_prod1` row, and
`scripts/verify_task2a.py` asserts that the `#define`s on disk reproduce that
row's configuration string exactly — so the headline numbers come from a
configuration that was actually measured, not hand-assembled afterwards. The
final `irrip` runs reproduce `max1_prod1`'s logs **line for line**.

### 14.1 Headline

| | mean instr MPKI | mean data MPKI | mean L2C load MPKI | geomean speedup | storage |
|---|---|---|---|---|---|
| LRU (baseline) | 10.1050 | 6.2305 | 16.3356 | 1.0000 | 3 072 B |
| RRIP (supplied) | 9.8467 | 5.9613 | 15.8080 | 1.0004 | 2 048 B |
| **I-RRIP (ours)** | **6.2219** | 8.5371 | **14.7590** | **1.0138** | **1 024 B** |

Against LRU: instruction MPKI **−38.4 %**, total L2 load MPKI **−9.7 %**,
speedup **1.0138**, at **one third of LRU's storage**. Against RRIP — the
comparison that isolates instruction-consciousness rather than RRIP — instruction
MPKI **−36.8 %**.

Per trace:

| trace | instr MPKI | data MPKI | L2C MPKI | speedup |
|---|---|---|---|---|
| trace1 | 10.338 → **9.238** (−10.6 %) | 7.358 → 9.996 (+35.9 %) | 17.696 → 19.234 (+8.7 %) | 0.9967 |
| trace2 | 18.853 → **8.715** (−53.8 %) | 8.504 → 12.344 (+45.2 %) | 27.357 → 21.058 (−23.0 %) | **1.0384** |
| trace3 | 1.124 → **0.713** (−36.5 %) | 2.830 → 3.271 (+15.6 %) | 3.954 → 3.985 (+0.8 %) | 1.0068 |

Instruction MPKI falls on every trace. The cost is a data-MPKI rise on every
trace, which on trace1 is large enough to make total L2 MPKI worse and IPC
0.33 % lower. §14.5 defends that choice; §14.8 is why Task 2b exists.

The mechanism is visible in ChampSim's own eviction counters — instruction lines
that got thrown out, against LRU:

| trace | instruction victims | by a data fill (`d→i`) | by another instruction (`i→i`) |
|---|---|---|---|
| trace1 | 257 967 → 200 049 (−22.5 %) | 120 225 → 103 643 (−13.8 %) | 112 800 → 77 919 (−30.9 %) |
| trace2 | 462 640 → 189 603 (**−59.0 %**) | 136 147 → 70 729 (−48.0 %) | 298 635 → 103 316 (−65.4 %) |
| trace3 | 30 733 → 16 064 (−47.7 %) | 19 415 → 8 580 (−55.8 %) | 8 097 → 5 650 (−30.2 %) |

### 14.2 The number that explains everything: reuse density

The policy's own counters give hits per fill, by class:

| trace | instruction promotes / inserts | data promotes / inserts | ratio |
|---|---|---|---|
| trace1 | **0.54** | 0.13 | 4.2× |
| trace2 | **3.06** | 0.19 | 16.1× |
| trace3 | **1.12** | 0.12 | 9.3× |

**A data line brought into this L2 is re-referenced about 0.15 times before it
leaves. An instruction line is re-referenced 0.5 to 3 times.** Instruction lines
are 4–16× more likely to be reused per fill than data lines.

That single table is the whole defence of the design, and it reframes it. The
policy is not expressing a *preference* for instructions over data — a bias
imposed from outside. It is **reading the reuse statistics of the two streams
correctly.** A line class that is hit 0.15 times per fill genuinely does not
deserve cache residency; one hit three times per fill genuinely does. Every knob
the sweep settled on — data inserted at the eviction edge, data promotion
weakened to evict-next, a 1-bit RRPV — follows from that asymmetry, not from the
word "instruction-conscious".

It also explains the per-trace split better than anything in §2. trace2's
instruction stream has 3.06 hits per fill and gains 53.8 %; trace1's has 0.54 and
gains 10.6 % while paying a net MPKI loss. **Protection pays exactly in
proportion to the reuse density of what is being protected.**

### 14.3 Three of my eight predictions were refuted

§9.2 recorded eight falsifiable predictions before any of this ran. Five held.
The three that failed all failed in the same direction — I systematically
under-estimated how hard these traces want instructions prioritised.

**Prediction 2 — REFUTED.** I predicted the benefit would rank
trace1 > trace3 > trace2, and said explicitly: "If trace2 gains most, my
capacity-vs-conflict reading is wrong." trace2 gained most by a wide margin.

The error: §2.3 reasoned from the **baseline** eviction mix, noting that 64.6 %
of trace2's instruction victims were killed by *other instruction lines*, and
concluded that was a capacity problem no type preference could fix. But the
eviction mix is an **output of the policy, not an input.** Protecting
instructions at insertion slows the rate at which instruction lines churn
against each other, so `i→i` fell 65.4 % on trace2 — the conflict I had declared
unaddressable fell further than the one I was aiming at. The right predictor was
never the conflict mix; it was reuse density (§14.2), which I could have measured
from the baseline just as easily and did not think to.

**Prediction 6 — REFUTED.** I predicted the eviction preference at slack 0 would
"change almost nothing", because "the bias is already in the RRPVs, so reading
the type again double-counts". It moved mean instruction MPKI from 9.08 to 8.37
and was the best *regression-free* variant in the sweep.

Why the argument was wrong: **insertion delays the decision; it does not inform
it.** Once a set is full of instruction lines all sitting at RRPV 0, the aging
pass drives them to the eviction edge *together*, and at the moment the victim is
chosen every candidate looks identical — the type information insertion used has
been consumed. An eviction-side check restores it precisely when insertion's
protection has expired. The two mechanisms are not redundant; they act at
different moments. This is a real correction to §6.3, and the only reason the
shipped configuration still leaves eviction alone is §14.5, not this argument.

**Prediction 8 — REFUTED.** I predicted weakening data promotion would lose. It
wins, and it is in the shipped configuration. iTP (ASPLOS'25) does exactly this
and was right.

My argument was that a hit is *evidence* and must not be overruled by a static
type prior — "letting a guess beat a fact". §14.2 shows what was wrong with it:
at 0.13 hits per fill, an L2 data hit is evidence of "referenced twice", not of
"hot". I treated a binary event as though it carried more information than it
does. The hit is still honoured — the line survives that eviction instead of
being the victim — it simply is not promised the top of the set.

The pattern across all three: **the reasoning about mechanism was sound; the
calibration was wrong,** and in every case the thing that would have corrected me
was a counter that was already being printed.

### 14.4 There is one axis, not ten knobs

Across all 26 variants, instruction MPKI and data MPKI are near-perfectly
anti-correlated: r = **−0.96 / −0.94 / −0.89** on the three traces. Every knob —
RRPV width, both insertion points, both promotion strengths, the eviction
preference, writeback handling — moves the *same* single quantity, at a roughly
constant exchange rate of **~0.5 data misses gained per instruction miss saved**
(range 0.37–0.61 across variants).

Two consequences:

1. **Why trading is almost always profitable here.** Instruction misses are 62 %
   of the baseline L2 load miss stream, so swapping one instruction miss for 0.5
   data misses reduces total misses as long as the exchange rate stays below
   ~1.6. It does, everywhere, on the aggregate.
2. **A failed measurement, reported as failed.** I tried to fit
   `speedup ≈ a·(−Δinstr) + b·(−Δdata)` over all 26 variants to put a number on
   how much more an instruction miss costs. It returned **negative coefficients**
   on trace1 and trace3 — physically impossible, since removing misses cannot
   reduce IPC. The cause is exactly the collinearity above: with r ≈ −0.95 the
   two-variable system is ill-conditioned and the coefficients are not
   identifiable. **I am discarding that fit rather than reporting it.**

   The direction survives without it, from a single clean comparison:
   `max1_prod1` has *worse* total L2C MPKI than `max7_ev4` (14.759 vs 14.247) and
   *better* speedup (1.0138 vs 1.0092). The only difference is composition — less
   instruction, more data. So an L2 instruction miss costs more IPC than an L2
   data miss, which is what the assignment's own premise predicts: an
   instruction miss stalls the frontend, leaving nothing to overlap it with,
   whereas a data miss is absorbed by out-of-order execution and
   memory-level parallelism. The magnitude is not identifiable from this data and
   is not quoted.

### 14.5 Why this configuration, and not the regression-free one

Only 7 of 26 variants regress no single trace. The best of them,
`ev0_wb0_trev` (the three clean Stage-1 winners combined), is a genuine
alternative:

| | instr MPKI | L2C MPKI | geomean speedup | storage | trace1 |
|---|---|---|---|---|---|
| `max1_prod1` (shipped) | **6.222** | 14.759 | **1.0138** | **1 024 B** | L2C +8.7 %, IPC −0.33 % |
| `ev0_wb0_trev` | 7.776 | **14.384** | 1.0069 | 3 072 B | clean |

`max1_prod1` was chosen because:

1. **It wins the objective the assignment names.** "Your goal should be to reduce
   L2 load instruction MPKI" — 6.222 against 7.776, a further 20 % reduction.
2. **It wins on IPC by the largest margin in the sweep** (1.0138; next best
   1.0099).
3. **It is the cheapest configuration tested** — 1 024 B, one third of the LRU it
   replaces and half of plain RRIP.
4. **It leaves eviction untouched**, so the RRPV remains the complete summary of
   a line's priority. That is what lets Task 2b duel two policies that differ in
   a single number, with no second victim-selection path to reason about.
5. **Its weakness is precisely what Task 2b exists to fix**, so it hands 2b a
   measured target rather than an assumption.

`ev0_wb0_trev` is reported here rather than discarded, because the honest
statement is that this is a **Pareto frontier, not a single optimum**: a reader
who weights worst-case per-workload behaviour above the stated objective should
prefer it, and the sweep data for it is in `results/task2a_sweep/`.

One finding worth recording from that row: the three clean knobs **compose**.
Individually they cut mean instruction MPKI by 0.717, 0.541 and 0.217 (sum
1.475); together they cut it by 1.308, or 89 % of additive. Sub-additive but
genuinely cumulative — and the combination reaches instruction MPKI 7.78 *without
regressing any trace*, where every single-knob attempt to get that low regresses
trace1. **Three gentle pushes go further than one hard shove.**

### 14.6 Storage — exact accounting

8 192 lines (`L2C_SET 1024` × `L2C_WAY 8`), 1 bit of RRPV each:

| | bits/line | total | vs LRU |
|---|---|---|---|
| LRU (replaced) | 3 (`ceil(log2(8))` recency rank) | 24 576 b = **3 072 B** | — |
| RRIP (supplied) | 2 | 16 384 b = 2 048 B | −33 % |
| **I-RRIP (shipped)** | **1** | 8 192 b = **1 024 B** | **−67 %** |

The policy prints this itself at the end of every run, so the figure is read off
the run rather than recomputed by hand:

```
L2C IRRIP STORAGE rrpv_bits_per_line 1 rrpv_bits 8192 type_bits 0 total_bits 8192 total_bytes 1024
```

**The cost of instruction-consciousness itself is 0 bits.** Insertion and
promotion take the line's class from `packet.instruction`, a field of a packet
already in flight through the MSHR — not state the cache keeps. Only the
eviction preference would need the class of a *resident* line, i.e. a stored bit
per line, and the shipped configuration does not use it. So I-RRIP is a third
cheaper than the LRU it replaces *and* adds nothing to RRIP.

### 14.7 The verdict on insertion, promotion and eviction

The deliverable asks for the rationale on modifying **or not modifying** each of
the three, and for a defence of the choice. Final answers, with the
pre-measurement position shown so the change is visible:

| | argued before | shipped | why |
|---|---|---|---|
| **Insertion** | change — instructions to RRPV 0, data left at SRRIP's max−1 | **changed, harder**: instructions 0, data **at** the edge | Insertion is the only hook that predicts about a line with no history, so a free type hint is worth most there; it is also the only option costing 0 extra bits. I left data alone so the gain would be attributable to *protecting instructions* rather than *penalising data* — the cleaner claim and the weaker policy. §14.2 shows why: at 0.13 hits per fill, data does not deserve a protection budget at all. |
| **Promotion** | do not change — a hit is evidence, not a guess | **changed**: data hits promote to the edge, not to 0 | Refuted (§14.3). An L2 data hit at 0.13 hits/fill means "referenced twice", not "hot"; I credited a binary event with more information than it carries. The hit is still honoured by the line surviving that eviction. |
| **Eviction** | do not change — the RRPV must remain the complete priority | **not changed** | The *conclusion* stands but the *argument* for it was refuted (§14.3): the preference does help. It stays off because the shipped configuration beats it on the stated objective, on IPC and on storage, and because keeping eviction a pure function of the RRPV is what keeps Task 2b's set-dueling tractable. |

The defence of "why this is best" rests on four claims, each measured rather than
argued: it reduces instruction MPKI more than any alternative tested (−38.4 % vs
LRU); it has the highest IPC of all 26 variants (1.0138); it is the cheapest
(1 024 B, −67 % against LRU); and its one weakness is identified, quantified, and
assigned to the task designed to fix it.

### 14.8 Limitations, and the handover to Task 2b

1. **trace1 regresses.** Total L2 MPKI +8.7 %, IPC −0.33 %. The cause is measured,
   not guessed: trace1's instruction stream has 0.54 hits per fill against
   trace2's 3.06, so protection there costs data residency and collects little.
   This is exactly the PDF's framing for 2b — "blindly prioritizing instruction
   lines over data lines may result in an increase in data misses for certain
   phases of a workload" — and we now hand 2b a number instead of a worry.
2. **The right signal for 2b is already identified.** §14.2's reuse density is
   measurable online from two counters per class (fills and hits) — cheaper than
   the accesses-and-misses ratio the PDF suggests, and directly causal rather
   than correlational. Worth testing against the suggested formula.
3. **The bias lives in two integers consulted at insertion plus one at
   promotion**, and eviction is untouched, so "switch to normal RRIP" is a change
   of three constants. A set-dueling controller needs no second policy
   implementation and no second victim path.
4. **Knob interactions are only partly explored.** Stage 2 combined the clean
   winners and bracketed the far end (`max7_ev6` is worse than `max7_ev4` on
   MPKI), but the space is 10-dimensional and 26 points is a thin sample of it.
5. **Three traces.** Per-trace results are reported beside every aggregate for
   exactly this reason, and the geometric mean is used for speedup so no single
   trace dominates through a large absolute IPC.
