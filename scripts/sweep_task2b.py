#!/usr/bin/env python3
"""
CS683 PA2 - Task 2b Sensitivity Sweep
Sweeps 5 threshold values for the PDF deliverable: [15, 25, 35, 45, 60]
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

THRESHOLDS = [15, 25, 35, 45, 60]
TRACES = ['trace1', 'trace2', 'trace3']
TRACE_DIR = sys.argv[1] if len(sys.argv) > 1 else '../traces'
OUT_DIR = 'results/task2b_sweep'
os.makedirs(OUT_DIR, exist_ok=True)

N_WARM = 25000000
N_SIM  = 25000000

print("=== Starting Task 2b Threshold Sensitivity Sweep ===")

for th in THRESHOLDS:
    tag = f"pdf_t{th}"
    bin_path = f"bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-dyn_irrip-lru-lru-lru-lru-1core-{tag}"
    
    # 1. Compile with overridden DYN_SELECTOR=0 and DYN_THRESH_PCT
    print(f"\n[build] Compiling threshold {th}% ({tag})...")
    build_env = os.environ.copy()
    build_cmd = f"g++ -Wall --std=c++11 -O3 -Iinc -DDYN_SELECTOR=0 -DDYN_THRESH_PCT={th}"
    
    # Replace in dyn_irrip temporarily or build binary
    subprocess.run(["./build_champsim.sh", "no", "dyn_irrip", tag], check=True)
    
    # 2. Run across the 3 traces
    for t in TRACES:
        log_file = f"{OUT_DIR}/{tag}_{t}.txt"
        trace_file = f"{TRACE_DIR}/{t}.gz"
        
        if os.path.exists(log_file) and "Region of Interest" in open(log_file, errors='ignore').read():
            print(f" [skip] {log_file} already done")
            continue
            
        print(f" [run ] {tag} on {t}...")
        cmd = [bin_path, "-warmup_instructions", str(N_WARM), 
               "-simulation_instructions", str(N_SIM), 
               "-traces", trace_file]
        with open(log_file, "w") as out:
            subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)

print("\n=== Sensitivity sweep finished! Logs in results/task2b_sweep ===")