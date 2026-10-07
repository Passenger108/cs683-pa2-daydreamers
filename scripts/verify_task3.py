#!/usr/bin/env python3
"""
CS683 PA2 - Task 3 audit.  Checks that the source, the logs and the design-doc
numbers all agree, in the same spirit as verify_task2a/2b: the errors that
survive review are real numbers attached to the wrong claim, so we check the
attachments.

    python3 scripts/verify_task3.py
"""
import io, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, 'scripts')
from parse_results import parse_log, geomean           # noqa: E402

TRS = ['trace1', 'trace2', 'trace3']
POL = 'replacement/dyn_irrip.l2c_repl'
SRC = io.open(POL, encoding='utf-8').read()
DD = io.open('docs/TASK3_DESIGN_DECISIONS.md').read() if os.path.exists('docs/TASK3_DESIGN_DECISIONS.md') else ''
npass = nfail = 0


def check(name, cond, detail=''):
    global npass, nfail
    print('  %s  %s%s' % ('PASS' if cond else 'FAIL', name, '' if cond else '   ' + detail))
    if cond: npass += 1
    else: nfail += 1


print('== 1. the prefetch-awareness is actually in the policy ==')
check('reads packet type PREFETCH', 'type == PREFETCH' in SRC)
check('DYN_SPP_AWARE knob present', '#define DYN_SPP_AWARE' in SRC)
check('DYN_PF_INSERT knob present', '#define DYN_PF_INSERT' in SRC)
check('prefetch insert is gated on DYN_SPP_AWARE',
      re.search(r'#if DYN_SPP_AWARE\s*\n\s*if \(pf\) return DYN_PF_INSERT', SRC) is not None)
check('static_assert bounds DYN_PF_INSERT to an RRPV',
      'DYN_PF_INSERT >= 0 && DYN_PF_INSERT <= DYN_MAX_RRPV' in SRC)
check('counts useful prefetches at L2 (demand hit on a prefetched line)',
      'block[set][way].prefetch) dyn_pf_useful++' in SRC)

print('\n== 2. every knob combination compiles clean ==')
bad = []
for A in (0, 1):
    for P in ('1', '2', 'DYN_MAX_RRPV'):
        r = subprocess.run(['g++', '-std=c++11', '-x', 'c++', '-Iinc', '-Wall',
                            '-Warray-bounds', '-fsyntax-only',
                            '-DDYN_SPP_AWARE=%d' % A, '-DDYN_PF_INSERT=%s' % P, POL],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        msg = [l for l in r.stdout.decode().splitlines()
               if ('error' in l or 'warning' in l) and 'linker input' not in l]
        if r.returncode or msg:
            bad.append('AWARE=%d PF=%s' % (A, P))
check('all 6 SPP_AWARE x PF_INSERT combinations compile clean', not bad, str(bad))

print('\n== 3. INERTNESS: standalone dyn I-RRIP (no prefetcher) == Task 2b bit-for-bit ==')
# The Task 3 edit only fires on PREFETCH fills, so with no prefetcher the L2
# behaviour must be identical to Task 2b's dyn_irrip, except the additive
# "DYN PREFETCH" stats line and the extended config line.
def beh(path):
    if not os.path.exists(path):
        return None
    return [l for l in io.open(path, errors='ignore').read().splitlines()
            if l.startswith('L2C ') and 'DYN PREFETCH' not in l
            and 'DYN-IRRIP config' not in l]
have = all(os.path.exists('results/task3/dyn_irrip_t3_%s.txt' % t) for t in TRS) and \
       all(os.path.exists('results/task2b/dyn_irrip_%s.txt' % t) for t in TRS)
if have:
    same = all(beh('results/task3/dyn_irrip_t3_%s.txt' % t) ==
               beh('results/task2b/dyn_irrip_%s.txt' % t) for t in TRS)
    check('standalone dyn_irrip_t3 reproduces Task 2b dyn_irrip (edit is inert without a prefetcher)', same)
else:
    print('  SKIP  need results/task3/dyn_irrip_t3_* and results/task2b/dyn_irrip_* -- run both')

print('\n== 4. the combined policy saw prefetches and handled them ==')
for t in TRS:
    p = 'results/task3/spp_dyn_irrip_%s.txt' % t
    if not os.path.exists(p):
        print('  SKIP  %s not run yet' % p); continue
    m = re.search(r'DYN PREFETCH aware (\d+) pf_insert_rrpv (\d+) pf_inserts (\d+) pf_useful_at_l2 (\d+)',
                  io.open(p, errors='ignore').read())
    v = [int(x) for x in m.groups()] if m else [0, 0, 0, 0]
    check('%s: aware=1 and non-zero prefetch inserts' % t, v[0] == 1 and v[2] > 0,
          'aware=%d inserts=%d' % (v[0], v[2]))

print('\n== 5. THE TASK 3 BAR: combined beats BOTH standalones in IPC ==')
def _plog(p):
    return parse_log(p) if os.path.exists(p) else None
def sp(tag):
    base = {t: _plog('results/task3/lru_t3_%s.txt' % t) for t in TRS}
    recs = {t: _plog('results/task3/%s_%s.txt' % (tag, t)) for t in TRS}
    xs = [recs[t]['ipc'] / base[t]['ipc'] for t in TRS
          if recs.get(t) and base.get(t) and base[t].get('ipc')]
    return geomean(xs) if len(xs) == len(TRS) else None
sc, ss, sd = sp('spp_dyn_irrip'), sp('spp_t3'), sp('dyn_irrip_t3')
if None in (sc, ss, sd):
    print('  SKIP  run all four configs first (./scripts/run_task3.sh)')
else:
    check('combined (%.4f) > SPP alone (%.4f)' % (sc, ss), sc > ss)
    check('combined (%.4f) > dyn I-RRIP alone (%.4f)' % (sc, sd), sc > sd)

print('\n== 6. metric definitions match Task 1 (accuracy, coverage) ==')
pr = io.open('scripts/parse_results.py').read()
check('accuracy = pf_useful / pf_lower_level (Task 1 definition, reused)',
      'l1d_pf_useful' in pr and 'l1d_pf_lower_level' in pr)
check('parse_task3 imports parse_results.parse_log (no redefined metric)',
      'from parse_results import parse_log' in io.open('scripts/parse_task3.py').read())

print('\n== 7. design-doc numbers match the logs ==')
if DD and None not in (sc, ss, sd):
    DDN = re.sub(r'(?<=\d)[ \t](?=\d)', '', DD)
    for tag, label in (('spp_dyn_irrip', 'combined'), ('spp_t3', 'SPP alone'),
                       ('dyn_irrip_t3', 'dyn I-RRIP alone')):
        s = sp(tag)
        check('doc quotes %s speedup %.4f' % (label, s), ('%.4f' % s) in DDN, 'not in doc')
else:
    print('  SKIP  design doc or logs not ready')

print('\n%s  %d passed, %d failed' % ('OK ' if nfail == 0 else 'PROBLEMS', npass, nfail))
sys.exit(1 if nfail else 0)
