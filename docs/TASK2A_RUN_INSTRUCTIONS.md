# Task 2a — run instructions

Everything here runs **inside the GCC 7 container**. GCC 7 is not a preference:
g++ 11 at `-O3` deadlocks this ChampSim before it prints `Warmup complete`
(undefined behaviour at `src/cache.cc:1885` reads `MSHR.entry[-1]`, and newer
codegen turns that into a hang). Every number in the Task 2a results must come
from GCC 7 at `-O3`, exactly as in Task 1.

> The only thing I ran with g++ 11 was `g++ -fsyntax-only`, purely to check that
> the code compiles and that each sweep variant's `static_assert`s pass.
> `-fsyntax-only` emits no binary and produces no results.

Inside the container, check this first:

```bash
g++ --version        # must say 7.x
gcc --version        # must say 7.x
```

If not, `sudo update-alternatives --config g++` and `--config gcc` (the repo
README has the full setup).

---

## Section 0 — where things stand

Already done, nothing for you to run:

| | |
|---|---|
| `update_replacement_state` extended with `uint8_t isInstruction` | 28 declarations + 6 call sites in `src/cache.cc` |
| `replacement/irrip.l2c_repl` written | 521 lines, all knobs in one block at the top |
| `replacement/rrip.l2c_repl` now builds | it never could before — that was the build break the PDF warned about |
| `scripts/run_task2a.sh`, `parse_task2a.py`, `plot_task2a.py`, `sweep_task2a.py` | written and syntax-checked |
| `scripts/verify_task2a.py` | self-audit: checks the docs' claims against the source and the logs |
| `docs/TASK2A_DESIGN_DECISIONS.md` | every decision and its reasoning, plus predictions made before the runs |

Branch is `nitin2`. **No commits have been made — those are yours.**

---

## Section 1 — build the three main binaries

> **Everything below, including the sweep, must run inside the container.**
> The first attempt ran the sweep on the macOS host, so all 51 runs were built
> by Apple clang and had to be thrown away: for an *identical* policy, clang and
> GCC 7 differ by up to 3.82 % in L2 instruction MPKI on trace2, which is as
> large as the knob effects being measured. The scripts now refuse to run
> outside GCC 7 on Linux, but check `g++ --version` anyway.
> See `docs/TASK2A_DESIGN_DECISIONS.md` §13.2.

Run these from the repository root (inside the container, i.e.
`/work/cs683-pa2-daydreamers`):

```bash
./build_champsim.sh no lru   lru_t2a
./build_champsim.sh no rrip  rrip
./build_champsim.sh no irrip irrip
```

Each is a full `make clean` + `make`, so expect a minute or two apiece.

Three configurations, because two would not answer the question:

* **`lru_t2a`** — no prefetcher, stock LRU at L2. The speedup denominator.
* **`rrip`** — the SRRIP the handout ships. Without this we could only show
  "I-RRIP beats LRU", which would not separate *RRIP's* benefit from
  *instruction-consciousness's* benefit. **`I-RRIP − RRIP` is the number that
  actually answers Task 2a.**
* **`irrip`** — our policy.

The L1D prefetcher is `no` for all three on purpose: Task 2a is about the
replacement policy, so the prefetcher is held fixed. SPP rejoins in Task 3.

Expect `irrip` to print its configuration on startup:

```
L2C I-RRIP config  MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
```

If any build fails, stop and send me the error — do not work around it.

---

## Section 2 — run the nine main simulations

```bash
./scripts/run_task2a.sh ../traces 3
```

`../traces` is the trace directory, `3` is how many simulations to keep in
flight. 3 configs × 3 traces = 9 runs at 25M warmup + 25M simulation, which is
roughly what Task 1's `run_task1.sh` took.

The script skips any log that already reached the `Region of Interest` section,
so it is safe to re-run after an interruption. Logs land in `results/task2a/`.

### 2.1 The verification step — please actually do this one

`lru_t2a` is the *same configuration* as Task 1's `baseline`. Re-running it under
the new 9-parameter signature is how we prove the plumbing change altered no
behaviour:

```bash
for t in trace1 trace2 trace3; do
  echo "=== $t ==="
  diff <(grep -E "^(L2C|L1D|LLC|CPU 0 cumulative)" results/task1/baseline_$t.txt) \
       <(grep -E "^(L2C|L1D|LLC|CPU 0 cumulative)" results/task2a/lru_t2a_$t.txt) \
    && echo "IDENTICAL - signature change is behaviour-neutral"
done
```

If these come out identical, the Task 1 results stand untouched and we can say so
in the write-up. If they differ, something is wrong with the plumbing edit and I
need to know before anything else proceeds.

---

## Section 3 — tables and plots

```bash
python3 scripts/parse_task2a.py
python3 scripts/plot_task2a.py
```

Produces, in `results/task2a/`:

| file | what |
|---|---|
| `task2a.csv` | one row per (config, trace), every metric |
| `task2a_tables.md` | the tables the PDF asks for, plus the eviction-conflict analysis |
| `task2a_ipc.png` | IPC |
| `task2a_speedup.png` | speedup vs LRU, geometric mean |
| `task2a_l2c_load_mpki.png` | L2C load MPKI |
| `task2a_instr_load_mpki.png` | **L2 instruction load MPKI — the metric the PDF names as the goal** |
| `task2a_data_load_mpki.png` | L2 data load MPKI — watch this for the starvation side effect |

`parse_task2a.py` also prints a summary to the terminal. **Paste that terminal
summary back to me** and I will read the result before we touch the knobs.

Aggregation, in case it comes up: geometric mean for speedup (it is a ratio),
arithmetic mean for the MPKIs (already per-1000-instructions, and every trace ran
exactly 25M instructions, so this equals the pooled value).

---

## Section 4 — the knob sweep

Do **not** start this until Section 3 looks sane. If the baseline comparison is
wrong, 51 more runs will just be wrong 51 times.

```bash
python3 scripts/sweep_task2a.py --list          # see the 17 variants, no runs
python3 scripts/sweep_task2a.py ../traces 3     # the whole sweep
```

26 variants x 3 traces = **78 simulations plus 26 full rebuilds** (Stage 1 is 17 of them, Stage 2 the remaining 9). The rebuilds
are the slow part. If you would rather do it in sittings, the groups are
independent and resume cleanly:

```bash
python3 scripts/sweep_task2a.py --only base,B,C ../traces 3    # insertion first
python3 scripts/sweep_task2a.py --only A       ../traces 3    # RRPV width
python3 scripts/sweep_task2a.py --only E,F,G   ../traces 3    # promotion, eviction, writeback
python3 scripts/sweep_task2a.py --only D       ../traces 3    # translations
python3 scripts/sweep_task2a.py --summary-only                # retabulate, no runs
```

**If you only have time for part of it, run `base,B,C` first.** Those are the
rows that test the central design decision (where to insert instruction lines,
and whether to also demote data). Group `B`'s `ins_i2` row is the control that
must reproduce RRIP exactly — it is the cheapest way to catch a broken harness.

Output: `results/task2a_sweep/<variant>_<trace>.txt` and
`results/task2a_sweep/sweep_summary.md`. **Send me `sweep_summary.md`** and I
will pick the knob values and write up what the sweep confirmed and what it
refuted.

How a variant is built, so nothing here is mysterious: the script copies
`irrip.l2c_repl` to `irrip_sweep.l2c_repl` with one `#define` rewritten, runs
`./build_champsim.sh no irrip_sweep sw_<id>`, runs the three traces, and deletes
the copy at the end. It then reads each run's printed configuration back out of
its own log and **refuses to tabulate any run whose compiled configuration is not
the one that was requested** — so a stale binary cannot be reported as a result.
A build failure is written to `results/task2a_sweep/BUILD_FAIL_<id>.txt` and the
sweep carries on with the next variant.

---

## Section 5 — what happens after

Once I have the Section 3 summary and the Section 4 sweep:

1. I pick the final knob values from measured data, not argument.
2. If the sweep contradicts a decision in `TASK2A_DESIGN_DECISIONS.md` §9, I
   change the default, say which prediction was wrong, and why. Those are the
   most useful paragraphs in the write-up.
3. I rebuild the final `irrip` with the chosen values and we re-run Sections 2–3
   so the headline tables and plots come from the shipped configuration.
4. I write the Task 2a section of the summary, with the rationale deliverable
   (insertion / promotion / eviction) and the storage breakdown.
5. I tell you Task 2a is wrapped up, and we move to 2b.

---

## Section 6 — the self-audit (run it any time)

```bash
python3 scripts/verify_task2a.py
```

Checks that what the documents claim is actually true of the tree: that every
knob default in `irrip.l2c_repl` matches the table in the design doc, that every
knob is `static_assert`-guarded, that the storage arithmetic is right, that every
`file:line` citation in the docs still points at what it says it does, that all
29 signatures carry the new parameter and there are exactly 6 call sites, and
that every baseline figure quoted in the design doc matches
`results/task1/baseline_*.txt`.

It exits non-zero on any failure, so it is safe to run before a commit. It
currently reports **101 passed, 0 failed** — and it earned its place: its first
run found five real problems, including a missing `static_assert` on
`IRRIP_WB_PROMOTES` that would have let a bad sweep value behave as 1 instead of
being rejected.

---

## Troubleshooting

| symptom | cause | what to do |
|---|---|---|
| simulator spins at 100 % CPU, never prints `Warmup complete` | built with g++ 11, not GCC 7 | check `g++ --version`, rebuild |
| `[ERROR] Cannot find L2C replacement policy` | typo in the policy name | it must match a file in `replacement/*.l2c_repl` — `lru`, `rrip`, `irrip` |
| `static_assert failed` during a sweep build | a knob value out of range | intended behaviour — it refuses to build rather than produce a misleading number |
| a sweep variant missing from `sweep_summary.md` | its three runs did not all complete, or its compiled config did not match | check for `BUILD_FAIL_<id>.txt`, then re-run that group |
| `parse_task2a.py` says "no Region of Interest section" | that run was killed mid-flight | delete that one log and re-run `run_task2a.sh` |
| `git` complains `File exists` about a `.lock` file under `.git` | a stale lock from an interrupted operation | `rm -f .git/*.lock` then retry |

## Related documents

* `docs/TASK2A_DESIGN_DECISIONS.md` — every decision, the alternatives rejected,
  the storage accounting, and the predictions made before the runs.
* `docs/TASK2A_IRRIP.md` — the code, explained line by line.
* `docs/TASK1_SPP.md`, `docs/RUN_INSTRUCTIONS.md` — Task 1, for comparison.
