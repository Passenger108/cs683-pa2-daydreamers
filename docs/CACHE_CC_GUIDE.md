# Reading `src/cache.cc` — a guide

`src/cache.cc` is **4 298 lines** and it is the file every remaining task touches. It looks
impenetrable, and it mostly isn't — it is one small idea repeated at five levels of the
hierarchy, with a lot of special-casing bolted on.

This guide gives you a mental model first, then a map, then the twelve places that actually
matter for PA2.

---

## 1. The one idea the whole file is built on

**One `CACHE` class is instantiated for every cache in the machine** — ITLB, DTLB, STLB,
L1I, L1D, L2C, LLC, the page-table-walker caches, the BTB. They all run the same code. The
only thing that distinguishes them is the `cache_type` field, which is why you will see

```c
if (cache_type == IS_L1D) { ... }
else if (cache_type == IS_L2C) { ... }
```

everywhere. **That pattern is 80 % of the file's bulk.** Once you accept that, the file
shrinks enormously: when you are working on the L1D, every branch that isn't `IS_L1D` or
generic is noise.

### Each cache is four queues and an array of blocks

From `inc/cache.h` (lines 169–173):

| Queue | What goes in it |
|---|---|
| **RQ** — read queue | demand reads arriving from the level above (loads, RFOs) |
| **WQ** — write queue | writebacks and stores |
| **PQ** — prefetch queue | prefetch requests, from this level's prefetcher or pushed from below |
| **MSHR** | *misses in flight* — requests that missed here and are waiting on the level below |
| PROCESSED | finished requests waiting to be returned upward |

Plus `BLOCK **block` — the actual tag array, `block[set][way]`.

**The MSHR is the concept to get right**, because half the subtle behaviour lives there. It
holds one entry per outstanding miss. If a second request arrives for a line already in the
MSHR, it does not allocate a new entry — it **merges**. That merge is how a demand load
"catches" an in-flight prefetch, and it is where `late_prefetch` is counted.

### Everything is driven by `operate()`, once per cycle

Line **2816**, and it is only 20 lines — read it first:

```c
void CACHE::operate()
{
    handle_fill();        // lines coming back from below -> install them
    handle_writeback();   // stores / writebacks
    reads_available_this_cycle = MAX_READ;
    if (cache_type == IS_L1I || cache_type == IS_L1D)
        handle_processed();
    handle_read();        // demand reads
    if (PQ.occupancy && (reads_available_this_cycle > 0))
        handle_prefetch();   // prefetch requests, only with leftover read bandwidth
}
```

Two things worth noticing immediately:

* The **order** is the priority. Fills first, then writebacks, then demands, and prefetches
  **last** — and only out of `reads_available_this_cycle` left over after demands. Prefetch
  requests are genuinely second-class citizens in the pipeline, by construction.
* The whole simulator is `for each cycle { for each cache { operate(); } }`. There is no
  magic scheduler.

---

## 2. The map — where everything is

Every function in the file, with its line number. Print this page.

| Line | Function | What it does | Care about it for |
|---|---|---|---|
| 38 | `handle_fill()` | a line came back from below: pick a victim, evict, install | **Tasks 2, 3** |
| 730 | `handle_writeback()` | stores and writebacks | rarely |
| 1126 | `handle_processed()` | returns completed requests upward (VIPT path) | rarely |
| 1423 | `handle_read()` | demand reads: hit → return, miss → MSHR | **Task 1** |
| 2411 | `handle_prefetch()` | prefetch requests out of the PQ | **Task 1** |
| 2816 | `operate()` | the per-cycle driver | read first |
| 2838 | `get_set()` / 2849 `get_way()` | index and tag lookup | reference |
| 2859 | `fill_cache()` | writes a block into `block[set][way]` | **Tasks 2, 3** |
| 2969 | `check_hit()` | is this address resident? | reference |
| 3064 | `add_rq()` | enqueue a demand read | rarely |
| 3474 | `add_wq()` | enqueue a write | rarely |
| **3594** | **`prefetch_line()`** | **what your prefetcher calls** | **Task 1** |
| 3667 | `prefetch_translation()` | TLB-level prefetch | no |
| 3703 | `kpc_prefetch_line()` | dead code — it `assert(0)`s | no |
| 3750 | `add_pq()` | enqueue a prefetch | **Task 1** |
| 4055 | `return_data()` | a lower level hands data back | rarely |
| 4163 | `check_nonfifo_queue()` | **MSHR lookup / merge** | **Task 1** |
| 4226 | `add_nonfifo_queue()` | MSHR allocate | reference |

Four functions carry almost everything: `handle_fill`, `handle_read`, `handle_prefetch`,
`prefetch_line`.

---

## 3. The lifecycle of one load — follow this once, end to end

This is the single most valuable half-hour you can spend in this file. Trace one L1D load
miss that is later serviced.

1. **`handle_read()` (1423)** pulls the request off the RQ and calls `check_hit()`.
2. **Hit path** — around line **1715**:
   * `l1d_prefetcher_operate(..., cache_hit = 1, ...)` ← *your prefetcher is called on
     hits too*
   * if `block[set][way].prefetch` is set, `pf_useful++` (line **1848**) and the bit is
     cleared — **this is the definition of a "useful prefetch"**: a demand access hit a
     line that a prefetch brought in
   * `update_replacement_state(...)` with `hit = 1` (line **1766**) ← promotion, Task 2
3. **Miss path** — around line **2342**:
   * `l1d_prefetcher_operate(..., cache_hit = 0, ...)`
   * `check_nonfifo_queue(&MSHR, ...)` to see if the line is already in flight
   * **if it merges with an existing prefetch MSHR entry** → `late_prefetch++`
     (line **2250**). Your prefetch was *right* but *late*.
   * otherwise `add_nonfifo_queue(&MSHR, ...)` and the request goes to the L2
4. **Later, `handle_fill()` (38)** runs when the data returns:
   * `find_victim(...)` (line **56**) ← Task 2's eviction decision
   * `l1d_prefetcher_cache_fill(...)` (line ~504)
   * `update_replacement_state(..., hit = 0)` (line **527**) ← Task 2's **insertion**
   * `fill_cache()` (2859), which sets
     `block[set][way].prefetch = (packet->type == PREFETCH) ? 1 : 0` (line **2917**) and
     `used = 0`
   * if the block being evicted was a prefetch that was never used → `pf_useless++`
     (line **2913**)

Once you can narrate that path, the file is no longer scary.

---

## 4. The twelve lines that matter for PA2

Bookmark these.

### Task 1 — prefetching

| Line | What |
|---|---|
| 1715, 2342 | `l1d_prefetcher_operate` called on a demand **hit** / **miss** |
| **2465, 2649** | `l1d_prefetcher_operate` called **from the PQ with `type = PREFETCH`** — the self-training trap. This is why SPP starts with `if (type != LOAD) return;` |
| 3594 | `prefetch_line()` — returns **1** if queued, **0** if the PQ was full and it was silently dropped |
| 3600 / 3650 | `pf_requested++` / `pf_issued++` |
| 1848 | `pf_useful++` — demand hit on a prefetched line |
| 2913 | `pf_useless++` — prefetched line evicted without ever being used |
| **2604** | `++pf_lower_level` — *"Increment for new prefetch miss"*. A prefetch that actually **missed and allocated an MSHR entry**, i.e. genuinely fetched a line. **This is the denominator of ChampSim's `ACCURACY`** and the right denominator for throttling |
| 2250 | `late_prefetch++` — a demand caught a prefetch still in flight |
| 3652–3657 | `cross_page_prefetch_requests++` / `same_page_prefetch_requests++` — ChampSim auditing your page confinement for you |

### Tasks 2 and 3 — replacement

| Line | What | Which part of the policy |
|---|---|---|
| 56, 976 | `find_victim(...)` | **eviction** |
| 140, 527, 1080 | `update_replacement_state(..., hit = 0)` | **insertion** (on a fill) |
| 819, 1766, 2452 | `update_replacement_state(..., hit = 1)` | **promotion** (on a hit) |
| 2859 | `fill_cache()` | where `instruction` / `translation` / `prefetch` block flags are set |

Note line **2452**: `update_replacement_state` is called with `hit = 1` from
`handle_prefetch()` as well — a *prefetch* that hits an existing line promotes it. Think
about whether you want that for Task 3.

Also note the signature you will have to change for Task 2a, from `inc/cache.h:341`:

```c
(CACHE::*update_replacement_state)(uint32_t cpu, uint32_t set, uint32_t way,
                                   uint64_t full_addr, uint64_t ip,
                                   uint64_t victim_addr, uint32_t type, uint8_t hit)
```

There is no "is this an instruction line" parameter — adding one is exactly what the PDF
means by *"By default I-RRIP won't build until you finish this step."* You will need to
change the declaration in `cache.h`, every `*_update_replacement_state` definition in
`replacement/`, and all **six** call sites above. The information you want is
`packet->instruction` (see `inc/block.h`) and `MSHR.entry[...].instruction`.

---

## 5. Gotchas that will cost you hours

**L1 caches work in virtual addresses.** This ChampSim is VIPT, so `full_addr` at the L1D
is *virtual*, and the physical address only exists after translation. That is why
`handle_processed()` exists and why `handle_fill()` has that `inverse_table` lookup around
line 480 to recover a virtual address. For Task 1 this is good news — strides and page
boundaries are naturally virtual.

**`prefetch_line()` can silently fail.** It returns 0 when `PQ.occupancy == PQ.SIZE`. If
you ignore the return value you will never know your deepest prefetches were thrown away.
`L1D_PQ_SIZE` is 16 (`inc/cache.h:88`), which is one of the three reasons SPP caps its
degree at 4.

**There is real undefined behaviour in the file.** Line 1885:

```c
if ((mshr_index == -1) && (MSHR.occupancy < MSHR_SIZE)) {      // mshr_index IS -1
    if (cache_type == IS_STLB && MSHR.entry[mshr_index].type == TRANSLATION_FROM_L1D)
```

A negative array index. GCC 7 tolerated it; **GCC 11 at `-O3` deadlocks the whole
simulator** — it spins at 100 % CPU having read ~64 instruction records, and the
*unmodified* baseline binary hangs identically. This is why `README.md` has a whole GCC-7
section. Build with GCC 7.

**Stats are reset at the ROI boundary, your own counters are not.** `src/main.cc:412`
(`reset_cache_stats`) zeroes `pf_useful`, `pf_issued`, `pf_lower_level` and the
`sim_*` arrays when warm-up ends. Anything *you* declare in your prefetcher keeps counting
from cycle 0. Two consequences: read only the **Region of Interest** half of a log, and if
you keep window snapshots of ChampSim counters, take the difference as **signed** and clamp
at zero or the unsigned wrap will jam your logic (SPP does this — see `spp.l1d_pref`
section (1)).

**`DEADLOCK_CYCLE` assert.** If a PQ entry is not serviced for too long, `operate()` aborts
with a `DEADLOCK` message (line 2830). If you see that, you have flooded the PQ.

---

## 6. How to find anything in this file

Four commands cover almost every question.

```bash
# Where is this function defined?
grep -n "^\s*\(void\|int\|uint32_t\|uint64_t\)\s*CACHE::" src/cache.cc

# Where is my hook called from, and with what arguments?
grep -n "l1d_prefetcher_operate(" src/cache.cc

# Where is this counter incremented?  (the only way to learn what a stat MEANS)
grep -n "pf_lower_level++\|++pf_lower_level" src/cache.cc

# Read the surrounding context, never just the matching line
sed -n '2590,2610p' src/cache.cc
```

The third one is the habit worth building. **A ChampSim stat's name tells you almost
nothing; its increment site tells you everything.** `pf_issued` sounds like it should be
the accuracy denominator, and it is the wrong one — the only way to find that out is to
read line 2604 and see the comment *"Increment for new prefetch miss"*. That one grep is
the difference between a throttle that works and one that is silently switched off.

---

## 7. A 90-minute plan to actually learn the file

1. **(10 min)** Read `operate()` at 2816. Write the five calls in order on paper.
2. **(10 min)** Read `inc/cache.h` lines 110–185 — the `CACHE` class members. Note the four
   queues and the stat counters.
3. **(25 min)** Follow the load lifecycle in §3 above with the file open. Do not read
   sideways into the `IS_STLB` / `IS_PTW` branches — skip anything that isn't `IS_L1D` or
   unconditional.
4. **(15 min)** Read `prefetch_line()` at 3594 completely. It is only ~70 lines and it is
   the entire interface between your prefetcher and the machine.
5. **(15 min)** Grep for the three prefetch stat counters and read 10 lines around each
   increment. Write down, in your own words, what each one counts.
6. **(15 min)** Read `handle_fill()` from line 38 to line 140, which is where the
   replacement policy is driven. This is your on-ramp to Task 2.

After that you will know this file better than most people who "use" ChampSim.
