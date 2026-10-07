# Task 2b — `replacement/dyn_irrip.l2c_repl`, read top to bottom

This is the companion to `TASK2A_IRRIP.md`. It walks the dynamic policy in the
order the file is written and explains why each piece exists. If you read
`TASK2A_IRRIP.md` first, the recurring note "same as 2a / different from 2a"
will tell you exactly what dynamism added.

The whole policy is one idea: **run plain RRIP and Task 2a's I-RRIP in the same
cache at the same time, measure which one is missing less, and give the rest of
the cache the winner.** Everything below is machinery for doing that fairly and
cheaply.

## The shape of the file

```
knob block (#defines)         -- every tunable, each with the reason it exists
globals                       -- RRPV array, PSEL, counters
DYN_MODE_* / DYN_* class ids  -- the two modes and the three line classes
dyn_role(set)                 -- is this set an RRIP leader, I-RRIP leader, or follower?
dyn_mode_of(set)              -- which mode does this set run right now?
dyn_insert_rrpv / _promote    -- the two modes expressed as RRPV values
dyn_threshold_mode            -- selectors 0/1 only
dyn_end_of_window             -- re-decide the mode, then decay
l2c_initialize_replacement    -- reset state, print the config line
l2c_find_victim               -- plain RRIP victim scan (identical in both modes)
l2c_update_replacement_state  -- the heart: track leaders, vote, insert/promote
l2c_replacement_final_stats   -- the reported metrics, incl. the PDF counters
```

## 1. The two modes, as four RRPV values

```c
static inline uint8_t dyn_insert_rrpv(int mode, int cls) {
    if (mode == DYN_MODE_RRIP) return DYN_MAX_RRPV - 1;         // RRIP: everything at max-1
    return (cls == DYN_INSTR) ? 0 : DYN_MAX_RRPV;               // I-RRIP: instr protected, data at max
}
static inline uint8_t dyn_promote_rrpv(int mode, int cls) {
    if (mode == DYN_MODE_RRIP) return 0;                        // RRIP: a hit resets to 0 (plain SRRIP)
    return (cls == DYN_INSTR) ? 0 : DYN_MAX_RRPV;               // I-RRIP: instr hit protected, data hit NOT
}
```

This four-line pair *is* the policy. Read it against Task 2a:

- **RRIP mode** is textbook SRRIP: insert everything at `MAX_RRPV - 1` (one
  reprieve before eviction), and on a hit reset to 0. No class distinction —
  this is the "normal RRIP" the PDF contrasts I-RRIP against.
- **I-RRIP mode** is Task 2a's policy, widened to 2 bits: instructions insert
  at 0 (maximally protected), data inserts at `MAX_RRPV` (first to go), and a
  *data hit* is demoted to `MAX_RRPV` rather than protected — the aggressive
  instruction bias Task 2a §6 argued for.

Why `DYN_MAX_RRPV - 1` and not `0` for RRIP-mode inserts? Because at
`MAX_RRPV 3` that is 2, which leaves data genuinely evictable while still
distinct from I-RRIP's instruction insert (0) and data insert (3). This is the
concrete reason the design doc §2 says the policy cannot run at `MAX_RRPV 1`:
there, `MAX_RRPV - 1 == 0 == ` the I-RRIP instruction insert, and the two modes
would be the same code.

## 2. Who is a leader, and who runs what

```c
static inline int dyn_role(uint32_t set) {
    uint32_t r = set % DYN_STRIDE;            // DYN_STRIDE = L2C_SET / DYN_NUM_LEADERS = 1024/8 = 128
    if (r == 0)              return DYN_LEAD_IRRIP;   // group pinned to I-RRIP
    if (r == DYN_STRIDE / 2) return DYN_LEAD_RRIP;    // group pinned to RRIP
    return DYN_FOLLOWER;                              // everyone else
}
static inline int dyn_mode_of(uint32_t set) {
    int r = dyn_role(set);
    if (r == DYN_LEAD_RRIP)  return DYN_MODE_RRIP;    // pinned, never changes
    if (r == DYN_LEAD_IRRIP) return DYN_MODE_IRRIP;   // pinned, never changes
    return dyn_mode;                                  // followers run the current winner
}
```

The leaders are a fixed sample: 8 sets locked to RRIP, 8 locked to I-RRIP, for
the whole run. Their misses feed the duel. Everyone else (`dyn_mode`) follows.

The single most important line here is `r == DYN_STRIDE / 2` for the RRIP
group. With `DYN_STRIDE = 128`, that is set offset 64 — and because the L2C set
index is address bits 6..15, with bits 6..11 being the within-page 64 B slot,
`STRIDE = 128 ≥ 64` means **both leader groups land on within-page slot 0 and
differ only in page-number bits**. That is the fair sample. At 16 or 32
leaders the stride drops below 64 and the two groups sit on *different*
within-page slots — code pages and data pages, different populations — and the
duel silently compares two workloads instead of two policies. The design doc §3
has the full table; the one-sentence rule is *leaders must differ in
page-number bits, never in within-page-offset bits*, and 8 is the smallest
count that obeys it.

## 3. The victim scan — deliberately identical in both modes

```c
uint32_t CACHE::l2c_find_victim(...) {
    while (1) {
        for (int i = 0; i < L2C_WAY; i++)
            if (dyn_rrpv[set][i] == DYN_MAX_RRPV) return i;   // evict the first max-RRPV line
        for (int i = 0; i < L2C_WAY; i++) dyn_rrpv[set][i]++; // else age the whole set and rescan
        dyn_age_rounds++;
    }
}
```

This is plain RRIP eviction, and it is the *same* in RRIP and I-RRIP mode on
purpose. The two modes differ only in the RRPV a line is *given* (insertion and
promotion); once a value is set, eviction treats all lines by the same rule.
This is the cleanest possible separation: the duel changes *what values go in*,
never *how victims come out*, so a mode switch cannot create a transient where
eviction logic disagrees with the values already in the array. Task 2a made the
same choice (eviction unchanged); here it also keeps the two modes
mode-switch-safe.

## 4. The heart: `l2c_update_replacement_state`

Called on every access. Three steps: classify, measure (leaders only), apply.

```c
int cls  = dyn_class(type, isInstruction);   // TRANSL / INSTR / DATA -- same 3-way split as Task 2a
int role = dyn_role(set);
int mode = dyn_mode_of(set);

if (type == LOAD) {
    if (role == DYN_LEAD_RRIP) {             // MEASURE in the unbiased (RRIP) leaders only
        dyn_acc[cls]++;  if (!hit) dyn_mis[cls]++;     // windowed -> drives the duel (decays)
        dyn_tot[cls]++;  if (!hit) dyn_tmis[cls]++;    // cumulative -> the PDF's reported counts
    }
    // --- selector 2 (shipped): the PSEL duel ---
    if (!hit) {
        int w = (cls == DYN_INSTR) ? DYN_INSTR_WEIGHT : 1;
        int d = (role == DYN_LEAD_IRRIP) ? +w : (role == DYN_LEAD_RRIP ? -w : 0);
        // I-RRIP-leader miss pushes PSEL up, RRIP-leader miss pushes it down; followers don't vote
        dyn_psel = saturate(dyn_psel + d);
    }
    if (++dyn_ctr >= DYN_WINDOW) { dyn_end_of_window(); dyn_ctr = 0; }
}

if (hit) dyn_rrpv[set][way] = dyn_promote_rrpv(mode, cls);   // APPLY
else     dyn_rrpv[set][way] = dyn_insert_rrpv(mode, cls);
```

Four things to notice, each a deliberate decision:

1. **Measurement is in the RRIP leaders only.** If we sampled the I-RRIP
   leaders to decide whether I-RRIP is good, the measurement would be
   contaminated by the policy under test. The RRIP group is the neutral control.
2. **Two counter pairs.** `dyn_acc/dyn_mis` are windowed and halved each window
   — the right input for a decision that must forget old phases. `dyn_tot/
   dyn_tmis` are never decayed — the right number to *report* for the PDF's
   "track accesses and misses to these sets". Reporting the decayed counter is
   the bug the design doc §6 documents; it prints near-zero because it has been
   halved 141/251/75 times by the end of the run.
3. **The vote is asymmetric by `DYN_INSTR_WEIGHT`.** An instruction-leader miss
   moves PSEL by 2, a data-leader miss by 1, because an L2 instruction miss
   stalls the front end with nothing to overlap while a data miss is hidden by
   out-of-order execution. This weight is the one cause the sweep isolated
   cleanly (design doc §5).
4. **Only `LOAD` drives the duel.** Writebacks and prefetch fills are not demand
   misses the user is waiting on, so they neither vote nor advance the window —
   the duel measures demand behaviour, which is what IPC depends on.

## 5. Re-deciding the mode: `dyn_end_of_window`

```c
// shipped path (selector 2): the followers run whichever leader group is missing less
next = (dyn_psel < DYN_PSEL_MID) ? DYN_MODE_IRRIP : DYN_MODE_RRIP;

if (next != dyn_mode) dyn_switches++;
dyn_mode = next;

// decay: halve the windowed counters and pull PSEL toward the midpoint
for (int c = 0; c < 3; c++) { dyn_acc[c] >>= 1; dyn_mis[c] >>= 1; }
dyn_psel = DYN_PSEL_MID + (dyn_psel - DYN_PSEL_MID) / 2;
```

`dyn_psel < DYN_PSEL_MID` means the I-RRIP leaders accumulated *fewer* down-votes
than the RRIP leaders gave — i.e. I-RRIP is winning — so the followers switch to
I-RRIP. The comparison is just the cache's own miss counts; there is no
threshold, which is why selector 2 cannot be miscalibrated the way selectors 0
and 1 can (design doc §4.1).

**Halve, don't clear.** Clearing at each boundary would make every window a
fresh election with no memory, so one unlucky window could flip a stable
policy. Halving keeps a fading memory: recent windows dominate, old ones fade,
and a phase that has *ended* decays back toward neutral and stops voting. The
same halving on PSEL pulls it toward the midpoint so the duel re-opens rather
than staying stuck at a saturated value.

The two threshold selectors (0 = the PDF's intensity formula, 1 = instruction
hit rate) live in the `#if` branches above the shipped line. They are swept and
kept as evidence but not shipped, because both read a *ratio* that is not
monotone in the quantity we care about (design doc §4).

## 6. Reported statistics: `l2c_replacement_final_stats`

The final-stats function prints, in order:

- `DYN-IRRIP config` — the identity line (every knob value), so a log can never
  be mistaken for a different configuration.
- `DYN MODE windows / in_irrip / pct_irrip / switches` — how long the followers
  ran each mode and how often they switched. Low switch counts here are the
  evidence behind the design doc's "these traces have no phases to exploit".
- `DYN PSEL final / mid` — where the duel settled.
- `DYN COUNTERS instr_acc / ... ` — **the PDF-mandated leader-set tracking**,
  printed from the cumulative `dyn_tot/dyn_tmis`, so it shows real traffic.
- `DYN INSERTS / PROMOTES` per class, `LEADERS`, `AGE ROUNDS`, and `STORAGE`
  (the exact bit accounting the design doc §7 reproduces: 2 RRPV bits × 8192 +
  selector = 2058 bytes).

Why a dedicated stats hook at all? Because Task 2a §13 found that a single-core
ChampSim run never called `l2c_replacement_final_stats` until `main.cc` was
patched to call it beside `l1d_prefetcher_final_stats`. That patch is shared by
both L2 policies; without it every number in this section would silently be
missing.

## 7. How this connects back to Task 2a (the dots the user asked for)

| Task 2a (static I-RRIP) | Task 2b (dynamic) |
|---|---|
| 1 RRPV bit (`MAX_RRPV 1`) | 2 bits (`MAX_RRPV 3`) — needed to keep two modes distinct |
| instructions insert at 0, data at 1 | *I-RRIP mode* does the same at the wider scale; *RRIP mode* ignores class |
| the policy is fixed | a PSEL duel picks the policy per window from leader misses |
| 3-way class split (instr/data/transl) | same split, reused so the counters line up |
| eviction unchanged | eviction unchanged, and identical across modes |
| 1024 B | 2058 B (the second RRPV bit, + 76 selector bits) |
| helps t2/t3, hurts t1 (+8.7%) | erases the t1 regression (+0.45%), best mean MPKI, slightly lower IPC |

The dynamic policy is not a new algorithm — it is Task 2a's I-RRIP and plain
RRIP, run together, with a cheap fair referee deciding which one the cache
should be. That is the whole of Task 2b, and it is why Task 3 can extend *this*
referee to also reason about SPP-prefetched lines.
