#!/usr/bin/env python3
"""
CS683 PA2 - Task 2a results parser.

Reads the ChampSim logs produced by scripts/run_task2a.sh and emits

    results/task2a/task2a.csv          one row per (config, trace)
    results/task2a/task2a_tables.md    the tables the PDF asks for

Task 2a deliverable, verbatim:
    "Report the IPC, speedup, and Load MPKI of L2C, L2 Instruction, and L2 Data
     in tabular form, and plot them."

so the five required columns are IPC, speedup, L2C load MPKI, L2 instruction
load MPKI, L2 data load MPKI.  Everything else this script prints is supporting
evidence for the rationale section, not a required deliverable.

AGGREGATION, and why each choice:
  * speedup is a RATIO, so the across-trace figure is the GEOMETRIC mean.  An
    arithmetic mean of ratios is not the speedup of anything; the geometric mean
    is the only average for which "A is x% faster than B" composes correctly and
    does not depend on which config you put in the denominator.
  * MPKI is already normalised per 1000 instructions and every trace ran exactly
    25M instructions, so the ARITHMETIC mean across traces is correct here and
    happens to equal the pooled (total misses / total instructions) value.

usage:  python3 scripts/parse_task2a.py [RESULT_DIR]
"""
import csv, io, os, re, sys

RESDIR  = sys.argv[1] if len(sys.argv) > 1 else 'results/task2a'
TRACES  = ['trace1', 'trace2', 'trace3']
# order matters: the first entry is the speedup denominator
CONFIGS = [('lru_t2a', 'LRU (baseline)'),
           ('rrip',    'RRIP (supplied)'),
           ('irrip',   'I-RRIP (ours)')]

EVICT_PAIRS = [('Instructions', 'Data'), ('Translations', 'Data'), ('Data', 'Data'),
               ('Instructions', 'Instructions'), ('Translations', 'Instructions'),
               ('Data', 'Instructions'),
               ('Instructions', 'Translations'), ('Translations', 'Translations'),
               ('Data', 'Translations')]


def num(s):
    return float(s)


def expected_irrip_config():
    """Rebuild the config line irrip.l2c_repl would print, from its #defines.

    This is the identity check.  A log is only accepted as a measurement of the
    current I-RRIP if it contains exactly this line.  It exists because a stale
    binary -- built at 13:03 from an entirely different I-RRIP whose source was
    no longer in the tree -- was once run and reported as a result.  An mtime
    test can be fooled by a touch; this cannot, because the string is emitted by
    the binary itself at run time.
    """
    src = 'replacement/irrip.l2c_repl'
    if not os.path.exists(src):
        return None
    txt = io.open(src, encoding='utf-8').read()
    v = {}
    for k in ('MAX_RRPV', 'INSERT_INSTR', 'INSERT_DATA', 'INSERT_TRANSL',
              'PROMOTE_INSTR', 'PROMOTE_DATA', 'PROMOTE_TRANSL',
              'EVICT_PREFER_DATA', 'EVICT_SLACK', 'WB_PROMOTES'):
        m = re.search(r'^#define IRRIP_%s (.*)$' % k, txt, re.M)
        if not m:
            return None
        v[k] = eval(m.group(1).strip().replace('IRRIP_MAX_RRPV', str(v.get('MAX_RRPV', 0))))
    return ('MAX_RRPV %d | INSERT instr %d data %d transl %d | '
            'PROMOTE instr %d data %d transl %d | '
            'EVICT_PREFER_DATA %d slack %d | WB_PROMOTES %d') % (
        v['MAX_RRPV'], v['INSERT_INSTR'], v['INSERT_DATA'], v['INSERT_TRANSL'],
        v['PROMOTE_INSTR'], v['PROMOTE_DATA'], v['PROMOTE_TRANSL'],
        v['EVICT_PREFER_DATA'], v['EVICT_SLACK'], v['WB_PROMOTES'])


EXPECTED_CFG = expected_irrip_config()

# Let run_task2a.sh ask for this string, so its resume logic can tell a log
# produced by the CURRENT I-RRIP configuration from one produced by an older
# set of knob values.  Without it, changing a #define leaves stale logs that
# "reached the Region of Interest" and are therefore skipped as complete.
if '--print-expected-config' in sys.argv:
    print(EXPECTED_CFG or '')
    sys.exit(0)


def parse(path):
    """Pull every number we care about out of one ChampSim log."""
    t = io.open(path, encoding='utf-8', errors='replace').read()
    d = {}

    # --- IPC: the Region-of-Interest value, never the warmup heartbeats ------
    roi = t.find('Region of Interest Statistics')
    if roi < 0:
        raise ValueError('%s: no Region of Interest section (run incomplete)' % path)
    tail = t[roi:]
    m = re.search(r'CPU 0 cumulative IPC:\s*([\d.]+)\s*instructions:\s*(\d+)\s*cycles:\s*(\d+)', tail)
    if not m:
        raise ValueError('%s: could not find ROI IPC line' % path)
    d['ipc']    = num(m.group(1))
    d['instrs'] = int(m.group(2))
    d['cycles'] = int(m.group(3))

    # --- L2C load: exact access/hit/miss counts ------------------------------
    m = re.search(r'^L2C LOAD\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+)', tail, re.M)
    d['l2c_load_access'] = int(m.group(1))
    d['l2c_load_hit']    = int(m.group(2))
    d['l2c_load_miss']   = int(m.group(3))

    m = re.search(r'^L2C TOTAL\s+ACCESS:\s*(\d+)\s+HIT:\s*(\d+)\s+MISS:\s*(\d+)', tail, re.M)
    d['l2c_total_access'] = int(m.group(1))
    d['l2c_total_miss']   = int(m.group(3))

    # --- the two split MPKIs, exactly as main.cc prints them -----------------
    # These printed values ARE the graded numbers, so they are taken verbatim
    # rather than recomputed.  main.cc prints at 6 significant figures, so the
    # miss counts reconstructed from them below can be off by +/-1 line; the
    # MPKIs themselves are not.
    d['mpki_instr'] = num(re.search(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)', tail, re.M).group(1))
    d['mpki_data']  = num(re.search(r'^L2C DATA LOAD MPKI:\s*([\d.]+)',        tail, re.M).group(1))

    d['mpki_l2c_load']  = d['l2c_load_miss']  * 1000.0 / d['instrs']
    d['mpki_l2c_total'] = d['l2c_total_miss'] * 1000.0 / d['instrs']

    d['instr_miss'] = int(round(d['mpki_instr'] * d['instrs'] / 1000.0))
    d['data_miss']  = d['l2c_load_miss'] - d['instr_miss']

    m = re.search(r'^L2C AVERAGE MISS LATENCY:\s*([\d.]+)', tail, re.M)
    d['miss_latency'] = num(m.group(1)) if m else float('nan')

    # --- the nine eviction-conflict counters ChampSim already keeps ----------
    for killer, victim in EVICT_PAIRS:
        m = re.search(r'^L2C %s Evicting %s\s+(\d+)' % (killer, victim), tail, re.M)
        d['ev_%s_%s' % (killer[:5].lower(), victim[:5].lower())] = int(m.group(1)) if m else 0
    d['victims_instr'] = (d['ev_instr_instr'] + d['ev_trans_instr'] + d['ev_data_instr'])
    d['victims_data']  = (d['ev_instr_data']  + d['ev_trans_data']  + d['ev_data_data'])
    d['victims_trans'] = (d['ev_instr_trans'] + d['ev_trans_trans'] + d['ev_data_trans'])

    # --- I-RRIP's own counters, when the policy is I-RRIP --------------------
    m = re.search(r'^L2C I-RRIP config\s+(.*)$', t, re.M)
    d['irrip_config'] = m.group(1).strip() if m else ''
    # Identity gate, applied only to I-RRIP logs.
    if os.path.basename(path).startswith('irrip_'):
        if not d['irrip_config']:
            raise ValueError(
                '%s has no "L2C I-RRIP config" line -- it was NOT produced by the '
                'current replacement/irrip.l2c_repl. Rebuild and re-run.' % path)
        if EXPECTED_CFG and d['irrip_config'] != EXPECTED_CFG:
            raise ValueError(
                '%s was built from different knob values than the source on disk.\n'
                '      log:    %s\n      source: %s' % (path, d['irrip_config'], EXPECTED_CFG))
    for key, pat in [('ins_i', r'IRRIP INSERTS instr (\d+)'),
                     ('ins_d', r'IRRIP INSERTS instr \d+ data (\d+)'),
                     ('ins_t', r'IRRIP INSERTS instr \d+ data \d+ transl (\d+)'),
                     ('pro_i', r'IRRIP PROMOTES instr (\d+)'),
                     ('pro_d', r'IRRIP PROMOTES instr \d+ data (\d+)'),
                     ('evpref', r'IRRIP EVICT PREF FIRED (\d+)'),
                     ('age',    r'IRRIP AGE ROUNDS (\d+)'),
                     ('stor',   r'IRRIP STORAGE .*total_bytes (\d+)')]:
        m = re.search(pat, t)
        d['irrip_' + key] = int(m.group(1)) if m else 0
    return d


def geomean(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def mean(xs):
    return sum(xs) / float(len(xs))


# ---------------------------------------------------------------- load -------
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
    print('\nRun ./scripts/run_task2a.sh first.')
    if not data:
        sys.exit(1)
    print('(continuing with what is present)\n')

BASE = CONFIGS[0][0]
for (cfg, tr), d in data.items():
    b = data.get((BASE, tr))
    d['speedup'] = d['ipc'] / b['ipc'] if b else float('nan')

# ----------------------------------------------------------------- csv -------
os.makedirs(RESDIR, exist_ok=True)
cols = (['config', 'trace', 'ipc', 'speedup', 'mpki_l2c_load', 'mpki_instr', 'mpki_data',
         'mpki_l2c_total', 'l2c_load_access', 'l2c_load_hit', 'l2c_load_miss',
         'instr_miss', 'data_miss', 'miss_latency', 'cycles', 'instrs',
         'victims_instr', 'victims_data', 'victims_trans']
        + ['ev_%s_%s' % (k[:5].lower(), v[:5].lower()) for k, v in EVICT_PAIRS]
        + ['irrip_ins_i', 'irrip_ins_d', 'irrip_ins_t', 'irrip_pro_i', 'irrip_pro_d',
           'irrip_evpref', 'irrip_age', 'irrip_stor', 'irrip_config'])
csv_path = os.path.join(RESDIR, 'task2a.csv')
with io.open(csv_path, 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for cfg, _ in CONFIGS:
        for tr in TRACES:
            d = data.get((cfg, tr))
            if not d:
                continue
            w.writerow([cfg, tr] + [d.get(c, '') for c in cols[2:]])
print('wrote', csv_path)

# -------------------------------------------------------------- tables -------
out = []
A = out.append
A('# Task 2a - Instruction-Conscious L2 Replacement (I-RRIP): results\n')
A('All runs: 25M warmup + 25M simulation, single core, no L1D prefetcher,')
A('built with GCC 7 at `-O3`. Speedup is against **LRU (baseline)**, i.e.')
A('`IPC(policy) / IPC(no prefetcher + LRU at L2)`.\n')

have = [c for c, _ in CONFIGS if any((c, t) in data for t in TRACES)]
label = dict(CONFIGS)


def table(title, note, fmt, key, agg):
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


table('IPC', '', '%.5f', 'ipc', ('arith. mean', mean))
table('Speedup over LRU baseline',
      'Geometric mean, because speedup is a ratio.',
      '%.4f', 'speedup', ('geomean', geomean))
table('L2C load MPKI', 'Lower is better. All L2 load misses.',
      '%.4f', 'mpki_l2c_load', ('mean', mean))
table('L2 INSTRUCTION load MPKI',
      'Lower is better. **This is the metric Task 2a asks us to reduce.**',
      '%.4f', 'mpki_instr', ('mean', mean))
table('L2 DATA load MPKI',
      'Lower is better. Watch this one for the starvation side effect that '
      'Task 2b exists to fix.',
      '%.4f', 'mpki_data', ('mean', mean))

# --- the analysis table: what moved, and in which direction ------------------
if 'lru_t2a' in have:
    A('### What changed, per trace\n')
    A('Instruction-MPKI reduction is the goal; data-MPKI change is the cost.')
    A('Both are shown against the LRU baseline so the trade-off is visible.\n')
    A('| policy | trace | instr MPKI | vs LRU | data MPKI | vs LRU | L2C load MPKI | vs LRU |')
    A('|---|---|---|---|---|---|---|---|')
    for cfg in have:
        if cfg == 'lru_t2a':
            continue
        for t in TRACES:
            if (cfg, t) not in data:
                continue
            d, b = data[(cfg, t)], data[('lru_t2a', t)]
            def pct(n, o):
                return '%+.2f%%' % (100.0 * (n - o) / o) if o else 'n/a'
            A('| %s | %s | %.4f | %s | %.4f | %s | %.4f | %s |' % (
                label[cfg], t,
                d['mpki_instr'], pct(d['mpki_instr'], b['mpki_instr']),
                d['mpki_data'],  pct(d['mpki_data'],  b['mpki_data']),
                d['mpki_l2c_load'], pct(d['mpki_l2c_load'], b['mpki_l2c_load'])))
    A('')

# --- eviction conflicts: the mechanism, not just the outcome ----------------
A('### Eviction conflicts (ChampSim\'s own counters)\n')
A('`data->instr` is the number of times a data fill threw out an instruction')
A('line. That is the quantity I-RRIP is built to reduce, so it is the direct')
A('evidence that the mechanism did what it was designed to do, independently')
A('of whether the MPKI happened to move.\n')
A('| policy | trace | instr victims | data->instr | instr->instr | transl->instr | data victims |')
A('|---|---|---|---|---|---|---|')
for cfg in have:
    for t in TRACES:
        if (cfg, t) not in data:
            continue
        d = data[(cfg, t)]
        A('| %s | %s | %d | %d | %d | %d | %d |' % (
            label[cfg], t, d['victims_instr'], d['ev_data_instr'],
            d['ev_instr_instr'], d['ev_trans_instr'], d['victims_data']))
A('')

# --- I-RRIP internals -------------------------------------------------------
if any(('irrip', t) in data for t in TRACES):
    A('### I-RRIP internals\n')
    cfgline = data[('irrip', TRACES[0])]['irrip_config'] if ('irrip', TRACES[0]) in data else ''
    if cfgline:
        A('Configuration read back out of the run\'s own log:\n')
        A('```\n%s\n```\n' % cfgline)
    A('| trace | inserts instr | inserts data | inserts transl | promotes instr | promotes data | evict-pref fired | storage (B) |')
    A('|---|---|---|---|---|---|---|---|')
    for t in TRACES:
        if ('irrip', t) not in data:
            continue
        d = data[('irrip', t)]
        A('| %s | %d | %d | %d | %d | %d | %d | %d |' % (
            t, d['irrip_ins_i'], d['irrip_ins_d'], d['irrip_ins_t'],
            d['irrip_pro_i'], d['irrip_pro_d'], d['irrip_evpref'], d['irrip_stor']))
    A('')

md_path = os.path.join(RESDIR, 'task2a_tables.md')
io.open(md_path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('wrote', md_path)

# ------------------------------------------------------------ console --------
print('\n%-16s %-8s %8s %8s %10s %10s %10s' % ('config', 'trace', 'IPC', 'speedup',
                                               'L2C MPKI', 'instr', 'data'))
for cfg in have:
    for t in TRACES:
        if (cfg, t) not in data:
            continue
        d = data[(cfg, t)]
        print('%-16s %-8s %8.5f %8.4f %10.4f %10.4f %10.4f' % (
            cfg, t, d['ipc'], d['speedup'], d['mpki_l2c_load'], d['mpki_instr'], d['mpki_data']))
    vals = [data[(cfg, t)] for t in TRACES if (cfg, t) in data]
    if vals:
        print('%-16s %-8s %8.5f %8.4f %10.4f %10.4f %10.4f   <- aggregate' % (
            cfg, 'ALL',
            mean([v['ipc'] for v in vals]),
            geomean([v['speedup'] for v in vals]),
            mean([v['mpki_l2c_load'] for v in vals]),
            mean([v['mpki_instr'] for v in vals]),
            mean([v['mpki_data'] for v in vals])))
