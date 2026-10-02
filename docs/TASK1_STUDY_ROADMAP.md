# Task 1, in digestible chunks — a study roadmap

Ten chunks, 15–30 minutes each. Do them in order; each one builds on the last.

Every chunk has the same three parts:

* **Read** — the exact file and lines.
* **Do** — something small and concrete, so it is not passive reading.
* **You've got it when** — a question you should be able to answer out loud, without notes.
  If you can't, redo the chunk. These are the questions an instructor actually asks.

Total: about four hours. You do not need to do it in one sitting — chunks 1–4 are one
session, 5–8 another, 9–10 a third.

---

## Chunk 1 — What a prefetcher is plugged into (20 min)

**Read**

* `README.md` — the Compile and Run sections only.
* `build_champsim.sh`, lines 180–200 (the block of `cp` commands).

**Do**

Run this and watch what changes:

```bash
ls -la prefetcher/l1d_prefetcher.cc
./build_champsim.sh spp lru spp
ls -la prefetcher/l1d_prefetcher.cc
head -5 prefetcher/l1d_prefetcher.cc
```

**You've got it when** you can explain why editing `prefetcher/l1d_prefetcher.cc` is a
mistake, and which file you edit instead.

> The answer: `build_champsim.sh` does `cp prefetcher/${L1D_PREFETCHER}.l1d_pref
> prefetcher/l1d_prefetcher.cc`. The `.cc` is **generated** and overwritten on every build.
> The real source is `prefetcher/spp.l1d_pref`. The long binary name encodes the whole
> configuration, which is how you can tell two binaries apart later.

---

## Chunk 2 — The three hooks a prefetcher gets (20 min)

**Read**

* `inc/cache.h`, lines 374–397 — the list of prefetcher member functions.
* `prefetcher/no.l1d_pref` — the empty prefetcher. All four functions, doing nothing.

**Do**

List the three hooks the L1D prefetcher actually implements, and write one sentence each
on *when* ChampSim calls them.

**You've got it when** you can say what `l1d_prefetcher_operate` receives and why each
argument is there.

> `(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint8_t critical_ip_flag)`
> — the address being accessed, the PC of the instruction accessing it (this is what makes
> it an *IP*-based prefetcher), whether it hit, and what kind of access it was. The `ip` is
> the whole reason a stride prefetcher can work: it lets you separate one instruction's
> address stream from everyone else's.

---

## Chunk 3 — IP-stride, line by line (30 min)

**Read**

`prefetcher/ip_stride.l1d_pref` — all 139 lines. It is the smallest complete prefetcher
you will ever read.

**Do**

On paper, trace the tracker state for one IP seeing cache-line addresses
`100, 102, 104, 106`:

| access | `cl_addr` | `stride` | `last_stride` | does it prefetch? | what does it emit? |
|---|---|---|---|---|---|
| 1 | 100 | — | 0 | | |
| 2 | 102 | | | | |
| 3 | 104 | | | | |
| 4 | 106 | | | | |

Then do it again for `100, 101, 103, 105, 107, 110` (the PDF's non-uniform pattern) and
see it fall apart.

**You've got it when** you can state the exact condition under which `ip_stride` issues a
prefetch, and why the first access to a new IP never prefetches.

> Condition: `stride == trackers[index].last_stride` and `stride != 0`. It needs the *same*
> stride twice in a row. A brand-new tracker returns early at line 73 — one address gives
> you no stride at all.

---

## Chunk 4 — The five weaknesses (25 min)

**Read**

`docs/TASK1_SPP.md` §1.1 — the table of five weaknesses.

**Do**

For each of the five, find the exact line in `ip_stride.l1d_pref` that causes it. Write the
line number next to it. Then verify weakness 4 for yourself:

```bash
grep -n "l1d_prefetcher_operate(" src/cache.cc
```

Look at what is passed as `type` on lines 2465 and 2649.

**You've got it when** you can explain weakness 4 — the self-training feedback loop —
without looking. This is the best thing in the whole task to be able to explain, because it
is a real bug in supplied code that you found by reading the caller rather than the callee.

> ChampSim calls `l1d_prefetcher_operate` from the **prefetch queue** too, with
> `type = PREFETCH` and the IP that `prefetch_line()` copied into our own prefetch packet.
> `ip_stride` does not filter on `type`, so addresses it invented come back as training
> data and advance `last_cl_addr`. SPP's very first line, `if (type != LOAD) return;`, is
> what prevents it.

---

## Chunk 5 — SPP's two tables (25 min)

**Read**

`prefetcher/spp.l1d_pref`, the header comment plus the `IP_ENTRY` and `PATTERN_ENTRY`
class definitions.

**Do**

Draw the two tables on paper with their field widths. Add up the bits per entry yourself
and check you get 56 and 9. Then check your totals against `docs/TASK1_SPP.md` §6.

**You've got it when** you can answer: *why is the stride field exactly 7 bits?*

> Because strides are computed in **page-offset space**. A 4 KB page holds 64 lines, so an
> offset is 0–63 and a stride is −63…+63 — which is exactly a 7-bit signed number. The
> width is not a guess that happens to fit; it is a consequence of the representation, and
> that same choice is what makes crossing a page impossible.

---

## Chunk 6 — Page-offset space, and why it solves three problems (20 min)

**Read**

`spp.l1d_pref` section (2) of `l1d_prefetcher_operate`, and `docs/TASK1_SPP.md` §2.2.

**Do**

Take virtual address `0x7f1234_5A80`. Compute by hand:

* the page tag (`addr >> 12`, low 12 bits),
* the line offset inside the page (`(addr >> 6) & 63`).

Now take the next address `0x7f1234_5B40` and compute the stride. Then take
`0x7f1235_0000` and convince yourself why that one must be *skipped* rather than used.

**You've got it when** you can name the three requirements this one representation choice
satisfies at once.

> (1) Page confinement becomes structural — an out-of-page address is never representable.
> (2) The 7-bit stride field is provably sufficient. (3) IP-stride's garbage-stride-at-every-
> page-boundary bug disappears.

---

## Chunk 7 — The signature (30 min, the conceptual core)

**Read**

`docs/TASK1_SPP.md` §4, then `spp_update_signature` and `spp_train_pattern` in the code.

**Do**

```bash
python3 scripts/verify_design.py
```

Read the output next to §4.3. Then by hand, starting from `sig = 0`, apply
`sig = ((sig << 3) ^ (stride & 0x7F)) & 0x3FF` for strides `1, 2, 2, 2, 3` and check you
reproduce one of the five signatures the script prints.

**You've got it when** you can explain, in one breath, what the pattern table maps and why
it needs no tag.

> It maps *a compressed history of the last ~4 strides* → *the next expected stride*. It
> needs no tag because a signature collision does not corrupt a value: the 2-bit confidence
> counter is decremented on a mismatch, and `conf < 2` means "refuse to predict". Paying 16
> bits of tag per entry to prevent something a 2-bit counter already handles would nearly
> triple the table's cost.

---

## Chunk 8 — Why degree > 1 needs chaining (25 min)

**Read**

`docs/TASK1_SPP.md` §5, then the single prediction loop at the end of
`l1d_prefetcher_operate`.

**Do**

Write out, for the pattern `(+1,+2,+2,+2,+3)` sitting at phase 0 with degree 3, the three
addresses SPP emits. Then write out what IP-stride would emit if it mistakenly thought the
stride was `+1`. Compare.

**You've got it when** you can explain why `break` and not `continue` when confidence runs
out.

> Every address later in the chain is built on top of this stride — `cum += next_stride`.
> Once a link is untrustworthy the whole remainder of the chain is garbage, so you stop,
> you don't skip. And the deeper point: a non-uniform pattern cannot be extrapolated by
> multiplication, which is why uniform can do `addr + k*stride` and non-uniform must replay
> the predictor on its own output.

---

## Chunk 9 — The throttle, and the mistake worth knowing (30 min)

**Read**

`docs/TASK1_SPP.md` §7.1 — including the part about the metric I got wrong first.

**Do**

```bash
grep -n "pf_lower_level++\|++pf_lower_level" src/cache.cc
sed -n '2600,2606p' src/cache.cc
grep -n "PREFETCH  REQUESTED\|USEFUL LOAD PREFETCHES" results/task1/spp_trace1.txt
```

Compare `ISSUED: 1075443` with `PREFETCH ISSUED TO LOWER LEVEL: 69907` on trace1 and
explain the gap.

**You've got it when** you can say why `useful / issued` is the wrong denominator for
throttling.

> Because ~94 % of issued prefetch requests **hit in the L1D and are dropped** before
> fetching anything. A dropped prefetch evicts nothing and consumes no bandwidth, so it
> cannot pollute — putting it in the denominator of an anti-pollution metric dilutes the
> signal until it is useless. Measured: throttling on `useful/issued` read ~7 % and pinned
> the degree at the floor in 30 of 32 windows. The right denominator is `pf_lower_level`,
> lines actually fetched, which is also exactly what ChampSim prints as `ACCURACY`.

Also be ready for: *why is the degree floor 1 and not 0?*

> Degree 0 is absorbing. No prefetches → `pf_lower_level` stops advancing → the window
> never closes → no new accuracy is ever measured → the prefetcher can never recover. A
> control loop must not be able to switch off its own sensor.

---

## Chunk 10 — Reading your own results (30 min)

**Read**

`docs/TASK1_SPP.md` §8 and §8.7, with `results/task1/task1_tables.md` open beside it.

**Do**

Answer these from the tables:

1. On which trace does IP-stride do worst, and what single number shows it?
2. Why does SPP get *both* higher accuracy and higher coverage, when those normally trade
   off?
3. Which number shows SPP's biggest remaining weakness, and what would you change?
4. Why are the absolute speedups only ~1–2 %?

**You've got it when** you can answer all four.

> 1. trace3 — IP-stride accuracy **15.99 %**, i.e. five of every six lines it fetches are
>    never used. It is extrapolating `2*stride`, `3*stride` from a stride that isn't
>    constant.
> 2. Because SPP's extra prefetches are extra *evidence*, not extra *speculation* — the
>    non-uniform path emits an address only when a pattern entry has confidence ≥ 2, and
>    the chain breaks the moment a link drops below that. `chains cut by conf` (219 K–439 K
>    per run) counts the times it had degree budget left and chose not to use it.
> 3. trace2's **IP-table hit rate of 43.43 %** — more than half of its loads land on an
>    entry belonging to a different instruction. The fix is a bigger IP table
>    (`IP_TABLE_SETS` / `IP_TABLE_WAYS`). Note trace2 has the *highest* mean windowed
>    usefulness (67.20 %), so the prediction logic is fine — it just doesn't get to keep
>    histories.
> 4. An L1D prefetch hit saves an L2 access (~10 cycles), not a DRAM round trip, and the
>    baseline L1D hit rate is already ~94 %. trace3 proves the mechanism: lowest baseline
>    MPKI (3.403) but the largest speedup (1.0225), because its remaining misses are the
>    ones that actually stall the core.

---

## The five sentences to have ready

If you only remember five things, make them these.

1. **"IP-stride stores one stride; SPP stores a signature of the last four, so it can
   predict a repeating *sequence*."**
2. **"Strides live in page-offset space, which makes crossing a page impossible by
   construction and makes a 7-bit stride field provably sufficient."**
3. **"Uniform confidence saturates at 3 because the PDF's own example has a run of three
   identical strides — two consecutive matches — so 3 is the smallest threshold that never
   misclassifies it."**
4. **"Degree > 1 on a non-uniform pattern needs the predictor replayed on its own output,
   because you cannot multiply a stride that changes."**
5. **"The throttle measures useful lines over lines *actually fetched*, not over requests
   issued, because a dropped prefetch cannot pollute."**

---

## If you are asked something not on this list

The three places to look, in order:

1. `docs/TASK1_SPP.md` §10 — the consistency audit. It is a closed list of every pair of
   requirements that could conflict, and how each was resolved. Most "but doesn't X break
   Y?" questions are already a row in that table.
2. `docs/TASK1_SPP.md` §6 — storage. Any "how much does it cost" question.
3. `results/task1/task1_tables.md` — any "how do you know" question.
