#!/bin/bash
# ---------------------------------------------------------------------------
# CS683 PA2 - Task 2b experiment driver.  4 configurations x 3 traces.
#
#   lru_t2a    no prefetcher + stock LRU. The speedup denominator, shared with
#              Task 2a so the two tasks' numbers are directly comparable.
#   rrip       the supplied SRRIP. One of the two modes the duel switches
#              between, so it is also the "prioritisation permanently OFF" end
#              of the comparison.
#   irrip      Task 2a's static policy: prioritisation permanently ON. The
#              thing 2b has to beat, and the reason 2b exists -- it regresses
#              trace1.
#   dyn_irrip  the dynamic policy. Should recover trace1 (where static I-RRIP
#              loses) while keeping most of trace2's win. That is the whole
#              claim, and these four rows are what test it.
#
# Four configurations, not two, because "dynamic beats LRU" would prove almost
# nothing: the interesting comparisons are dyn vs irrip (did adapting help?)
# and dyn vs rrip (is it better than never prioritising?).
#
# BUILD FIRST, inside the GCC 7 container:
#     ./build_champsim.sh no lru       lru_t2a
#     ./build_champsim.sh no rrip      rrip
#     ./build_champsim.sh no irrip     irrip
#     ./build_champsim.sh no dyn_irrip dyn_irrip
#
# usage:  ./scripts/run_task2b.sh [TRACE_DIR] [JOBS]
# ---------------------------------------------------------------------------
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
TRACE_DIR="${1:-../traces}"; JOBS="${2:-3}"
N_WARM=25000000; N_SIM=25000000
OUT="results/task2b"; mkdir -p "$OUT"

PRE="bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-"
POST="-lru-lru-lru-lru-1core-"
declare -A BIN SRC BUILDCMD
for c in lru_t2a:lru rrip:rrip irrip:irrip dyn_irrip:dyn_irrip; do
    tag="${c%%:*}"; pol="${c##*:}"
    BIN[$tag]="${PRE}${pol}${POST}${tag}"
    SRC[$tag]="replacement/${pol}.l2c_repl"
    BUILDCMD[$tag]="./build_champsim.sh no ${pol} ${tag}"
done
CONFIGS="lru_t2a rrip irrip dyn_irrip"
TRACES="trace1 trace2 trace3"

# The same three gates as Task 2a, for the same reasons: each one failed
# silently once.  (1) a clang/macOS build completes happily and produces
# DIFFERENT simulated counters -- up to 3.82% on trace2 for an identical
# policy.  (2) a binary older than its policy source is stale, and a stale
# binary once got reported as a result.  (3) further down, a log only counts as
# complete if it reached the Region of Interest.
missing=0
for c in $CONFIGS; do
    b="${BIN[$c]}"
    if [ ! -x "$b" ]; then
        echo "[ERROR] missing binary for '$c'"; echo "        build: ${BUILDCMD[$c]}"; missing=1; continue
    fi
    if ! file -b "$b" | grep -q '^ELF'; then
        echo "[ERROR] '$c' is not a Linux ELF -- built outside the GCC 7 container:"
        echo "        $(file -b "$b")"; echo "        rebuild: ${BUILDCMD[$c]}"; missing=1; continue
    fi
    newer=$(find "${SRC[$c]}" src inc -type f -newer "$b" \
                 ! -name '*.bak' ! -name 'champsim.h' 2>/dev/null | head -3)
    if [ -n "$newer" ]; then
        echo "[ERROR] '$c' binary is STALE -- newer build inputs:"
        echo "$newer" | sed 's/^/          /'; echo "        rebuild: ${BUILDCMD[$c]}"; missing=1
    fi
done
[ "$missing" -eq 0 ] || exit 1

# The config line the current dyn_irrip source will print, so a knob change
# invalidates old logs instead of letting them be skipped as "complete".
EXPECT_DYN="$(python3 scripts/parse_task2b.py --print-expected-config 2>/dev/null)"
[ -n "$EXPECT_DYN" ] && echo "[info] current DYN-IRRIP config: $EXPECT_DYN"

running=0
for t in $TRACES; do
  for c in $CONFIGS; do
    log="$OUT/${c}_${t}.txt"
    if [ -s "$log" ] && grep -q "Region of Interest" "$log"; then
        if [ "$c" = "dyn_irrip" ] && [ -n "$EXPECT_DYN" ] && ! grep -qF "$EXPECT_DYN" "$log"; then
            echo "[redo] $log came from a DIFFERENT dyn_irrip configuration"
        elif [ "${BIN[$c]}" -nt "$log" ]; then
            # The binary was rebuilt after this log was written, so the log is
            # stale even if the config line is unchanged (e.g. a code fix that
            # adds a counter but touches no knob).  Redo rather than skip.
            echo "[redo] $log older than the rebuilt $c binary"
        else
            echo "[skip] $log already complete"; continue
        fi
    fi
    echo "[run ] $c on $t"
    "${BIN[$c]}" -warmup_instructions $N_WARM -simulation_instructions $N_SIM \
                 -traces "$TRACE_DIR/${t}.gz" > "$log" 2>&1 &
    running=$((running+1))
    if [ "$running" -ge "$JOBS" ]; then wait -n 2>/dev/null || wait; running=$((running-1)); fi
  done
done
wait
echo "[done] logs in $OUT"
echo "next:  python3 scripts/parse_task2b.py && python3 scripts/plot_task2b.py"
