#!/usr/bin/env python3
"""
CS683 PA2 - Task 2a plots.

Produces the five plots the deliverable asks for, in the grouped-bar style the
PDF's examples use (one group per trace, plus an aggregate group on the right):

    results/task2a/task2a_ipc.png
    results/task2a/task2a_speedup.png
    results/task2a/task2a_l2c_load_mpki.png
    results/task2a/task2a_instr_load_mpki.png
    results/task2a/task2a_data_load_mpki.png

Reads results/task2a/task2a.csv, so run parse_task2a.py first.

The aggregate bar uses the geometric mean for speedup (it is a ratio) and the
arithmetic mean for IPC and the MPKIs (already per-1000-instructions, and every
trace ran the same 25M instructions).  The speedup chart draws a line at 1.0 so
a regression is impossible to miss.

usage:  python3 scripts/plot_task2a.py [RESULT_DIR]
"""
import csv, io, os, sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

RESDIR = sys.argv[1] if len(sys.argv) > 1 else 'results/task2a'
CSVP = os.path.join(RESDIR, 'task2a.csv')
if not os.path.exists(CSVP):
    sys.exit('missing %s -- run: python3 scripts/parse_task2a.py' % CSVP)

TRACES = ['trace1', 'trace2', 'trace3']
ORDER = [('lru_t2a', 'LRU (baseline)'),
         ('rrip',    'RRIP'),
         ('irrip',   'I-RRIP')]
COLOUR = {'lru_t2a': '#9e9e9e', 'rrip': '#4878a8', 'irrip': '#c44e52'}

rows = {}
with io.open(CSVP, encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        rows[(r['config'], r['trace'])] = r

have = [(c, lab) for c, lab in ORDER if any((c, t) in rows for t in TRACES)]
if not have:
    sys.exit('no usable rows in %s' % CSVP)


def geomean(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def chart(key, title, ylabel, fname, agg, baseline_at=None):
    labels = TRACES + [agg[0]]
    x = np.arange(len(labels))
    n = len(have)
    width = 0.8 / n

    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, (cfg, lab) in enumerate(have):
        vals = []
        for t in TRACES:
            vals.append(float(rows[(cfg, t)][key]) if (cfg, t) in rows else 0.0)
        present = [v for v in vals if v]
        vals.append(agg[1](present) if present else 0.0)
        pos = x - 0.4 + width * (i + 0.5)
        bars = ax.bar(pos, vals, width, label=lab, color=COLOUR.get(cfg), edgecolor='white')
        for b, v in zip(bars, vals):
            ax.annotate('%.3f' % v, (b.get_x() + b.get_width() / 2, v),
                        textcoords='offset points', xytext=(0, 2),
                        ha='center', fontsize=6.5)

    if baseline_at is not None:
        ax.axhline(baseline_at, color='black', lw=0.9, ls='--', zorder=0)
        ax.annotate('no change', (len(labels) - 0.45, baseline_at),
                    fontsize=7, va='bottom', ha='right')
        # a ratio chart is unreadable from 0; start just below the smallest bar
        allv = [float(rows[k][key]) for k in rows if key in rows[k] and rows[k][key] != '']
        if allv:
            ax.set_ylim(min(min(allv), baseline_at) * 0.985, max(allv) * 1.015)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis='y', alpha=0.25)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    p = os.path.join(RESDIR, fname)
    fig.savefig(p, dpi=160)
    plt.close(fig)
    print('wrote', p)


MEAN = ('arith. mean', lambda v: sum(v) / len(v))
GEO = ('geomean', geomean)

chart('ipc', 'Task 2a - IPC (25M warmup + 25M sim, no L1D prefetcher)',
      'IPC', 'task2a_ipc.png', MEAN)
chart('speedup', 'Task 2a - Speedup over LRU baseline (geometric mean)',
      'speedup', 'task2a_speedup.png', GEO, baseline_at=1.0)
chart('mpki_l2c_load', 'Task 2a - L2C load MPKI (lower is better)',
      'MPKI', 'task2a_l2c_load_mpki.png', MEAN)
chart('mpki_instr', 'Task 2a - L2 INSTRUCTION load MPKI (lower is better)',
      'MPKI', 'task2a_instr_load_mpki.png', MEAN)
chart('mpki_data', 'Task 2a - L2 DATA load MPKI (lower is better)',
      'MPKI', 'task2a_data_load_mpki.png', MEAN)
