# Task 1 — exhaustive steps to generate every deliverable (GCC 7 only)

Everything in `prefetcher/spp.l1d_pref` and `scripts/` is done. What remains is
work that needs **GCC 7** and ~hours of simulation, which is why it is yours to run.

Read §0 first — it is the part that will otherwise cost you an afternoon.

---

## 0. Why GCC 7 is mandatory here (verify before trusting any number)

Built with a modern g++ (11.4) at the stock `-O3`, this ChampSim **deadlocks**: it spins
at 100 % CPU having read only ~64 instruction records and never prints
`Warmup complete`. The *unmodified* baseline binary hangs identically, and the same source
at `-O0` runs fine — so it is the toolchain, not the assignment code and not SPP. There is
UB in the supplied source that fits (`src/cache.cc:1885` indexes `MSHR.entry[-1]`), which
GCC 7 tolerated and newer GCC optimises on.

So: **build with GCC 7 at `-O3`, and sanity-check that it actually runs before launching
the long jobs.** Do not lower the optimisation level to make it work — your numbers would
not be comparable to anyone else's.

**The 20-second check** — after building, run this and confirm you see `Warmup complete`
within a second or two:

```bash
./bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-lru-lru-lru-lru-lru-1core-baseline \
    -warmup_instructions 20000 -simulation_instructions 20000 \
    -traces ../traces/trace1.gz | grep -E "Warmup complete|cumulative IPC"
```

If it prints nothing and pegs a core, your compiler is wrong. Stop and fix §1.

---

## 1. Getting GCC 7

`brew install gcc@7` no longer works (the formula was removed from Homebrew core), so on a
Mac use a container or a lab machine. Pick **one** of these.

### Option A — Docker, Ubuntu 18.04 (recommended on a Mac)

Ubuntu 18.04's default compiler *is* GCC 7, so there is nothing to pin. It also runs
natively on Apple Silicon (arm64) — ChampSim is architecture-independent, so you do **not**
need `--platform linux/amd64`, and you should avoid it (x86 emulation is several times
slower).

```bash
cd ~/Desktop/PA2

docker run -it --name pa2 \
  -v "$PWD":/work -w /work/cs683-pa2-daydreamers \
  ubuntu:18.04 bash

# --- inside the container ---
apt-get update
apt-get install -y build-essential g++-7 gcc-7 python3 python3-pip gzip
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-7 100
update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-7 100
gcc --version   # must say 7.x
g++ --version   # must say 7.x
```

Mounting `~/Desktop/PA2` (not just the repo) means the traces are visible at
`../traces/` exactly as the README assumes.

For plotting, either `pip3 install matplotlib` inside the container, or skip it there and
run `scripts/plot_task1.py` on your Mac afterwards — the plot script only reads the CSV.

To get back into the container later: `docker start -ai pa2`.

### Option B — a CSE lab machine / any Ubuntu 18.04–20.04 box

```bash
sudo apt-get update
sudo apt-get install -y g++-7 gcc-7
sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-7 0
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-7 0
sudo update-alternatives --config g++   # pick gcc-7 if several are installed
sudo update-alternatives --config gcc
g++ --version
```

This is the path `README.md` describes, including the `add-apt-repository
ppa:ubuntu-toolchain-r/test` line if `g++-7` is not in your default repos.

### Option C — pass the compiler to the build script

`build_champsim.sh` forwards a compiler to `make` only when it receives 19 arguments,
which is awkward, so the cleanest explicit form is to bypass the wrapper's default:

```bash
make CXX=g++-7 CC=g++-7
```

but then you must do the file copying yourself (see §2.3). Prefer A or B.

---

## 2. Build the three binaries

### 2.1 Confirm the repo is in a clean state

```bash
cd ~/Desktop/PA2/cs683-pa2-daydreamers
git status --short
```

You should see only `prefetcher/spp.l1d_pref`, `.gitignore`, `scripts/` and `docs/`.
I deleted the `bin/` and `obj/` directories so that **no binary built by the wrong
compiler can survive into your submission** — rebuild from scratch.

### 2.2 Build

```bash
./build_champsim.sh no        lru baseline
./build_champsim.sh ip_stride lru ipstride
./build_champsim.sh spp       lru spp
```

Expect three binaries in `bin/`:

```
hashed_perceptron-no-no-no-no-no-no-no-lru-...-1core-baseline
hashed_perceptron-no-ip_stride-no-no-no-no-no-lru-...-1core-ipstride
hashed_perceptron-no-spp-no-no-no-no-no-lru-...-1core-spp
```

`scripts/run_task1.sh` knows these exact names and will tell you if one is missing.

### 2.3 If you build by hand

`build_champsim.sh` works by copying the chosen implementation over the generic file:

```bash
cp prefetcher/spp.l1d_pref prefetcher/l1d_prefetcher.cc
make clean && make CXX=g++-7
mv bin/champsim bin/<your-name>
```

Note the consequence: `prefetcher/l1d_prefetcher.cc` is a **generated** file. Never edit
it — edit `prefetcher/spp.l1d_pref`, which is the template the PDF tells us to use.

### 2.4 Then run the 20-second check from §0

Do this for the **baseline** binary and for **spp**. Two seconds of checking here saves
hours.

---

## 3. Run the simulations (25M warmup + 25M simulation, as the PDF requires)

```bash
./scripts/run_task1.sh ../traces 3
```

* arg 1 — trace directory (default `../traces`)
* arg 2 — how many simulations to run at once (default 3)

It writes one log per run to **`results/task1/<config>_<trace>.txt`** — 9 logs
(3 configs × 3 traces). It **skips any run whose log already contains a ROI section**, so
it is safe to re-run after an interruption.

Notes:

* Pick arg 2 ≈ your physical core count. Each run is single-threaded plus a `gunzip`
  child, so 3 parallel runs use ~6 cores' worth at peak. Memory per run is modest
  (hundreds of MB).
* Expect **hours**, not minutes. Run it under `tmux`/`screen`, or with `nohup`:
  ```bash
  nohup ./scripts/run_task1.sh ../traces 3 > results/task1/driver.log 2>&1 &
  ```
* Watch progress: ChampSim prints a heartbeat every 10M instructions, so
  ```bash
  tail -f results/task1/spp_trace1.txt
  ```
  should show `heartbeat IPC` lines, then `Warmup complete`, then
  `Region of Interest Statistics`.
* A log is complete when `grep -c "Region of Interest" results/task1/*.txt` is 1 for all 9.

**Keep these logs.** They are the raw evidence behind every number in Summary.pdf, they
belong in the repo (`results/` is not gitignored; only `bin/`, `obj/` and `traces/` are),
and the PDF asks for "generated results" in the tarball.

---

## 4. Parse into a CSV

```bash
python3 scripts/parse_results.py results/task1 results/task1/task1.csv
```

This reads **only the Region-of-Interest half** of each log — ChampSim resets every cache
and prefetch counter at the ROI boundary (`src/main.cc:442`), so warm-up numbers are
meaningless — and emits `results/task1/task1.csv` plus a readable summary table:

```
trace    config          IPC  speedup   LdMPKI   cover%    acc%
```

It computes, per the PDF's definitions:

* `speedup` = IPC(config) / IPC(baseline)
* `l1d_coverage` = (baseline L1D load misses − config L1D load misses) / baseline L1D load misses
* `l1d_pf_accuracy` = `USEFUL / ISSUED`

It reports accuracy as the field ChampSim literally labels `ACCURACY`
(`pf_useful / pf_lower_level` — useful lines over lines *actually fetched*), which is what
the PDF means by "also present in stats"; the coarser `useful / issued` ratio is carried
alongside it. The reasoning is in `docs/TASK1_SPP.md` §7.1.

It also **refuses to produce results that fail its own checks** and exits non-zero if any
run did not simulate 25M+25M, if any prefetcher emitted a cross-page prefetch, or if the
baseline issued prefetches. If it prints `all consistency checks passed`, the numbers are
safe to put in the report.

Besides the CSV it writes `results/task1/task1_tables.md` — the §8 tables of the write-up,
already formatted, ready to paste.

---

## 5. Plots

```bash
python3 scripts/plot_task1.py results/task1/task1.csv results/task1
```

Produces the four figures the PDF shows examples of:

| file | content |
|---|---|
| `task1_speedup.png` | speedup vs no-prefetch baseline, geomean bar, 1.0 reference line |
| `task1_l1d_load_mpki.png` | L1D load MPKI, all three configs |
| `task1_accuracy.png` | prefetch accuracy, ip_stride vs SPP |
| `task1_coverage.png` | L1D load-miss coverage, ip_stride vs SPP |

Needs `matplotlib` (`pip3 install matplotlib`). Safe to run on your Mac even if the
simulations ran in Docker — it only reads the CSV.

---

## 6. Fill in the write-up

**This is already done** — `docs/TASK1_SPP.md` §8 carries the real GCC 7 numbers,
and `Summary.pdf` at the repo root is built from it. What follows is how to
*regenerate* it after Tasks 2 and 3 add their own results.

`scripts/parse_results.py` writes `results/task1/task1_tables.md`, which is §8.1–§8.6
already formatted — paste it over the corresponding block. The sections are:

* §8.1 IPC and speedup
* §8.2 L1D load MPKI
* §8.3 accuracy and coverage
* §8.4 **SPP internal behaviour** — this one is not in the CSV by default; read it off the
  tail of each `results/task1/spp_*.txt`:
  ```bash
  for f in results/task1/spp_*.txt; do echo "== $f"; sed -n '/SPP (L1D) final stats/,/====/p' $f; done
  ```
  It reports the uniform vs non-uniform prefetch split, mean windowed usefulness, how many
  windows were spent at each degree, IP-table hit rate, and pattern-table occupancy.
  **This table is what proves the dual classification and the throttle are actually
  working** rather than one path carrying everything — don't skip it.

Then export to `Summary.pdf` (e.g. `pandoc docs/TASK1_SPP.md -o Summary.pdf`, or paste
into your editor of choice and add the four PNGs).

---

## 7. Optional experiments that would strengthen the report

Each is a one-line edit to `prefetcher/spp.l1d_pref`, a rebuild, and one run.

| Question | Edit | Why it helps |
|---|---|---|
| Was degree 4 the right cap? | `MAX_DEGREE` → 2, 3, 6 and the mapping in the throttle block | Turns §7.2's argument into measured data |
| Does throttling earn its keep? | make all four branches assign the same constant (fixed degree) | Isolates the throttle's contribution; expect it to *lose* slightly on easy traces and win on hard ones |
| Is the IP table big enough at 25M? | `IP_TABLE_SETS` / `IP_TABLE_WAYS` | I chose 64×4 from a 1M-instruction sweep; confirm the knee is in the same place at 25M |
| Is the uniform threshold of 3 best in practice? | `UNIFORM_CONF_MAX` → 2 | §3.2 proves 3 is required for the PDF's example; measuring 2 shows what mis-classification costs |
| Should stores train it? | `if (type != LOAD && type != RFO) return;` | Tests the §2.3 choice directly |
| Is the throttle window right? | `ACC_WINDOW` → 256, 1024 | §7.1 picks 512 from a bias-vs-adaptivity argument; ≈130 updates per 25M run is the coarsest part of the design |

Also re-runnable any time, no simulation needed — the offline design check:

```bash
python3 scripts/verify_design.py
```

It re-proves, mechanically, that the uniform threshold of 3 never misclassifies
`(+1,+2,+2,+2,+3)^n`, that the 10-bit signature gives all five phases distinct
signatures, and that the lookahead chain reproduces the next four strides from every
phase. Good thing to be able to run in front of the instructor.

---

## 8. Commit, with a history that reads like work

The PDF warns that unclear or last-minute commits lose points, so commit in stages rather
than one dump:

```bash
cd ~/Desktop/PA2/cs683-pa2-daydreamers

git add .gitignore scripts/verify_design.py
git commit -m "Task 1: offline verification of SPP signature and threshold choices"

git add prefetcher/spp.l1d_pref
git commit -m "Task 1B: SPP L1D prefetcher - IP table, signature pattern table, page-confined lookahead, accuracy throttling"

git add scripts/run_task1.sh scripts/parse_results.py scripts/plot_task1.py
git commit -m "Task 1: experiment driver, log parser and plot scripts"

git add docs/TASK1_SPP.md docs/RUN_INSTRUCTIONS.md
git commit -m "Task 1: design rationale, storage breakdown, threshold and degree justification"

# after the runs finish
git add results/task1
git commit -m "Task 1: ChampSim results for baseline / ip_stride / SPP on all three traces (25M+25M, GCC 7)"
```

Make sure the repo is **private**, and that `traces/` is gitignored (it is).

Tarball for Moodle — note the exclusions:

```bash
cd ~/Desktop/PA2
tar --exclude='.git' --exclude='bin' --exclude='obj' --exclude='*.gz' \
    -czf daydreamers_<LDAP1>_<LDAP2>_pa2.tar.gz cs683-pa2-daydreamers
tar -tzf daydreamers_<LDAP1>_<LDAP2>_pa2.tar.gz | grep -i trace   # must print nothing
```

The last line is the check that matters — the PDF explicitly says no trace files.

---

## 9. Quick troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Spins at 100 % CPU, never prints `Warmup complete` | Not GCC 7 (§0) | Rebuild with GCC 7 |
| `TRACE FILE DOES NOT EXIST` then an assert | path is relative to the repo dir | use `../traces/trace1.gz`, or pass an absolute path as arg 1 to `run_task1.sh` |
| `[ERROR] missing binary for 'spp'` | not built, or renamed | re-run §2.2; names must match exactly |
| `ChampSim does not support traces other than gz or xz` | wrong extension | the supplied files are `.gz`, which is supported |
| `ACCURACY: nan` on ITLB/DTLB/L2C/LLC lines | those prefetchers are `no`, so the denominator is 0 | expected; ignore, read only the `L1D` lines |
| `parse_results.py` says "incomplete log (no ROI section)" | that run was killed early | delete the log and re-run; the driver skips completed ones |
| Rebuild seems to ignore your edit | you edited the generated `prefetcher/l1d_prefetcher.cc` | edit `prefetcher/spp.l1d_pref` instead (§2.3) |
