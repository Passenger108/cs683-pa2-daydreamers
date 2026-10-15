#!/usr/bin/env python3
"""
CS683 PA2 - Task 2b Log Parser
Extracts IPC, speedup, L2C Load MPKI, L2 Instr MPKI, and L2 Data MPKI.
"""
import glob, os, re, sys

def parse_log(path):
    res = {'ipc': None, 'l2c_mpki': None, 'instr_mpki': None, 'data_mpki': None}
    if not os.path.exists(path):
        return res
    content = open(path, errors='ignore').read()
    
    m_ipc = re.search(r'CPU 0 cumulative IPC:\s+([0-9.]+)', content)
    if m_ipc: res['ipc'] = float(m_ipc.group(1))
    
    m_l2c = re.search(r'LLC TOTAL\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+\d+', content)
    m_load = re.search(r'LLC LOAD\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+(\d+)', content)
    m_instr = re.search(r'LLC INSTRUCTION LOAD MPKI:\s+([0-9.]+)', content)
    m_data = re.search(r'LLC DATA LOAD MPKI:\s+([0-9.]+)', content)
    m_total = re.search(r'LLC LOAD MPKI:\s+([0-9.]+)', content)

    if m_total: res['l2c_mpki'] = float(m_total.group(1))
    if m_instr: res['instr_mpki'] = float(m_instr.group(1))
    if m_data: res['data_mpki'] = float(m_data.group(1))
    return res

if __name__ == '__main__':
    log_dir = sys.argv[1] if len(sys.argv) > 1 else 'results/task2b'
    print(f"{'Config':<15} {'Trace':<10} {'IPC':<10} {'L2C MPKI':<12} {'Instr MPKI':<12} {'Data MPKI':<12}")
    print("-" * 75)
    for f in sorted(glob.glob(f"{log_dir}/*.txt")):
        base = os.path.basename(f).replace('.txt', '')
        parts = base.rsplit('_', 1)
        if len(parts) == 2:
            cfg, tr = parts
            data = parse_log(f)
            if data['ipc']:
                print(f"{cfg:<15} {tr:<10} {data['ipc']:<10.4f} {str(data['l2c_mpki']):<12} {str(data['instr_mpki']):<12} {str(data['data_mpki']):<12}")