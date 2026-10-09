#!/usr/bin/env python3
"""
CS683 PA2 - Task 2b results parser.

    results/task2b/task2b.csv        one row per (config, trace)
    results/task2b/task2b_tables.md  the tables the PDF asks for

Deliverable, verbatim: "Report the IPC, speedup, and Load MPKI of L2C, L2
Instruction, and L2 Data in tabular form, and plot them." Plus, for 2b, the
dynamic behaviour itself -- how much of the run was spent prioritising, and how
often the mode flipped. A selector that flips thousands of times is thrashing,
not adapting, and that distinction is invisible in an MPKI table.

Aggregation: GEOMETRIC mean for speedup (it is a ratio), ARITHMETIC mean for
the MPKIs (already per-1000-instructions, and every trace ran exactly 25M).

    python3 scripts/parse_task2b.py [RESULT_DIR]
    python3 scripts/parse_task2b.py --print-expected-config
"""
import csv, io, os, re, sys

RESDIR = 'results/task2b'
TRACES = ['trace1', 'trace2', 'trace3']
CONFIGS = [('lru_t2a', 'LRU (baseline)'), ('rrip', 'RRIP'),
           ('irrip', 'I-RRIP static (2a)'), ('dyn_irrip', 'Dynamic I-RRIP (2b)')]

DYN_KNOBS = ('MAX_RRPV', 'SELECTOR', 'THRESH_PCT', 'HYST_PCT',
             'NUM_LEADERS', 'WINDOW', 'INSTR_WEIGHT')


def expected_dyn_config(src='replacement/dyn_irrip.l2c_repl'):
    """Rebuild the config line dyn_irrip.l2c_repl will print, from its #defines.

    This is the identity gate. A log counts as a measurement of the CURRENT
    policy only if it contains exactly this string. It exists because during
    Task 2a a stale binary -- built from an entirely different I-RRIP whose
    source was gone -- was run and reported as a result. An mtime test can be
    fooled by `touch`; this cannot, because the binary emits the string itself.
    """
    if not os.path.exists(src):
        return None
    t = io.open(src, encoding='utf-8').read()
    v = {}
    for k in DYN_KNOBS:
        m = re.search(r'^#define DYN_%s (.*)$' % k, t, re.M)
        if not m:
            return None
        v[k] = int(m.group(1).strip())
    h = io.open('inc/cache.h', encoding='utf-8').read()
    sets = int(re.search(r'#define L2C_SET (\d+)', h).group(1))
    return ('MAX_RRPV %d | SELECTOR %d thresh %d hyst %d | LEADERS %d stride %d'
            ' | WINDOW %d | INSTR_WEIGHT %d') % (
        v['MAX_RRPV'], v['SELECTOR'], v['THRESH_PCT'], v['HYST_PCT'],
        v['NUM_LEADERS'], sets // v['NUM_LEADERS'], v['WINDOW'], v['INSTR_WEIGHT'])


EXPECTED = expected_dyn_config()
if '--print-expected-config' in sys.argv:
    print(EXPECTED or '')
    sys.exit(0)
if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
    RESDIR = sys.argv[1]


def parse(path):
    t = io.open(path, encoding='utf-8', errors='replace').read()
    roi = t.find('Region of Interest Statistics')
    if roi < 0:
        raise ValueError('%s: no Region of Interest section (run incomplete)' % path)
    tl = t[roi:]

    def g(pat, c=float, where=None, d=None):
        m = re.search(pat, tl if where is None else where, re.M)
        return c(m.group(1)) if m else d

    d = dict(
        ipc=g(r'CPU 0 cumulative IPC:\s*([\d.]+)'),
        instrs=g(r'CPU 0 cumulative IPC:\s*[\d.]+\s*instructions:\s*(\d+)', int),
        miss=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*\d+\s+MISS:\s*(\d+)', int),
        acc=g(r'^L2C LOAD\s+ACCESS:\s*(\d+)', int),
        hit=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*(\d+)', int),
        mpki_instr=g(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)'),
        mpki_data=g(r'^L2C DATA LOAD MPKI:\s*([\d.]+)'),
        dei=g(r'^L2C Data Evicting Instructions\s+(\d+)', int, None, 0),
        iei=g(r'^L2C Instructions Evicting Instructions\s+(\d+)', int, None, 0),
        tei=g(r'^L2C Translations Evicting Instructions\s+(\d+)', int, None, 0),
        # dynamic-policy specifics
        windows=g(r'DYN MODE windows (\d+)', int, t, 0),
        win_irrip=g(r'DYN MODE windows \d+ in_irrip (\d+)', int, t, 0),
        pct_irrip=g(r'pct_irrip ([\d.]+)', float, t, 0.0),
        switches=g(r'switches (\d+)', int, t, 0),
        psel=g(r'DYN PSEL final (\d+)', int, t, 0),
        sacrificed=g(r'sacrificed_pct ([\d.]+)', float, t, 0.0),
        dyn_bytes=g(r'DYN STORAGE .*total_bytes (\d+)', int, t, 0),
        irrip_bytes=g(r'IRRIP STORAGE .*total_bytes (\d+)', int, t, 0),
        dyn_cfg=g(r'^L2C DYN-IRRIP config\s+(.*)$', str, t, ''))
    d['mpki_l2c'] = d['miss'] * 1000.0 / d['instrs']
    d['victims_i'] = d['dei'] + d['iei'] + d['tei']
    d['storage'] = d['dyn_bytes'] or d['irrip_bytes']

    if os.path.basename(path).startswith('dyn_irrip_'):
        if not d['dyn_cfg']:
            raise ValueError('%s has no "DYN-IRRIP config" line -- not produced by '
                             'the current dyn_irrip.l2c_repl. Rebuild and re-run.' % path)
        if EXPECTED and d['dyn_cfg'] != EXPECTED:
            raise ValueError('%s was built from different knobs than the source:\n'
                             '      log:    %s\n      source: %s'
                             % (path, d['dyn_cfg'], EXPECTED))
    return d


def mean(xs):
    return sum(xs) / float(len(xs))


def geo(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


data, missing = {}, []
for cfg, _ in CONFIGS:
    for tr in TRACES:
        p = os.path.join(RESDIR, '%s_%s.txt' % (cfg, tr))
        if not os.path.exists(p):
            missing.append(p); continue
        try:
            data[(cfg, tr)] = parse(p)
        except Exception as e:
            missing.append('%s  (%s)' % (p, e))

if missing:
    print('MISSING OR INCOMPLETE:')
    for m in missing:
        print('   ', m)
    print('\nRun ./scripts/run_task2b.sh first.')
    if not data:
        sys.exit(1)
    print('(continuing with what is present)\n')

BASE = CONFIGS[0][0]
for (cfg, tr), d in data.items():
    b = data.get((BASE, tr))
    d['speedup'] = d['ipc'] / b['ipc'] if b else float('nan')

have = [c for c, _ in CONFIGS if any((c, t) in data for t in TRACES)]
label = dict(CONFIGS)

os.makedirs(RESDIR, exist_ok=True)
cols = ['config', 'trace', 'ipc', 'speedup', 'mpki_l2c', 'mpki_instr', 'mpki_data',
        'acc', 'hit', 'miss', 'victims_i', 'dei', 'iei', 'tei', 'instrs',
        'windows', 'win_irrip', 'pct_irrip', 'switches', 'psel', 'sacrificed',
        'storage', 'dyn_cfg']
with io.open(os.path.join(RESDIR, 'task2b.csv'), 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh); w.writerow(cols)
    for cfg, _ in CONFIGS:
        for tr in TRACES:
            d = data.get((cfg, tr))
            if d:
                w.writerow([cfg, tr] + [d.get(c, '') for c in cols[2:]])
print('wrote', os.path.join(RESDIR, 'task2b.csv'))

O = []
A = O.append
A('# Task 2b - Dynamic I-RRIP: results\n')
A('25M warmup + 25M simulation, single core, no L1D prefetcher, GCC 7 `-O3`.')
A('Speedup is against **LRU (baseline)**. Geometric mean for speedup (a ratio),')
A('arithmetic mean for the MPKIs.\n')
if EXPECTED:
    A('Dynamic policy configuration, read back from the runs\' own logs:\n')
    A('```\n%s\n```\n' % EXPECTED)


def table(title, note, key, fmt, agg):
    A('### %s\n' % title)
    if note:
        A(note + '\n')
    A('| policy | ' + ' | '.join(TRACES) + ' | ' + agg[0] + ' |')
    A('|---|' + '---|' * (len(TRACES) + 1))
    for cfg in have:
        vals = [data[(cfg, t)][key] for t in TRACES if (cfg, t) in data]
        row = ' | '.join(fmt % data[(cfg, t)][key] if (cfg, t) in data else '-' for t in TRACES)
        A('| %s | %s | **%s** |' % (label[cfg], row, fmt % agg[1](vals)))
    A('')


MEAN = ('mean', mean)
GEO = ('geomean', geo)
table('IPC', '', 'ipc', '%.5f', ('mean', mean))
table('Speedup over LRU', 'Geometric mean, because speedup is a ratio.', 'speedup', '%.4f', GEO)
table('L2C load MPKI', 'All L2 load misses. Lower is better.', 'mpki_l2c', '%.4f', MEAN)
table('L2 INSTRUCTION load MPKI', '**The metric Task 2a was asked to reduce.**',
      'mpki_instr', '%.4f', MEAN)
table('L2 DATA load MPKI',
      'The cost of prioritising. Static I-RRIP raises this on every trace; the '
      'dynamic policy should raise it less where prioritising does not pay.',
      'mpki_data', '%.4f', MEAN)

# --- the comparison that actually answers Task 2b -------------------------
if 'irrip' in have and 'dyn_irrip' in have and 'lru_t2a' in have:
    A('### Did adapting help? Dynamic vs static, per trace\n')
    A('Task 2b exists because static I-RRIP regresses a trace. The test is whether')
    A('the dynamic policy recovers that trace **without** giving back the trace where')
    A('prioritising pays. `vs LRU` columns flag a regression against the baseline.\n')
    A('| trace | policy | instr MPKI | L2C MPKI | vs LRU | speedup | verdict |')
    A('|---|---|---|---|---|---|---|')
    for t in TRACES:
        if (BASE, t) not in data:
            continue
        b = data[(BASE, t)]
        for cfg in ('rrip', 'irrip', 'dyn_irrip'):
            if (cfg, t) not in data:
                continue
            d = data[(cfg, t)]
            delta = 100.0 * (d['mpki_l2c'] - b['mpki_l2c']) / b['mpki_l2c']
            A('| %s | %s | %.4f | %.4f | %+.1f%% | %.4f | %s |' % (
                t, label[cfg], d['mpki_instr'], d['mpki_l2c'], delta, d['speedup'],
                'REGRESSES' if delta > 0.1 else 'clean'))
    A('')

# --- the dynamic behaviour itself ----------------------------------------
if 'dyn_irrip' in have:
    A('### The duel: what the selector actually did\n')
    A('`% in I-RRIP` is the share of decision windows that chose to prioritise.')
    A('`switches` is how often the verdict flipped: a high count means the selector')
    A('is thrashing rather than tracking phases, which no MPKI table would reveal.')
    A('`sacrificed` is the fraction of the cache pinned to a leader policy -- the')
    A('price of measuring, paid in cache the followers do not get.\n')
    A('| trace | windows | % in I-RRIP | switches | switches/window | PSEL | sacrificed | storage (B) |')
    A('|---|---|---|---|---|---|---|---|')
    for t in TRACES:
        if ('dyn_irrip', t) not in data:
            continue
        d = data[('dyn_irrip', t)]
        A('| %s | %d | %.1f%% | %d | %.4f | %d | %.2f%% | %d |' % (
            t, d['windows'], d['pct_irrip'], d['switches'],
            (d['switches'] / float(d['windows']) if d['windows'] else 0),
            d['psel'], d['sacrificed'], d['storage']))
    A('')
    A('Read `% in I-RRIP` against Task 2a: the dynamic policy *should* sit near 0 %')
    A('on the trace where static prioritisation lost and near 100 % where it won. If')
    A('it does not, the selector is reading the wrong signal, and that is the finding')
    A('to report rather than a number to tune away.\n')

A('### Eviction conflicts\n')
A('`data->instr` is a data fill throwing out an instruction line -- the conflict')
A('instruction-consciousness exists to reduce, and direct evidence about the')
A('mechanism independently of whether MPKI moved.\n')
A('| policy | trace | instr victims | data->instr | instr->instr |')
A('|---|---|---|---|---|')
for cfg in have:
    for t in TRACES:
        if (cfg, t) not in data:
            continue
        d = data[(cfg, t)]
        A('| %s | %s | %d | %d | %d |' % (label[cfg], t, d['victims_i'], d['dei'], d['iei']))
A('')

io.open(os.path.join(RESDIR, 'task2b_tables.md'), 'w', encoding='utf-8').write('\n'.join(O) + '\n')
print('wrote', os.path.join(RESDIR, 'task2b_tables.md'))

print('\n%-20s %-8s %8s %8s %10s %10s %10s %8s' % (
    'config', 'trace', 'IPC', 'speedup', 'L2C MPKI', 'instr', 'data', '%irrip'))
for cfg in have:
    for t in TRACES:
        if (cfg, t) not in data:
            continue
        d = data[(cfg, t)]
        print('%-20s %-8s %8.5f %8.4f %10.4f %10.4f %10.4f %8.1f' % (
            cfg, t, d['ipc'], d['speedup'], d['mpki_l2c'], d['mpki_instr'],
            d['mpki_data'], d['pct_irrip']))
    v = [data[(cfg, t)] for t in TRACES if (cfg, t) in data]
    if v:
        print('%-20s %-8s %8.5f %8.4f %10.4f %10.4f %10.4f %8s   <- aggregate' % (
            cfg, 'ALL', mean([x['ipc'] for x in v]), geo([x['speedup'] for x in v]),
            mean([x['mpki_l2c'] for x in v]), mean([x['mpki_instr'] for x in v]),
            mean([x['mpki_data'] for x in v]), ''))
