#!/usr/bin/env python3
"""
Task 2b self-audit.

Checks that what docs/TASK2B_*.md claim is actually true of the source tree and
the logs. Task 2a's lesson was that the errors which survive review are real
numbers attached to the wrong claim, so this script checks the attachments --
and in Task 2b it would have caught two of the three bugs on its own.

usage:  python3 scripts/verify_task2b.py
"""
import ast, glob, io, os, re, shutil, subprocess, sys

ok = fail = 0


def check(label, cond, detail=''):
    global ok, fail
    if cond:
        ok += 1
        print('  PASS  %s' % label)
    else:
        fail += 1
        print('  FAIL  %s   %s' % (label, detail))


def read(p):
    return io.open(p, encoding='utf-8', errors='replace').read()


POLICY = read('replacement/dyn_irrip.l2c_repl')
SWEEP = read('scripts/sweep_task2b.py')
DD = read('docs/TASK2B_DESIGN_DECISIONS.md') if os.path.exists('docs/TASK2B_DESIGN_DECISIONS.md') else ''
RUN = read('docs/TASK2B_RUN_INSTRUCTIONS.md') if os.path.exists('docs/TASK2B_RUN_INSTRUCTIONS.md') else ''
CACHEH = read('inc/cache.h')
TRS = ['trace1', 'trace2', 'trace3']

KNOBS = ('MAX_RRPV', 'SELECTOR', 'THRESH_PCT', 'HYST_PCT',
         'NUM_LEADERS', 'WINDOW', 'INSTR_WEIGHT')
# The shipped configuration after the 17-variant sweep: the psel_lead8 row.
WANT = [('MAX_RRPV', '3'), ('SELECTOR', '2'), ('THRESH_PCT', '45'),
        ('HYST_PCT', '3'), ('NUM_LEADERS', '8'), ('WINDOW', '8192'),
        ('INSTR_WEIGHT', '2')]

print('\n== 1. shipped knob values ==')
for k, v in WANT:
    m = re.search(r'^#define DYN_%s (.*)$' % k, POLICY, re.M)
    check('DYN_%s is %s' % (k, v), m is not None and m.group(1).strip() == v,
          'source has %r' % (m.group(1).strip() if m else None))
check('every knob is range-checked by static_assert',
      all(('DYN_%s' % k) in POLICY.split('static_assert', 1)[1].split('uint8_t  dyn_rrpv')[0]
          for k, _ in WANT))

print('\n== 2. the shipped config is exactly one of the swept variants ==')
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('sw2b', 'scripts/sweep_task2b.py')
_sw = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_sw)
v = {k: int(re.search(r'^#define DYN_%s (.*)$' % k, POLICY, re.M).group(1)) for k in KNOBS}
sets = int(re.search(r'#define L2C_SET (\d+)', CACHEH).group(1))
cfg = ('MAX_RRPV %d | SELECTOR %d thresh %d hyst %d | LEADERS %d stride %d'
       ' | WINDOW %d | INSTR_WEIGHT %d') % (
    v['MAX_RRPV'], v['SELECTOR'], v['THRESH_PCT'], v['HYST_PCT'],
    v['NUM_LEADERS'], sets // v['NUM_LEADERS'], v['WINDOW'], v['INSTR_WEIGHT'])
match = [x[1] for x in _sw.VARIANTS if _sw.expected_cfg(x[3]) == cfg]
check('shipped defaults match a measured variant (expect psel_lead8)',
      match == ['psel_lead8'], 'matched %s for %s' % (match, cfg))

print('\n== 3. the leader-placement rule the sweep forced ==')
# The L2C set index is address bits 6..15; a 4 KB page covers bits 0..11, so
# set-index bits 0..5 are the within-page 64 B slot. The two leader groups must
# differ in PAGE-NUMBER bits, not within-page-offset bits, or the duel compares
# two policies on two different address populations. This recomputes it.
n = v['NUM_LEADERS']; stride = sets // n
islots = sorted({s % 64 for s in range(sets) if s % stride == 0})
rslots = sorted({s % 64 for s in range(sets) if s % stride == stride // 2})
check('the two leader groups sample the SAME within-page slots (%s)' % islots,
      set(islots) == set(rslots),
      'I %s vs R %s -- the duel would be confounded' % (islots, rslots))
check('design doc records the leader-placement finding',
      'within-page' in DD and 'page-number' in DD)

print('\n== 3b. the PDF\'s mandated leader-set tracking ==')
# "Track the number of instruction and non-instruction line accesses and misses
# to these sets."  This was once gated behind `#if DYN_SELECTOR != PSEL`, so
# shipping the duel silently switched off the tracking the assignment requires
# and the stats line printed zeros.  Two assertions so it cannot recur: the
# code must track unconditionally, and the shipped logs must show it did.
_meas = POLICY.split('the PDF\'s required tracking')[-1].split('#if DYN_SELECTOR')[0] \
    if "the PDF's required tracking" in POLICY else ''
check('per-class leader tracking is NOT selector-gated',
      'dyn_acc[cls]++' in _meas and 'dyn_mis[cls]++' in _meas,
      'the dyn_acc/dyn_mis updates must sit before the #if, not inside it')
for _t in TRS:
    _p = 'results/task2b/dyn_irrip_%s.txt' % _t
    if not os.path.exists(_p):
        print('  SKIP  %s absent' % _p); continue
    _m = re.search(r'DYN COUNTERS instr_acc (\d+) instr_miss (\d+) data_acc (\d+) data_miss (\d+)',
                   read(_p))
    _v = [int(x) for x in _m.groups()] if _m else [0, 0, 0, 0]
    check('%s logs non-zero instruction AND data leader counters' % _t,
          _v[0] > 0 and _v[2] > 0,
          'instr_acc=%d data_acc=%d -- re-run dyn_irrip after the tracking fix' % (_v[0], _v[2]))

print('\n== 4. storage arithmetic ==')
ways = int(re.search(r'#define L2C_WAY (\d+)', CACHEH).group(1))
check('L2C_SET x L2C_WAY == 8192 lines', sets * ways == 8192, '%d x %d' % (sets, ways))
bits = 1
while (1 << bits) - 1 < v['MAX_RRPV']:
    bits += 1
check('MAX_RRPV %d needs %d bits -> %d B of RRPV' % (v['MAX_RRPV'], bits, sets * ways * bits // 8),
      bits == 2 and sets * ways * bits // 8 == 2048)

print('\n== 5. every sweep variant compiles clean and round-trips ==')
bad = []
saved = read('replacement/l2c_replacement.cc')
for grp, vid, desc, kn in _sw.VARIANTS:
    _sw.write_variant(kn)
    t = read(_sw.VAR)
    io.open('replacement/l2c_replacement.cc', 'w', encoding='utf-8').write(t)
    r = subprocess.run(['g++', '-std=c++11', '-Iinc', '-Wall', '-Warray-bounds',
                        '-fsyntax-only', 'replacement/l2c_replacement.cc'],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    msg = [l for l in r.stdout.decode().split('\n')
           if ('error' in l or 'warning' in l) and 'features.h' not in l]
    vv = {k: int(re.search(r'^#define DYN_%s (.*)$' % k, t, re.M).group(1)) for k in KNOBS}
    printed = ('MAX_RRPV %d | SELECTOR %d thresh %d hyst %d | LEADERS %d stride %d'
               ' | WINDOW %d | INSTR_WEIGHT %d') % (
        vv['MAX_RRPV'], vv['SELECTOR'], vv['THRESH_PCT'], vv['HYST_PCT'],
        vv['NUM_LEADERS'], sets // vv['NUM_LEADERS'], vv['WINDOW'], vv['INSTR_WEIGHT'])
    if r.returncode or msg or printed != _sw.expected_cfg(kn):
        bad.append(vid)
if os.path.exists(_sw.VAR):
    os.remove(_sw.VAR)
io.open('replacement/l2c_replacement.cc', 'w', encoding='utf-8').write(saved)
check('all %d variants compile clean and round-trip' % len(_sw.VARIANTS), not bad, str(bad))
check('write_variant pins CENTRE + overrides (not just overrides)',
      'full = dict(CENTRE)' in SWEEP)
check('sweep refuses to run outside GCC 7 on Linux',
      'assert_gcc7_linux' in SWEEP and "sys.platform != 'linux'" in SWEEP)

print('\n== 6. harness gates ==')
RUNSH = read('scripts/run_task2b.sh')
check('run_task2b.sh rejects a non-ELF (clang/macOS) binary', "grep -q '^ELF'" in RUNSH)
check('run_task2b.sh rejects a binary older than its build inputs', '-newer "$b"' in RUNSH)
PA = read('scripts/parse_task2b.py')
check('parse_task2b.py reconstructs and enforces the DYN config identity',
      'expected_dyn_config' in PA and 'was built from different knobs' in PA)
check('run_task2b.sh re-runs dyn_irrip when the knobs change',
      'EXPECT_DYN' in RUNSH and '[redo]' in RUNSH)

print('\n== 7. the headline runs are present, complete and identity-checked ==')
CFG = ['lru_t2a', 'rrip', 'irrip', 'dyn_irrip']
present = all(os.path.exists('results/task2b/%s_%s.txt' % (c, t)) for c in CFG for t in TRS)
check('all 12 headline logs exist', present)


def log(p):
    t = read(p)
    roi = t.find('Region of Interest Statistics')
    tl = t[roi:] if roi >= 0 else t

    def g(pat, c=float, where=None, d=None):
        m = re.search(pat, tl if where is None else where, re.M)
        return c(m.group(1)) if m else d
    d = dict(ipc=g(r'CPU 0 cumulative IPC:\s*([\d.]+)'),
             instrs=g(r'CPU 0 cumulative IPC:\s*[\d.]+\s*instructions:\s*(\d+)', int),
             miss=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*\d+\s+MISS:\s*(\d+)', int),
             mi=g(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)'),
             md=g(r'^L2C DATA LOAD MPKI:\s*([\d.]+)'),
             pct=g(r'pct_irrip ([\d.]+)', float, t, 0.0),
             sw=g(r'switches (\d+)', int, t, 0),
             win=g(r'DYN MODE windows (\d+)', int, t, 0),
             cfg=g(r'^L2C DYN-IRRIP config\s+(.*)$', str, t, ''))
    d['ml'] = d['miss'] * 1000.0 / d['instrs']
    return d


if present:
    R = {(c, t): log('results/task2b/%s_%s.txt' % (c, t)) for c in CFG for t in TRS}
    check('every dyn_irrip log carries the shipped config',
          all(R[('dyn_irrip', t)]['cfg'] == cfg for t in TRS))

    # The three control policies must reproduce Task 2a bit-for-bit, which is
    # what proves dyn_irrip and the main.cc edit are behaviour-neutral.
    for c in ('lru_t2a', 'rrip', 'irrip'):
        same = True
        for t in TRS:
            a = 'results/task2a/%s_%s.txt' % (c, t)
            if not os.path.exists(a):
                same = None; break
            la = [l for l in read(a).split('\n') if l.startswith('L2C ')]
            lb = [l for l in read('results/task2b/%s_%s.txt' % (c, t)).split('\n')
                  if l.startswith('L2C ')]
            if la != lb:
                same = False
        if same is None:
            print('  SKIP  %s not present in results/task2a' % c)
        else:
            check('%s reproduces Task 2a bit-for-bit' % c, same)

    # The shipped dyn_irrip must equal the sweep row it was chosen from.
    srow = all(os.path.exists('results/task2b_sweep/psel_lead8_%s.txt' % t) for t in TRS)
    if srow:
        # Behavioural equality: every L2C line must match the sweep row the
        # shipped config was chosen from -- EXCEPT the "DYN COUNTERS" line.
        # That line was changed on purpose after the sweep ran: the shipped
        # build reports cumulative leader-set counts (the PDF's mandated
        # tracking), while the sweep snapshot still printed the decayed windowed
        # residue.  The change touches no policy logic, so excluding this one
        # reporting line is exactly the right scope for a behaviour check.
        def beh(txt):
            return [l for l in txt.split('\n')
                    if l.startswith('L2C ') and 'DYN COUNTERS' not in l]
        same = all(beh(read('results/task2b/dyn_irrip_%s.txt' % t)) ==
                   beh(read('results/task2b_sweep/psel_lead8_%s.txt' % t)) for t in TRS)
        check('shipped dyn_irrip reproduces the swept psel_lead8 logs '
              '(behaviour; DYN COUNTERS line reports cumulatively by design)', same)

    print('\n== 8. the duel chose the better mode on all three traces ==')
    # Ground truth: whichever of static I-RRIP / RRIP had the higher IPC.
    for t in TRS:
        truth = R[('irrip', t)]['ipc'] > R[('rrip', t)]['ipc']   # True => prioritise
        choseni = R[('dyn_irrip', t)]['pct'] > 50
        check('%s: better mode is %-6s, duel chose %-6s (%.0f%% prioritising)' % (
                  t, 'I-RRIP' if truth else 'RRIP', 'I-RRIP' if choseni else 'RRIP',
                  R[('dyn_irrip', t)]['pct']),
              truth == choseni)
    # Not thrashing: a selector flipping every window is not adapting.
    for t in TRS:
        w, s = R[('dyn_irrip', t)]['win'], R[('dyn_irrip', t)]['sw']
        check('%s: %d switches over %d windows (%.3f/window, not thrashing)' % (t, s, w, s / float(w) if w else 0),
              w > 0 and s / float(w) < 0.5, 'ratio %.3f' % (s / float(w) if w else 0))

    print('\n== 9. numbers quoted in the design doc match the logs ==')
    if DD:
        def mean(xs):
            return sum(xs) / float(len(xs))

        def geo(xs):
            p = 1.0
            for x in xs:
                p *= x
            return p ** (1.0 / len(xs))
        DDN = re.sub(r'(?<=\d)[    ](?=\d)', '', DD)
        for c, label in (('lru_t2a', 'LRU'), ('rrip', 'RRIP'),
                         ('irrip', 'static I-RRIP'), ('dyn_irrip', 'dynamic')):
            sp = geo([R[(c, t)]['ipc'] / R[('lru_t2a', t)]['ipc'] for t in TRS])
            for key, nm in (('ml', 'L2C MPKI'), ('mi', 'instr MPKI')):
                val = mean([R[(c, t)][key] for t in TRS])
                check('doc quotes %s %s %.4f' % (label, nm, val), ('%.4f' % val) in DDN,
                      'not found in the design doc')
            check('doc quotes %s speedup %.4f' % (label, sp), ('%.4f' % sp) in DDN)
        for t in TRS:
            p = R[('dyn_irrip', t)]['pct']
            check('doc quotes %s prioritising share %.1f%%' % (t, p),
                  ('%.1f' % p) in DDN or ('%.0f' % p) in DDN)
    else:
        print('  SKIP  docs/TASK2B_DESIGN_DECISIONS.md not written yet')

print('\n== 10. every translation unit compiles, for all four policies ==')
units = sorted(subprocess.run(['find', 'src', 'branch', 'replacement', 'prefetcher',
                               '-name', '*.cc'], stdout=subprocess.PIPE).stdout.decode().split())
saved = read('replacement/l2c_replacement.cc')
for pol in ('lru', 'rrip', 'irrip', 'dyn_irrip'):
    shutil.copy('replacement/%s.l2c_repl' % pol, 'replacement/l2c_replacement.cc')
    broken = [u for u in units
              if subprocess.run(['g++', '-std=c++11', '-Iinc', '-fsyntax-only', u],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode]
    check('L2C=%-9s all %d translation units compile' % (pol, len(units)), not broken, str(broken))
io.open('replacement/l2c_replacement.cc', 'w', encoding='utf-8').write(saved)

print('\n%s  %d passed, %d failed' % ('OK' if fail == 0 else 'PROBLEMS', ok, fail))
sys.exit(1 if fail else 0)
