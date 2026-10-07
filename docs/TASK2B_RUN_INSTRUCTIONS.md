# Task 2b — how to reproduce every number

Everything here assumes the **GCC 7.5.0** container. clang/macOS produces
*different simulated counters* on these traces (a known UB at `src/cache.cc`
around the MSHR index, documented in Task 2a §13.2), so a non-GCC-7 build is
not comparable and the scripts reject it.

Check the toolchain first:

```bash
g++ --version        # must be 7.x
```

## 1. Build the four configurations

Task 2b compares four L2 policies against the shared LRU baseline. Build all
four (each writes a distinct binary under `branch/`):

```bash
./build_champsim.sh no lru       lru_t2a      # LRU baseline (shared with Task 2a)
./build_champsim.sh no rrip      rrip         # supplied SRRIP (prioritisation OFF)
./build_champsim.sh no irrip     irrip        # Task 2a static I-RRIP (prioritisation ON)
./build_champsim.sh no dyn_irrip dyn_irrip    # the dynamic duel (this task)
```

The first argument `no` means "no L1D prefetcher" — Task 2b isolates the L2
replacement policy, so the prefetcher is off for all four. (Task 3 is where SPP
comes back.)

## 2. Run all four across the three traces

```bash
./scripts/run_task2b.sh ../traces 3
```

`../traces` is the trace directory; `3` is the job count. The script runs 25M
warmup + 25M simulation per trace, exactly as the README mandates, and writes
`results/task2b/<policy>_<trace>.txt`. It refuses to run any binary that is not
a GCC-built ELF or that is older than its own source inputs, so a stale or
wrong-toolchain binary cannot quietly pollute the results.

## 3. Parse and plot

```bash
python3 scripts/parse_task2b.py      # -> results/task2b/task2b.csv + task2b_tables.md
python3 scripts/plot_task2b.py       # -> speedup / IPC / MPKI / mode PNGs
```

`parse_task2b.py` reconstructs the expected config line from the knobs and
refuses any log whose printed identity line does not match — the same
anti-staleness guard Task 2a uses.

## 4. If you change a knob in `dyn_irrip.l2c_repl`

The dynamic policy has knobs (selector, leaders, window, instruction weight —
see the knob block and `TASK2B_DESIGN_DECISIONS.md`). If you edit one, you
**must rebuild and rerun only `dyn_irrip`** — the other three policies are
unaffected:

```bash
./build_champsim.sh no dyn_irrip dyn_irrip
./scripts/run_task2b.sh ../traces 3
python3 scripts/parse_task2b.py && python3 scripts/plot_task2b.py
```

`run_task2b.sh` detects a knob change (it compares against `EXPECT_DYN` and
prints `[redo]`) so it re-runs `dyn_irrip` rather than reusing a stale log.

## 5. The sweep (optional — how the shipped knobs were chosen)

The 17-variant sweep that selected selector 2 / 8 leaders / weight 2 is:

```bash
python3 scripts/sweep_task2b.py ../traces 3            # all variants
python3 scripts/sweep_task2b.py --only F ../traces 3   # one variant group
```

Sweep logs land in `results/task2b_sweep/`. The shipped `dyn_irrip` reproduces
the sweep's `psel_lead8` row **bit-for-bit** on every `L2C` line except the
`DYN COUNTERS` line (which the shipped build reports cumulatively — see the
design doc §6).

## 6. Verify everything

```bash
python3 scripts/verify_task2b.py
```

This checks that the source, the logs, and the design-doc numbers all agree:
leader placement is fair, the mandated counters are non-zero, storage
arithmetic is exact, every translation unit compiles for all four policies, and
every figure quoted in `TASK2B_DESIGN_DECISIONS.md` matches the logs. A clean
run is **0 failed**. (The three `DYN COUNTERS` checks fail until you have done
the rebuild+rerun of step 4 with the current source.)
