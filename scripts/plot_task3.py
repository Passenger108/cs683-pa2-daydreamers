#!/usr/bin/env python3
"""
CS683 PA2 - Task 3 plots.  Reads results/task3/task3.csv (written by
parse_task3.py) and emits one grouped-bar PNG per deliverable metric:
IPC, speedup, L1D/L2C/L2-instr/L2-data load MPKI, prefetch accuracy, coverage.

    python3 scripts/plot_task3.py
"""
import csv, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = 'results/task3'
TRACES = ['trace1', 'trace2', 'trace3']
ORDER = ['lru_t3', 'spp_t3', 'dyn_irrip_t3', 'spp_dyn_irrip']
LABEL = {'lru_t3': 'LRU', 'spp_t3': 'SPP', 'dyn_irrip_t3': 'dynI-RRIP',
         'spp_dyn_irrip': 'SPP+dynI-RRIP'}

rows = {}
with open(os.path.join(OUT, 'task3.csv')) as f:
    for r in csv.DictReader(f):
        rows[(r['config'], r['trace'])] = r


def val(cfg, t, key):
    r = rows.get((cfg, t))
    if not r or r.get(key) in (None, '', 'None'):
        return None
    try:
        return float(r[key])
    except ValueError:
        return None


def bar(key, title, ylabel, fname, pooled=False):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    n = len(ORDER); w = 0.8 / n
    for i, cfg in enumerate(ORDER):
        xs = [j + i * w for j in range(len(TRACES))]
        ys = [val(cfg, t, key) or 0 for t in TRACES]
        ax.bar(xs, ys, w, label=LABEL[cfg])
    ax.set_xticks([j + 0.4 - w / 2 for j in range(len(TRACES))])
    ax.set_xticklabels(TRACES)
    ax.set_ylabel(ylabel); ax.set_title(title)
    ax.legend(fontsize=8); ax.grid(axis='y', alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=110)
    plt.close(fig); print('wrote %s/%s' % (OUT, fname))


bar('ipc', 'Task 3 - IPC', 'IPC', 'task3_ipc.png')
bar('speedup', 'Task 3 - speedup vs LRU', 'speedup', 'task3_speedup.png')
bar('l1d_load_mpki', 'Task 3 - L1D load MPKI', 'MPKI', 'task3_l1d_load_mpki.png')
bar('l2c_load_mpki', 'Task 3 - L2C load MPKI', 'MPKI', 'task3_l2c_load_mpki.png')
bar('l2c_instr_load_mpki', 'Task 3 - L2 instruction load MPKI', 'MPKI', 'task3_l2c_instr_load_mpki.png')
bar('l2c_data_load_mpki', 'Task 3 - L2 data load MPKI', 'MPKI', 'task3_l2c_data_load_mpki.png')
bar('accuracy', 'Task 3 - L1D prefetch accuracy', 'accuracy (%)', 'task3_accuracy.png')
bar('coverage', 'Task 3 - L1D load-miss coverage', 'coverage (%)', 'task3_coverage.png')
