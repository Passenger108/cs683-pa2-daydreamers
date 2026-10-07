# Task 3 — how to reproduce every number

GCC 7.5.0 container only (clang/macOS gives different simulated counters — see
Task 2a §13.2). Check first: `g++ --version` must be 7.x.

## 1. Build the four configurations

```bash
./build_champsim.sh no  lru       lru_t3          # LRU baseline
./build_champsim.sh spp lru       spp_t3          # standalone SPP  (bar #1)
./build_champsim.sh no  dyn_irrip dyn_irrip_t3    # standalone dynamic I-RRIP (bar #2)
./build_champsim.sh spp dyn_irrip spp_dyn_irrip   # the COMBINED design
```

Arg 1 is the L1D prefetcher, arg 2 the L2C replacement, arg 3 the binary name
(README §1). The combined design is just `spp` + the Task-2b policy file, which
now contains the prefetch-awareness that only activates when a prefetcher feeds
it `PREFETCH` fills.

## 2. Run the comparison

```bash
./scripts/run_task3.sh ../traces 3
python3 scripts/parse_task3.py       # -> results/task3/task3.csv + prints the Task 3 bar
python3 scripts/plot_task3.py        # -> IPC / speedup / MPKI / accuracy / coverage PNGs
```

`parse_task3.py` prints, at the bottom, `combined vs SPP-alone vs
dynI-RRIP-alone` and whether the combined beats **both** — the Task 3 bar.

## 3. Choose the prefetch insertion depth (the sweep)

The shipped `DYN_PF_INSERT` is chosen from measurement, not assumed:

```bash
python3 scripts/sweep_task3.py ../traces 3          # 4 variants x 3 traces, all built WITH spp
python3 scripts/sweep_task3.py --summary-only       # ranks them + checks the bar
python3 scripts/sweep_task3.py --only pf_max ../traces 3   # one variant
python3 scripts/sweep_task3.py --list
```

Variants: `unaware` (ablation — prefetch treated as data), `pf_max` (insert at
`MAX_RRPV`), `pf_max1` (`MAX-1`), `pf_mid` (1). The summary names the best aware
variant and whether it beats both standalones. If the winner is not the current
default, set `#define DYN_PF_INSERT` in `replacement/dyn_irrip.l2c_repl` to the
winner and re-run step 2 for `spp_dyn_irrip` only (the runner detects the knob
change and the rebuilt binary, and redoes just that config).

## 4. Build the summary PDF

```bash
./scripts/build_summary_task3.sh     # -> Summary_Task3.pdf  (pandoc; not in the Docker container)
```

Run this where pandoc/pdflatex exist (not the GCC container). Every figure is
recomputed from `results/task3/*.txt`.

## 5. Verify everything

```bash
python3 scripts/verify_task3.py
```

Checks: prefetch-awareness is really in the policy; all knob combinations
compile; **the standalone `dyn_irrip_t3` reproduces Task 2b's `dyn_irrip`
bit-for-bit** (proof the edit is inert without a prefetcher); the combined run
actually saw and handled prefetches; **the combined beats both standalones in
IPC** (the Task 3 bar); metric definitions match Task 1; and the design-doc
numbers match the logs. A clean run is `0 failed`.
