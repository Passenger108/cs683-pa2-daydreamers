#!/bin/bash
# ---------------------------------------------------------------------------
# CS683 PA2 - Task 2b Experiment Driver (4 configurations x 3 traces)
# ---------------------------------------------------------------------------
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
TRACE_DIR="${1:-../traces}"
JOBS="${2:-3}"
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

# Verify binaries exist
missing=0
for c in $CONFIGS; do
    b="${BIN[$c]}"
    if [ ! -x "$b" ]; then
        echo "[ERROR] Missing binary for '$c'. Build with: ${BUILDCMD[$c]}"
        missing=1
    fi
done
[ "$missing" -eq 0 ] || exit 1

running=0
for t in $TRACES; do
  for c in $CONFIGS; do
    log="$OUT/${c}_${t}.txt"
    if [ -s "$log" ] && grep -q "Region of Interest" "$log"; then
        echo "[skip] $log already completed"
        continue
    fi
    echo "[run ] $c on $t"
    "${BIN[$c]}" -warmup_instructions $N_WARM -simulation_instructions $N_SIM \
                 -traces "$TRACE_DIR/${t}.gz" > "$log" 2>&1 &
    running=$((running+1))
    if [ "$running" -ge "$JOBS" ]; then
        wait -n 2>/dev/null || wait
        running=$((running-1))
    fi
  done
done
wait
echo "[done] simulations finished, logs stored in $OUT"