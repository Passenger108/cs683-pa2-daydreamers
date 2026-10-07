#!/bin/bash
# ---------------------------------------------------------------------------
# CS683 PA2 - Task 2a experiment driver
#
#   3 configurations  x  3 traces  =  9 simulations
#   warmup_instructions = 25M, simulation_instructions = 25M, per the PDF.
#
#   The three configurations, and why all three are needed:
#
#     lru_t2a  no prefetcher + stock LRU at L2.
#              This is the speedup denominator.  It is also the SAME
#              configuration as Task 1's "baseline", deliberately: re-running
#              it after the update_replacement_state signature change lets us
#              check the logs are bit-identical to results/task1/baseline_*,
#              which proves the plumbing edit changed no behaviour.
#
#     rrip     no prefetcher + the SRRIP that ships in replacement/rrip.l2c_repl.
#              Without this we could only show "I-RRIP beats LRU", which would
#              not separate the benefit of RRIP from the benefit of being
#              instruction-conscious.  I-RRIP minus RRIP is the number that
#              actually answers Task 2a.
#
#     irrip    no prefetcher + our replacement/irrip.l2c_repl.
#
#   The L1D prefetcher is 'no' for all three on purpose: Task 2a is about the
#   replacement policy, so the prefetcher is held fixed. SPP rejoins in Task 3.
#
# BUILD FIRST (inside the GCC 7 container -- g++ must resolve to g++-7):
#     ./build_champsim.sh no lru   lru_t2a
#     ./build_champsim.sh no rrip  rrip
#     ./build_champsim.sh no irrip irrip
#
# usage:   ./scripts/run_task2a.sh  [TRACE_DIR]  [JOBS]
#          TRACE_DIR defaults to ../traces
#          JOBS      simulations to keep in flight at once (default 3)
# ---------------------------------------------------------------------------
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TRACE_DIR="${1:-../traces}"
JOBS="${2:-3}"

N_WARM=25000000
N_SIM=25000000

OUT="results/task2a"
mkdir -p "$OUT"

# build_champsim.sh bakes every module name into the binary name.  Only the
# L2C replacement slot changes across these three builds.
PRE="bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-"
POST="-lru-lru-lru-lru-1core-"

declare -A BIN
BIN[lru_t2a]="${PRE}lru${POST}lru_t2a"
BIN[rrip]="${PRE}rrip${POST}rrip"
BIN[irrip]="${PRE}irrip${POST}irrip"

declare -A BUILDCMD
BUILDCMD[lru_t2a]="./build_champsim.sh no lru lru_t2a"
BUILDCMD[rrip]="./build_champsim.sh no rrip rrip"
BUILDCMD[irrip]="./build_champsim.sh no irrip irrip"

TRACES="trace1 trace2 trace3"
CONFIGS="lru_t2a rrip irrip"

declare -A SRC
SRC[lru_t2a]="replacement/lru.l2c_repl"
SRC[rrip]="replacement/rrip.l2c_repl"
SRC[irrip]="replacement/irrip.l2c_repl"

# ---------------------------------------------------------------------------
# Three gates before any simulation runs.  All three exist because all three
# failed silently once:
#
#   1. TOOLCHAIN. The binary must be a Linux ELF, i.e. built inside the GCC 7
#      container.  A build run on the macOS host produces a Mach-O binary from
#      Apple clang, which completes happily and produces *different numbers* --
#      measured divergence of up to 3.8% in L2 instruction MPKI on trace2 for
#      an identical policy, which is the same order as the effects we are
#      trying to measure.
#   2. STALENESS. The binary must be newer than the policy source it was built
#      from.  Otherwise an old binary sitting at the expected path is run and
#      reported as if it were the current code.
#   3. COMPLETENESS, further down: a log only counts as done if it reached the
#      Region of Interest section.
# ---------------------------------------------------------------------------
missing=0
for c in $CONFIGS; do
    b="${BIN[$c]}"
    if [ ! -x "$b" ]; then
        echo "[ERROR] missing binary for '$c'"
        echo "        expected: $b"
        echo "        build it:  ${BUILDCMD[$c]}"
        missing=1; continue
    fi
    if ! file -b "$b" | grep -q '^ELF'; then
        echo "[ERROR] '$c' is not a Linux ELF binary:"
        echo "        $(file -b "$b")"
        echo "        You are building outside the GCC 7 container. Results from a"
        echo "        clang/macOS build are NOT comparable. Rebuild in the container:"
        echo "        ${BUILDCMD[$c]}"
        missing=1; continue
    fi
    # Stale if ANY build input is newer than the binary: its own policy source,
    # or anything under src/ or inc/.  Checking only the policy source would
    # miss a change to src/main.cc or src/cache.cc, which every policy depends
    # on, so the dependency set has to be the whole build.
    # build_champsim.sh rewrites inc/champsim.h with `sed -i.bak` at both the
    # start AND the end of every build (it sets NUM_CPUS, then restores it), so
    # champsim.h's mtime is always newer than the binary that was just linked
    # from it, and the .bak is pure build residue.  Both are excluded or this
    # check fires on every binary, always, and gets ignored -- which is worse
    # than not having it.  Cost: an edit to champsim.h itself (cache geometry)
    # is not caught here; parse_task2a.py's log-identity check covers that.
    newer=$(find "${SRC[$c]}" src inc -type f -newer "$b" \
                 ! -name '*.bak' ! -name 'champsim.h' 2>/dev/null | head -3)
    if [ -n "$newer" ]; then
        echo "[ERROR] '$c' binary is STALE -- these build inputs are newer than it:"
        echo "$newer" | sed 's/^/          /'
        echo "        binary: $b"
        echo "        rebuild: ${BUILDCMD[$c]}"
        missing=1
    fi
done
[ "$missing" -eq 0 ] || exit 1

# The exact "L2C I-RRIP config ..." line the current policy source will print.
# Used below so that changing a knob invalidates the old irrip logs instead of
# leaving them to be skipped as "complete".
EXPECT_CFG="$(python3 scripts/parse_task2a.py --print-expected-config 2>/dev/null)"
[ -n "$EXPECT_CFG" ] && echo "[info] current I-RRIP config: $EXPECT_CFG"

running=0
for t in $TRACES; do
    for c in $CONFIGS; do
        log="$OUT/${c}_${t}.txt"
        # Resume support, in two parts:
        #   1. a log is only done if it reached the ROI section, so a killed run
        #      is re-done rather than silently accepted;
        #   2. for irrip, it must ALSO carry the configuration the current
        #      source would print -- otherwise a knob change would leave a
        #      complete-looking log from the previous configuration in place.
        if [ -s "$log" ] && grep -q "Region of Interest" "$log"; then
            if [ "$c" = "irrip" ] && [ -n "$EXPECT_CFG" ] \
               && ! grep -qF "$EXPECT_CFG" "$log"; then
                echo "[redo] $log was produced by a DIFFERENT I-RRIP configuration"
            else
                echo "[skip] $log already complete"
                continue
            fi
        fi
        echo "[run ] $c on $t  ->  $log"
        "${BIN[$c]}" -warmup_instructions $N_WARM \
                     -simulation_instructions $N_SIM \
                     -traces "$TRACE_DIR/${t}.gz" > "$log" 2>&1 &
        running=$((running+1))
        if [ "$running" -ge "$JOBS" ]; then
            wait -n 2>/dev/null || wait
            running=$((running-1))
        fi
    done
done

wait
echo "[done] all Task-2a simulations finished; logs in $OUT"
echo
echo "next:  python3 scripts/parse_task2a.py"
echo "       python3 scripts/plot_task2a.py"
