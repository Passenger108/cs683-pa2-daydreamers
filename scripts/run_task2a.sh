#!/bin/bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TRACE_DIR="${1:-../traces}"
JOBS="${2:-3}"

N_WARM=25000000
N_SIM=25000000

OUT="results/task2a"
mkdir -p "$OUT"

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

EXPECT_CFG="$(python3 scripts/parse_task2a.py --print-expected-config 2>/dev/null)"
[ -n "$EXPECT_CFG" ] && echo "[info] current I-RRIP config: $EXPECT_CFG"

running=0
for t in $TRACES; do
    for c in $CONFIGS; do
        log="$OUT/${c}_${t}.txt"
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
