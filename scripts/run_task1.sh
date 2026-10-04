#!/bin/bash
# ---------------------------------------------------------------------------
# CS683 PA2 - Task 1 experiment driver
#
#   3 configurations  x  3 traces  =  9 simulations
#   every run uses warmup_instructions = 25M, simulation_instructions = 25M
#   exactly as the assignment PDF requires.
#
# usage:   ./scripts/run_task1.sh  [TRACE_DIR]  [JOBS]
#          TRACE_DIR defaults to ../traces
#          JOBS      how many simulations to keep running at once (default 3)
# ---------------------------------------------------------------------------
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TRACE_DIR="${1:-../traces}"
JOBS="${2:-3}"

N_WARM=25000000
N_SIM=25000000

OUT="results/task1"
mkdir -p "$OUT"

SUFFIX="no-no-no-no-no-lru-lru-lru-lru-lru-lru-lru-lru-1core"

declare -A BIN
BIN[baseline]="bin/hashed_perceptron-no-no-${SUFFIX}-baseline"
BIN[ipstride]="bin/hashed_perceptron-no-ip_stride-${SUFFIX}-ipstride"
BIN[spp]="bin/hashed_perceptron-no-spp-${SUFFIX}-spp"

TRACES="trace1 trace2 trace3"
CONFIGS="baseline ipstride spp"

for c in $CONFIGS; do
    if [ ! -x "${BIN[$c]}" ]; then
        echo "[ERROR] missing binary for '$c': ${BIN[$c]}"
        echo "        build it first, e.g.:"
        echo "        ./build_champsim.sh no lru baseline"
        echo "        ./build_champsim.sh ip_stride lru ipstride"
        echo "        ./build_champsim.sh spp lru spp"
        exit 1
    fi
done

running=0
for t in $TRACES; do
    for c in $CONFIGS; do
        log="$OUT/${c}_${t}.txt"
        if [ -s "$log" ] && grep -q "Region of Interest" "$log"; then
            echo "[skip] $log already complete"
            continue
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
echo "[done] all Task-1 simulations finished; logs in $OUT"
