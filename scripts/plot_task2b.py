#!/usr/bin/env python3
"""
CS683 PA2 - Task 2b plots.

    task2b_ipc.png              IPC
    task2b_speedup.png          speedup vs LRU (geomean aggregate)
    task2b_l2c_load_mpki.png    L2C load MPKI
    task2b_instr_load_mpki.png  L2 instruction load MPKI
    task2b_data_load_mpki.png   L2 data load MPKI
    task2b_mode.png             what the duel decided, per trace

The first five are the deliverable. The sixth is the one that explains the
other five: if the dynamic policy sits near 0 % prioritising on the trace where
static I-RRIP lost and near 100 % where it won, the selector is reading the
right signal. No MPKI chart can show that.

usage:  python3 scripts/plot_task2b.py [RESULT_DIR]
"""
import csv, io, os, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

RESDIR = sys.argv[1] if len(sys.argv) > 1 else 'results/task2b'
CSVP = os.path.join(RESDIR, 'task2b.csv')
if not os.path.exists(CSVP):
    sys.exit('missing %s -- run: python3 scripts/parse_task2b.py' % CSVP)

TRACES = ['trace1', 'trace2', 'trace3']
ORDER = [('lru_t2a', 'LRU'), ('rrip', 'RRIP'),
         ('irrip', 'I-RRIP static'), ('dyn_irrip', 'Dynamic I-RRIP')]
COLOUR = {'lru_t2a': '#9e9e9e', 'rrip': '#4878a8',
          'irrip': '#c44e52', 'dyn_irrip': '#55a868'}

rows = {}
with io.open(CSVP, encoding='utf-8') as fh:
    for r in csv.DictReader(fh):
        rows[(r['config'], r['trace'])] = r
have = [(c, l) for c, l in ORDER if any((c, t) in rows for t in TRACES)]
if not have:
    sys.exit('no usable rows in %s' % CSVP)


def geo(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def chart(key, title, ylabel, fname, agg, baseline_at=None):
    labels = TRACES + [agg[0]]
    x = np.arange(len(labels))
    width = 0.8 / len(have)
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    for i, (cfg, lab) in enumerate(have):
        vals = [float(rows[(cfg, t)][key]) if (cfg, t) in rows else 0.0 for t in TRACES]
        present = [v for v in vals if v]
        vals.append(agg[1](present) if present else 0.0)
        bars = ax.bar(x - 0.4 + width * (i + 0.5), vals, width, label=lab,
                      color=COLOUR.get(cfg), edgecolor='white')
        for b, v in zip(bars, vals):
            ax.annotate('%.3f' % v, (b.get_x() + b.get_width() / 2, v),
                        textcoords='offset points', xytext=(0, 2),
                        ha='center', fontsize=6)
    if baseline_at is not None:
        ax.axhline(baseline_at, color='black', lw=0.9, ls='--', zorder=0)
        allv = [float(rows[k][key]) for k in rows if rows[k].get(key)]
        if allv:
            ax.set_ylim(min(min(allv), baseline_at) * 0.985, max(allv) * 1.015)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel); ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis='y', alpha=0.25); ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    p = os.path.join(RESDIR, fname); fig.savefig(p, dpi=160); plt.close(fig)
    print('wrote', p)


MEAN = ('mean', lambda v: sum(v) / len(v))
GEO = ('geomean', geo)
chart('ipc', 'Task 2b - IPC (25M+25M, no L1D prefetcher)', 'IPC', 'task2b_ipc.png', MEAN)
chart('speedup', 'Task 2b - Speedup over LRU (geometric mean)', 'speedup',
      'task2b_speedup.png', GEO, baseline_at=1.0)
chart('mpki_l2c', 'Task 2b - L2C load MPKI (lower is better)', 'MPKI',
      'task2b_l2c_load_mpki.png', MEAN)
chart('mpki_instr', 'Task 2b - L2 INSTRUCTION load MPKI (lower is better)', 'MPKI',
      'task2b_instr_load_mpki.png', MEAN)
chart('mpki_data', 'Task 2b - L2 DATA load MPKI (lower is better)', 'MPKI',
      'task2b_data_load_mpki.png', MEAN)

# --- the mode chart: what the selector decided, against what it should have --
if any(('dyn_irrip', t) in rows for t in TRACES):
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    pct = [float(rows[('dyn_irrip', t)]['pct_irrip']) if ('dyn_irrip', t) in rows else 0.0
           for t in TRACES]
    # What static I-RRIP did to each trace's total MPKI: negative = it helped,
    # so the selector "should" have prioritised there.
    helped = []
    for t in TRACES:
        if ('irrip', t) in rows and ('lru_t2a', t) in rows:
            a = float(rows[('irrip', t)]['mpki_l2c']); b = float(rows[('lru_t2a', t)]['mpki_l2c'])
            helped.append(100.0 * (b - a) / b)
        else:
            helped.append(0.0)
    x = np.arange(len(TRACES))
    ax.bar(x - 0.2, pct, 0.4, label='% of windows prioritising (actual)', color='#55a868')
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, helped, 0.4, label='static I-RRIP gain in L2C MPKI (%)', color='#c44e52')
    ax2.axhline(0, color='black', lw=0.9)
    for i, v in enumerate(pct):
        ax.annotate('%.1f%%' % v, (i - 0.2, v), textcoords='offset points',
                    xytext=(0, 2), ha='center', fontsize=7)
    for i, v in enumerate(helped):
        ax2.annotate('%+.1f%%' % v, (i + 0.2, v), textcoords='offset points',
                     xytext=(0, 2 if v >= 0 else -9), ha='center', fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels(TRACES)
    ax.set_ylabel('% of decision windows in I-RRIP mode'); ax.set_ylim(0, 105)
    ax2.set_ylabel('static I-RRIP gain, L2C MPKI (%)')
    ax.set_title('Task 2b - did the selector prioritise where prioritising pays?')
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc='upper left')
    ax.grid(axis='y', alpha=0.25); ax.set_axisbelow(True)
    fig.tight_layout()
    p = os.path.join(RESDIR, 'task2b_mode.png'); fig.savefig(p, dpi=160); plt.close(fig)
    print('wrote', p)
