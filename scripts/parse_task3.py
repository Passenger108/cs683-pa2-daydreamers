#!/usr/bin/env python3
"""
CS683 PA2 - Task 3 parser.  Combined SPP + dynamic I-RRIP vs the two standalones.

Reuses scripts/parse_results.parse_log so every metric is defined IDENTICALLY to
Task 1 (prefetch accuracy = pf_useful / pf_lower_level; coverage = reduction in
L1D load misses vs the no-prefetch baseline) -- no metric is redefined for Task 3.

    python3 scripts/parse_task3.py                      # table + results/task3/task3.csv
    python3 scripts/parse_task3.py --print-expected-config
"""
import csv, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_results import parse_log, geomean            # noqa: E402

TRACES = ['trace1', 'trace2', 'trace3']
# config tag : human label (order = print order)
CFG = [('lru_t3',        'LRU (baseline)'),
       ('spp_t3',        'SPP alone'),
       ('dyn_irrip_t3',  'dyn I-RRIP alone'),
       ('spp_dyn_irrip', 'SPP + dyn I-RRIP')]
OUT = 'results/task3'


# ---- reconstruct the exact DYN-IRRIP config line the source will print -------
def _resolve_pf_insert(expr, max_rrpv):
    """DYN_PF_INSERT may be `DYN_MAX_RRPV`, `DYN_MAX_RRPV-1`, or a literal int."""
    expr = expr.strip()
    expr = expr.replace('DYN_MAX_RRPV', str(max_rrpv))
    return int(eval(expr, {'__builtins__': {}}, {}))   # only ints + - here


def expected_dyn_config(src='replacement/dyn_irrip.l2c_repl'):
    t = open(src).read()
    h = open('inc/cache.h').read()

    def d(name, default=None):
        m = re.search(r'^#define DYN_%s (.*)$' % name, t, re.M)
        return m.group(1).strip() if m else default

    v = {k: int(d(k)) for k in ('MAX_RRPV', 'SELECTOR', 'THRESH_PCT', 'HYST_PCT',
                                'NUM_LEADERS', 'WINDOW', 'INSTR_WEIGHT')}
    aware = int(d('SPP_AWARE', '1'))
    pf = _resolve_pf_insert(d('PF_INSERT', 'DYN_MAX_RRPV'), v['MAX_RRPV'])
    sets = int(re.search(r'#define L2C_SET (\d+)', h).group(1))
    return ('MAX_RRPV %d | SELECTOR %d thresh %d hyst %d | LEADERS %d stride %d'
            ' | WINDOW %d | INSTR_WEIGHT %d | SPP_AWARE %d PF_INSERT %d') % (
        v['MAX_RRPV'], v['SELECTOR'], v['THRESH_PCT'], v['HYST_PCT'],
        v['NUM_LEADERS'], sets // v['NUM_LEADERS'], v['WINDOW'],
        v['INSTR_WEIGHT'], aware, pf)


if '--print-expected-config' in sys.argv:
    print(expected_dyn_config())
    sys.exit(0)


# ---- read logs, compute speedup + coverage against the LRU baseline ----------
def load(tag, t):
    p = os.path.join(OUT, '%s_%s.txt' % (tag, t))
    return parse_log(p) if os.path.exists(p) else None


R = {}
for tag, _ in CFG:
    for t in TRACES:
        R[(tag, t)] = load(tag, t)

missing = [(tag, t) for tag, _ in CFG for t in TRACES if R[(tag, t)] is None]
if missing:
    print('[warn] missing logs: ' + ', '.join('%s/%s' % m for m in missing))
    print('       build the four configs and run ./scripts/run_task3.sh first')

rows = {}
for tag, label in CFG:
    for t in TRACES:
        r = R[(tag, t)]
        if r is None:
            continue
        base = R[('lru_t3', t)]
        sp = (r['ipc'] / base['ipc']) if base and base.get('ipc') else None
        cov = None
        if base and base.get('l1d_load_miss'):
            cov = 100.0 * (base['l1d_load_miss'] - r['l1d_load_miss']) / base['l1d_load_miss']
        rows[(tag, t)] = dict(
            config=tag, label=label, trace=t,
            ipc=r.get('ipc'), speedup=sp,
            l1d_load_mpki=r.get('l1d_load_mpki'),
            l2c_load_mpki=r.get('l2c_load_mpki'),
            l2c_instr_load_mpki=r.get('l2c_instr_load_mpki'),
            l2c_data_load_mpki=r.get('l2c_data_load_mpki'),
            accuracy=r.get('l1d_accuracy'), coverage=cov)

# ---- CSV ----
os.makedirs(OUT, exist_ok=True)
cols = ['config', 'label', 'trace', 'ipc', 'speedup', 'l1d_load_mpki',
        'l2c_load_mpki', 'l2c_instr_load_mpki', 'l2c_data_load_mpki',
        'accuracy', 'coverage']
with open(os.path.join(OUT, 'task3.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for tag, _ in CFG:
        for t in TRACES:
            if (tag, t) in rows:
                w.writerow({k: rows[(tag, t)].get(k) for k in cols})
print('wrote %s/task3.csv' % OUT)


# ---- aggregates: geomean speedup, arithmetic-mean MPKI ----
def agg(tag, key, kind):
    xs = [rows[(tag, t)][key] for t in TRACES if (tag, t) in rows and rows[(tag, t)][key] is not None]
    if not xs:
        return None
    return geomean(xs) if kind == 'geo' else sum(xs) / len(xs)


def fmt(x, nd=4):
    return ('%.*f' % (nd, x)) if isinstance(x, float) else ('-' if x is None else str(x))

print()
hdr = ('%-18s %-7s %8s %8s %9s %9s %9s %9s %8s %8s' %
       ('config', 'trace', 'IPC', 'speedup', 'L1Dmpki', 'L2Cmpki',
        'L2instr', 'L2data', 'acc%', 'cov%'))
print(hdr); print('-' * len(hdr))
for tag, label in CFG:
    for t in TRACES:
        if (tag, t) not in rows:
            continue
        d = rows[(tag, t)]
        print('%-18s %-7s %8s %8s %9s %9s %9s %9s %8s %8s' % (
            tag, t, fmt(d['ipc'], 5), fmt(d['speedup']),
            fmt(d['l1d_load_mpki'], 4), fmt(d['l2c_load_mpki'], 4),
            fmt(d['l2c_instr_load_mpki'], 4), fmt(d['l2c_data_load_mpki'], 4),
            fmt(d['accuracy'], 2), fmt(d['coverage'], 2)))
    print('%-18s %-7s %8s %8s %9s %9s %9s %9s %8s %8s   <- aggregate' % (
        tag, 'ALL', '', fmt(agg(tag, 'speedup', 'geo')),
        fmt(agg(tag, 'l1d_load_mpki', 'mean'), 4), fmt(agg(tag, 'l2c_load_mpki', 'mean'), 4),
        fmt(agg(tag, 'l2c_instr_load_mpki', 'mean'), 4), fmt(agg(tag, 'l2c_data_load_mpki', 'mean'), 4),
        '', ''))

# ---- the Task-3 verdict, printed so it cannot be fudged ----
sp = {tag: agg(tag, 'speedup', 'geo') for tag, _ in CFG}
if all(sp[k] is not None for k in ('spp_dyn_irrip', 'spp_t3', 'dyn_irrip_t3')):
    print('\nTask 3 bar:  combined %.4f  vs  SPP-alone %.4f  vs  dynI-RRIP-alone %.4f' %
          (sp['spp_dyn_irrip'], sp['spp_t3'], sp['dyn_irrip_t3']))
    beats = sp['spp_dyn_irrip'] > sp['spp_t3'] and sp['spp_dyn_irrip'] > sp['dyn_irrip_t3']
    print('             combined beats BOTH standalones: %s' % ('YES' if beats else 'NO'))

# ---- Markdown tables for the summary/doc ----
with open(os.path.join(OUT, 'task3_tables.md'), 'w') as f:
    f.write('# Task 3 results (generated)\n\n')
    f.write('| config | geomean speedup | mean L1D MPKI | mean L2C MPKI | mean L2 instr | mean L2 data |\n')
    f.write('|---|---:|---:|---:|---:|---:|\n')
    for tag, label in CFG:
        f.write('| %s | %s | %s | %s | %s | %s |\n' % (
            label, fmt(agg(tag, 'speedup', 'geo')),
            fmt(agg(tag, 'l1d_load_mpki', 'mean'), 4), fmt(agg(tag, 'l2c_load_mpki', 'mean'), 4),
            fmt(agg(tag, 'l2c_instr_load_mpki', 'mean'), 4), fmt(agg(tag, 'l2c_data_load_mpki', 'mean'), 4)))
print('wrote %s/task3_tables.md' % OUT)
