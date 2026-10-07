# Task 2a — I-RRIP explained, line by line

`docs/TASK2A_DESIGN_DECISIONS.md` argues *why*. This file explains *what the code
does*, in the order you should read it. If you work through the five chunks at
the end you will be able to explain any line of `replacement/irrip.l2c_repl`
without looking at it.

---

## 1. RRIP from first principles

Forget instructions for a moment. A replacement policy answers one question:
**when a set is full and a new line arrives, which of the eight resident lines
should go?**

LRU answers "the one referenced longest ago". That works when re-reference
distances are shorter than the cache's reach. It fails badly when they are not:
if a program streams through more data than fits, every line is evicted before it
is ever reused, and LRU still dutifully gives each new line the best position in
the set on the way through. The cache does maximum work for zero hits. This is
*thrashing*, and it is the regime this L2 is in — load hit rates of 29.7 %,
48.9 %, 28.5 % on the three traces.

RRIP's idea: instead of tracking *recency* (when was this used?), predict
*re-reference interval* (how long until this is used again?). Each line gets a
small counter, the **RRPV** — Re-Reference Prediction Value.

```
RRPV = 0           "I expect this to be used again very soon"      keep it
RRPV = maxRRPV     "I expect this never to be used again"          evict it
```

Three rules make a policy out of that:

| event | SRRIP's rule | in words |
|---|---|---|
| **insertion** (a line is filled) | RRPV = `maxRRPV - 1` | "probably won't be reused — but I'll give it one chance" |
| **promotion** (a line is hit) | RRPV = 0 | "I was wrong, it is hot; reset it to the top" |
| **eviction** | first way with RRPV == `maxRRPV`; if none, add 1 to every way and look again | "take anyone who is due; if nobody is, let everyone age" |

The insertion rule is the whole trick. A streamed line enters at `maxRRPV - 1`,
needs just one aging round to become evictable, and leaves without ever
displacing anything valuable. A genuinely hot line gets hit during that one
round, jumps to 0, and now has to be aged `maxRRPV` times before it is at risk.
**The cache stops giving new lines the benefit of the doubt, and makes them earn
their position instead.**

Two things to internalise, because they drive everything in §3:

* **The insertion RRPV is a deadline, measured in aging rounds.** A line inserted
  at *r* survives at least `maxRRPV - r` aging rounds. Insert at 0 with
  `maxRRPV = 3` and you have bought three rounds; insert at 2 and you have bought
  one.
* **Aging is global to the set.** The aging pass bumps *every* way, so no line is
  ever exempt — a protected line has a longer deadline, not immunity. This is
  what makes insertion-based protection inherently safe: it cannot starve
  anything forever.

`replacement/rrip.l2c_repl` (80 lines, shipped with the handout) is exactly this,
with `maxRRPV = 3`.

---

## 2. What I-RRIP adds

One sentence: **a data line never rises above evict-next, and an instruction
line gets exactly one aging round of protection.**

Concretely, with `IRRIP_MAX_RRPV = 1`:

| event | instruction line | data / translation line |
|---|---|---|
| inserted | RRPV 0 — survives one aging pass | RRPV 1 (= max) — evictable immediately |
| hit | RRPV 0 — back to the top | RRPV 1 — survives *this* eviction, nothing more |
| evicted | plain RRIP scan, type not consulted | same |

So **insertion and promotion are both type-aware; eviction is not.** That is not
the design I started with — I argued for insertion only, and for leaving
promotion alone because "a hit is evidence, not a guess". A 26-variant sweep
refuted that. The reason, in one number: a data line brought into this L2 is
re-referenced **0.13 times** before it leaves, while an instruction line is
re-referenced **0.54 to 3.06 times** depending on the trace. An L2 data hit
means "referenced twice", not "hot", so it does not earn the top of the set when
an instruction line wants the same way.

§14 of the design-decisions document has the measurements and the three
predictions they refuted. Everything else in the 252-line file is knobs,
classification, comments and statistics.

---

## 3. The file, in reading order

### 3.1 The knob block (lines ~60–160)

```c
#ifndef IRRIP_MAX_RRPV
#define IRRIP_MAX_RRPV 1
#endif
```

The `#ifndef` wrapper means a value can also be forced with `-DIRRIP_MAX_RRPV=7`
on the compiler command line without editing the file. The shipped value is
**1** — a one-bit RRPV. The sweep tested 1, 3 and 7; 1 was both the cheapest
(1 024 B against 2 048 and 3 072) and the strongest, because with only two
classes to separate there is nothing for the extra states to express, while a
wider range means a longer aging loop and a staler set. `scripts/sweep_task2a.py`
rewrites the `#define` line instead (more visible in the generated variant), but
either works.

```c
#ifndef IRRIP_INSERT_DATA
#define IRRIP_INSERT_DATA IRRIP_MAX_RRPV
#endif
```

Note the value is an *expression*, not a literal. That matters: change
`IRRIP_MAX_RRPV` to 7 and the data insertion point follows it to 7, staying
"evict-next" rather than becoming an absolute 1 that means something completely
different at a different width.

**This is also a trap worth seeing.** The original version of this knob read
`(IRRIP_MAX_RRPV - 1)`, following SRRIP. At `IRRIP_MAX_RRPV == 1` that
expression evaluates to **0** — identical to `IRRIP_INSERT_INSTR` — so the
policy would have had no instruction bias at all, silently, with no error and
no warning. A `#define` written as an expression has to be checked at every
value the sweep can give it.

Then ten `static_assert`s:

```c
static_assert(IRRIP_EVICT_SLACK >= 0 && IRRIP_EVICT_SLACK < IRRIP_MAX_RRPV,
              "IRRIP_EVICT_SLACK must be 0..IRRIP_MAX_RRPV-1");
```

`static_assert` is a compile-time check (C++11). These exist because a sweep is
a program generating programs: if a knob combination is nonsense, I want the
*build* to fail loudly rather than a simulation to succeed quietly and produce a
number that looks like a result. This particular one matters most — a slack equal
to `maxRRPV` would make the eviction preference match every way in the set, which
is not a bounded preference but "always evict a data line".

### 3.2 State (lines ~165–180)

```c
uint8_t l2_irrip_rrpv[L2C_SET][L2C_WAY];
```

One RRPV per line. `L2C_SET` is 1024 and `L2C_WAY` is 8 (`inc/cache.h:93-94`), so
8192 entries. `uint8_t` is a modelling convenience — the hardware cost is
`ceil(log2(maxRRPV+1))` bits per line, which is 2 bits by default, and
`l2c_replacement_final_stats()` prints that accounting.

Declared at file scope rather than as a `CACHE` member because that is how every
policy in this tree does it, including the supplied `rrip.l2c_repl`. It works
because only one `.l2c_repl` file is ever compiled: `build_champsim.sh` copies
the chosen one over `replacement/l2c_replacement.cc`.

The counters below it (`irrip_insert[3]`, `irrip_promote[3]`, …) feed the final
stats only. **They never influence a decision** — worth being able to say out
loud, because a counter that feeds a decision is part of the policy and has to be
counted in the storage budget.

### 3.3 Classification (lines ~185–230)

```c
static inline int irrip_class(uint32_t type, uint8_t isInstruction)
{
    if (type == LOAD_TRANSLATION || type == PREFETCH_TRANSLATION || type == TRANSLATION_FROM_L1D)
        return IRRIP_TRANSL;
    if ((type == LOAD || type == PREFETCH) && isInstruction)
        return IRRIP_INSTR;
    return IRRIP_DATA;
}
```

Three lines of logic, two decisions.

**Translations are tested first.** An instruction page walk arrives with
`packet.instruction == 1`, so without this ordering it would be classified as an
instruction line. It is not one — it is page-table data on the way to an
instruction fetch. ChampSim agrees: `fill_cache()` sets `block.translation` on it
and leaves `block.instruction` at 0.

**The split is identical to ChampSim's own.** Compare `src/cache.cc:60-71`:

```c
uint8_t fill_packet_type = 0; //1.Translation 2. Instruction 3. Data
if(cache_type == IS_L2C) {
    if(type == PREFETCH_TRANSLATION || type == TRANSLATION_FROM_L1D || type == LOAD_TRANSLATION)
        fill_packet_type = 1;
    else if((type == LOAD || type == PREFETCH) && instruction)
        fill_packet_type = 2;
    else fill_packet_type = 3;
}
```

Same predicates, same order. This is what makes the nine `L2C <X> Evicting <Y>`
counters usable as evidence about my policy — my `INSTR` *is* their
"Instructions", so `Data Evicting Instructions` means precisely "a fill I classed
as DATA replaced a line I would have classed as INSTR".

`WRITEBACK` and `RFO` fall through to `DATA`. Correct: a writeback is a dirty data
line being pushed down; an RFO is a store. Neither is an instruction fetch.

The two helpers below it (`irrip_insert_rrpv`, `irrip_promote_rrpv`) are just
3-way lookups mapping a class to its knob. Keeping them separate from
`irrip_class` means the *classification* and the *policy applied to a class* are
independently readable, which is also why the sweep can change one without
touching the other.

### 3.4 `l2c_initialize_replacement()` (lines ~235–270)

```c
for (int i = 0; i < L2C_SET; i++)
    for (int j = 0; j < L2C_WAY; j++)
        l2_irrip_rrpv[i][j] = IRRIP_MAX_RRPV;
```

Every way starts at `maxRRPV`, i.e. "evict me". This is the trick that lets
`find_victim` skip an invalid-line check: an untouched way already reads as due
for eviction, so a cold cache fills way 0, then way 1, and so on, without ever
disturbing a resident line. The supplied `rrip.l2c_repl` relies on the same
trick; I kept it and documented it rather than adding a redundant `valid` scan.

Then it prints the configuration:

```
L2C I-RRIP config  MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | ...
```

This line is load-bearing. `sweep_task2a.py` reads it back out of each log and
refuses to tabulate a run whose compiled configuration is not the one it asked
for. Without it, a failed rebuild would silently report the previous variant's
numbers under the new variant's name — which is the kind of error that survives
review because every individual number is real.

### 3.5 `l2c_find_victim()` (lines ~275–340)

```c
while (1)
{
#if IRRIP_EVICT_PREFER_DATA
    for (int i = 0; i < L2C_WAY; i++)
        if (l2_irrip_rrpv[set][i] + IRRIP_EVICT_SLACK >= IRRIP_MAX_RRPV
            && current_set[i].instruction == 0)
        { irrip_evict_pref++; return i; }
#endif

    for (int i = 0; i < L2C_WAY; i++)
        if (l2_irrip_rrpv[set][i] == IRRIP_MAX_RRPV)
            return i;

    for (int i = 0; i < L2C_WAY; i++)
        l2_irrip_rrpv[set][i]++;
    irrip_age_rounds++;
}
```

Read the second and third loops first: **that pair is plain RRIP**, byte-for-byte
the same algorithm as the supplied `rrip.l2c_repl`. Find someone at the edge;
if nobody is there, age everyone and look again. It always terminates: each pass
adds 1 to every RRPV, so after at most `maxRRPV` passes some way must reach
`maxRRPV`.

The first loop is compiled out entirely by default (`#if` on a macro that is 0),
which is why "eviction is unchanged" is literally true rather than
approximately true. When switched on it is a *bounded* diversion: pass over an
instruction line if some non-instruction line is within `IRRIP_EVICT_SLACK` of
the edge.

* `slack = 0` → the condition is `rrpv == maxRRPV && !instruction`: the same
  candidates RRIP would have considered, just preferring a data one among them.
* `slack = 1` → also eligible are data ways at `maxRRPV - 1`, i.e. ways not yet
  due. We are now willing to evict a data line early to spare an instruction
  line. That is the real trade, and it is the reason the knob exists separately
  from the on/off switch.

Note `current_set[i].instruction` — this reads the *resident* line's class
straight out of the `BLOCK` array that ChampSim already maintains for the L2C
(`src/cache.cc:2929`). Eviction needs no plumbing change at all; the parameter we
had to add is only needed by insertion (§3.6).

An invalid way reads `instruction == 0`, so it is preferred by this pass too —
which is what we want.

### 3.6 `l2c_update_replacement_state()` (lines ~345–410)

ChampSim calls this for both insertion and promotion, and `hit` says which:

```c
if (hit)   /* a resident line was referenced */ ...
else       /* a line is being filled */        ...
```

The promotion branch:

```c
if (type == WRITEBACK && !IRRIP_WB_PROMOTES) { irrip_wb_skipped++; return; }
l2_irrip_rrpv[set][way] = irrip_promote_rrpv(cls);
```

With the default knobs `irrip_promote_rrpv` returns 0 for every class, so this is
SRRIP's promotion exactly. The writeback escape hatch is off by default so that
I-RRIP matches the supplied RRIP here too.

The insertion branch:

```c
l2_irrip_rrpv[set][way] = irrip_insert_rrpv(cls);
```

One line, and it is the whole policy. With the defaults it writes **0** for an
instruction line and **2** for a data or translation line.

**Why the `isInstruction` parameter is genuinely necessary here.** In
`handle_fill` the order is:

```
line  56:  find_victim(...)                     <- picks the way
line 527:  update_replacement_state(..., hit=0) <- THIS function
line 553:  fill_cache(...)                      <- writes block[set][way].instruction
```

`fill_cache` is what records the new line's class, and it runs *after* this
function. So at the moment of insertion, `block[set][way]` still describes **the
line being thrown out**. The incoming line's class is unavailable from the block
array — it can only come in as an argument. That is exactly what the PDF means by
"By default I-RRIP won't build until you finish this step".

On the promotion path the line was filled long ago, so `block[set][way].instruction`
*is* valid and the parameter is redundant there. Having it anyway is useful: it
lets the policy distinguish *what the line is* from *who is asking for it*.

The inherited sanity check at the top:

```c
if ((type == WRITEBACK) && ip) assert(0);
```

A writeback is a dirty line being pushed down a level, so it carries no
instruction pointer. Both supplied policies have this; I kept it.

### 3.7 `l2c_replacement_final_stats()` (lines ~415–434)

```c
int rrpv_bits = 1;
while ((1 << rrpv_bits) - 1 < IRRIP_MAX_RRPV) rrpv_bits++;
```

The smallest field holding `0..IRRIP_MAX_RRPV`: 1 bit for max 1, 2 bits for max 3,
3 bits for max 7. Computing it rather than hard-coding it means the storage
deliverable is correct for whatever the sweep compiled, and is read off the run
rather than recomputed by hand.

```c
long type_total = IRRIP_EVICT_PREFER_DATA ? (long)L2C_SET * L2C_WAY * 1 : 0;
```

The type bit is charged **only when the policy reads it**. Insertion and promotion
get the class from the packet, which is in flight through the MSHR anyway and is
not state the cache keeps. Only the eviction preference needs the class of a
*resident* line, and that is a stored bit per line. ChampSim happens to maintain
`BLOCK::instruction` already so the simulator shows no cost, but a real
implementation would pay it — so the accounting charges it.

---

## 4. Reading a run's output

```bash
grep -E "^L2C (LOAD|DATA LOAD MPKI|INSTRUCTION LOAD MPKI)" results/task2a/irrip_trace1.txt
grep -E "^L2C .* Evicting"                                  results/task2a/irrip_trace1.txt
grep -E "^L2C (I-RRIP|IRRIP)"                               results/task2a/irrip_trace1.txt
```

| line | meaning |
|---|---|
| `L2C LOAD ... MPKI` | all L2 load misses per 1000 instructions |
| `L2C INSTRUCTION LOAD MPKI` | **the metric the PDF names as the goal.** `main.cc:198`, from `roi_instr_miss[cpu][0]` |
| `L2C DATA LOAD MPKI` | total load misses minus instruction misses. Watch this for the starvation side effect |
| `L2C Data Evicting Instructions` | times a data fill threw out an instruction line — **the conflict this policy exists to reduce** |
| `L2C Instructions Evicting Instructions` | instruction-on-instruction conflict; no type preference can help here |
| `L2C IRRIP INSERTS instr/data/transl` | how many fills of each class — sanity-checks the classifier |
| `L2C IRRIP EVICT PREF FIRED` | how often the eviction preference actually changed a victim. 0 with the default knobs, by construction |
| `L2C IRRIP STORAGE ... total_bytes` | the storage deliverable |

The last one is the useful trick: `Data Evicting Instructions` is *direct evidence
about the mechanism*, independent of whether MPKI happened to move. If instruction
MPKI barely changes but `data→instr` drops sharply, the policy did what it was
designed to do and the limit is somewhere else (capacity, or latency being hidden
anyway). That distinction is most of the analysis.

---

## 5. Study roadmap — five chunks

**Chunk 1 (20 min) — RRIP itself.** Read §1 above, then
`replacement/rrip.l2c_repl` top to bottom. It is 80 lines. Answer for yourself:
why does inserting at `maxRRPV - 1` rather than 0 defeat thrashing? Why does the
victim loop always terminate?

**Chunk 2 (20 min) — the headroom.** Read §2 of
`docs/TASK2A_DESIGN_DECISIONS.md`. Then run the awk one-liner in Section 2.2 of
that document against `results/task1/baseline_trace2.txt` yourself. The question
to be able to answer: *trace2 has the highest instruction MPKI of the three — why
do I expect it to benefit least?*

**Chunk 3 (30 min) — the central argument.** §6 of the design-decisions
document, all five sub-sections. This is the graded deliverable. Be able to state
the one-line thesis from memory, and give the three separate objections to
modifying eviction.

**Chunk 4 (30 min) — the code.** §3 above, with the file open beside it. Pay
attention to §3.6: the ordering argument for why insertion needs the parameter is
the thing most likely to be asked about, because it is the step the PDF makes
mandatory.

**Chunk 5 (20 min) — storage and knobs.** §7, §8 and §14.6 of the
design-decisions document. Be able to derive **1024 bytes** from `L2C_SET`
(1024) × `L2C_WAY` (8) × 1 bit, to say why that is a third of the LRU it
replaces, and to say why instruction-consciousness itself costs 0 extra bits.

**Chunk 6 (30 min) — what the measurement changed.** §14 of the design-decisions
document, especially §14.2 (reuse density: 0.13 hits per data fill against
0.54–3.06 per instruction fill — the number that justifies the whole design) and
§14.3 (the three predictions the sweep refuted, and why each argument was
wrong). This is the part most worth being able to discuss, because it is where
the work stops being a restatement of the handout.

### Questions to be able to answer

1. Why does the supplied `rrip.l2c_repl` not compile in a fresh checkout?
2. At the moment `update_replacement_state` is called with `hit == 0`, what does
   `block[set][way]` contain, and why does that force the signature change?
3. You inserted instruction lines at RRPV 0. In units of aging rounds, how much
   longer do they survive than data lines, and why is that not starvation?
4. The PDF says to change insertion, promotion *and* eviction. You changed two.
   Why is eviction still untouched — and which of your original arguments for
   leaving it alone did the sweep refute?
8. A data line in this L2 is re-referenced 0.13 times per fill. Which two knob
   choices does that single number justify?
9. Your best-IPC configuration has *worse* total L2 MPKI than another variant.
   Why is that not a contradiction?
5. Which trace do you expect to benefit least, and why is that not the one with
   the lowest instruction MPKI?
6. How much storage does instruction-consciousness itself cost, and why?
7. What stops a sweep from reporting a stale binary's numbers as a new result?
