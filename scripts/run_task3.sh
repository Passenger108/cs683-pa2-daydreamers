#!/bin/bash
# ---------------------------------------------------------------------------
# CS683 PA2 - Task 3 experiment driver.  4 configurations x 3 traces.
#
#   lru_t3         no prefetcher + stock LRU.  The speedup denominator, and the
#                  same baseline Tasks 1 and 2 used, so every task's numbers are
#                  directly comparable.
#   spp_t3         SPP + LRU.  STANDALONE SPP -- one of the two things Task 3
#                  must beat.  Identical config to Task 1's `spp` run.
#   dyn_irrip_t3   no prefetcher + dynamic I-RRIP.  STANDALONE dynamic I-RRIP --
#                  the other thing Task 3 must beat.  Because the Task 3 edit to
#                  dyn_irrip.l2c_repl only fires on PREFETCH fills and this build
#                  has no prefetcher, this MUST reproduce Task 2b's dyn_irrip
#                  logs bit-for-bit (verify_task3.py checks it) -- that is the
#                  proof the edit is inert without a prefetcher.
#   spp_dyn_irrip  SPP + dynamic I-RRIP.  THE COMBINED DESIGN.  The whole claim
#                  is that this one row beats BOTH standalones above in IPC.
#
# The two standalones are the honest bar: "combined beats LRU" proves nothing,
# since both standalones already beat LRU.  The comparison that matters is
# combined vs spp_t3 (did the replacement policy add anything on top of the
# prefetcher?) and combined vs dyn_irrip_t3 (did the prefetcher add anything on
# top of the policy?).
#
# BUILD FIRST, inside the GCC 7 container:
#     ./build_champsim.sh no  lru       lru_t3
#     ./build_champsim.sh spp lru       spp_t3
#     ./build_champsim.sh no  dyn_irrip dyn_irrip_t3
#     ./build_champsim.sh spp dyn_irrip spp_dyn_irrip
#
# usage:  ./scripts/run_task3.sh [TRACE_DIR] [JOBS]
# ---------------------------------------------------------------------------
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
TRACE_DIR="${1:-../traces}"; JOBS="${2:-3}"
N_WARM=25000000; N_SIM=25000000
OUT="results/task3"; mkdir -p "$OUT"

# config : L1D_prefetcher : L2C_replacement
declare -A BIN SRC BUILDCMD
for c in lru_t3:no:lru spp_t3:spp:lru dyn_irrip_t3:no:dyn_irrip spp_dyn_irrip:spp:dyn_irrip; do
    tag="${c%%:*}"; rest="${c#*:}"; pf="${rest%%:*}"; repl="${rest##*:}"
    BIN[$tag]="bin/hashed_perceptron-no-${pf}-no-no-no-no-no-lru-lru-lru-${repl}-lru-lru-lru-lru-1core-${tag}"
    SRC[$tag]="replacement/${repl}.l2c_repl"
    BUILDCMD[$tag]="./build_champsim.sh ${pf} ${repl} ${tag}"
done
CONFIGS="lru_t3 spp_t3 dyn_irrip_t3 spp_dyn_irrip"
TRACES="trace1 trace2 trace3"

# Same three gates as Tasks 2a/2b, each of which caught a real silent failure:
# (1) a clang/macOS build runs but produces DIFFERENT simulated counters; reject
# anything that is not a Linux ELF.  (2) a binary older than its policy source is
# stale.  (3) a log counts as complete only if it reached the Region of Interest.
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

# The config line the current dyn_irrip source prints, so a knob change (e.g. a
# different DYN_PF_INSERT) invalidates old combined/standalone logs rather than
# letting them be skipped as "complete".
EXPECT_DYN="$(python3 scripts/parse_task3.py --print-expected-config 2>/dev/null)"
[ -n "$EXPECT_DYN" ] && echo "[info] current DYN-IRRIP config: $EXPECT_DYN"

running=0
for t in $TRACES; do
  for c in $CONFIGS; do
    log="$OUT/${c}_${t}.txt"
    if [ -s "$log" ] && grep -q "Region of Interest" "$log"; then
        if { [ "$c" = "dyn_irrip_t3" ] || [ "$c" = "spp_dyn_irrip" ]; } \
             && [ -n "$EXPECT_DYN" ] && ! grep -qF "$EXPECT_DYN" "$log"; then
            echo "[redo] $log came from a DIFFERENT dyn_irrip configuration"
        elif [ "${BIN[$c]}" -nt "$log" ]; then
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
echo "next:  python3 scripts/parse_task3.py && python3 scripts/plot_task3.py"
