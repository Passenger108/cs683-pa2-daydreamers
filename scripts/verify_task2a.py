#!/usr/bin/env python3
"""
Task 2a self-audit.

Checks that the claims made in docs/TASK2A_*.md are actually true of the source
tree and of the measured logs.  In Task 1 the errors that survived review were
not wrong numbers -- they were real numbers attached to the wrong claim -- so
this script exists to check the attachments.

usage:  python3 scripts/verify_task2a.py
"""
import io, os, re, sys

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


POLICY = read('replacement/irrip.l2c_repl')
DD     = read('docs/TASK2A_DESIGN_DECISIONS.md')
GUIDE  = read('docs/TASK2A_IRRIP.md')
RUN    = read('docs/TASK2A_RUN_INSTRUCTIONS.md')
CACHEH = read('inc/cache.h')
CACHEC = read('src/cache.cc')

print('\n== 1. knob defaults in the source match the table in the design doc ==')
WANT = [('MAX_RRPV', '1', '1'), ('INSERT_INSTR', '0', '0'),
        ('INSERT_DATA', 'IRRIP_MAX_RRPV', 'max'),
        ('INSERT_TRANSL', 'IRRIP_MAX_RRPV', 'max'),
        ('PROMOTE_INSTR', '0', '0'),
        ('PROMOTE_DATA', 'IRRIP_MAX_RRPV', 'max'),
        ('PROMOTE_TRANSL', '0', '0'),
        ('EVICT_PREFER_DATA', '0', '0'), ('EVICT_SLACK', '0', '0'),
        ('WB_PROMOTES', '1', '1')]
for knob, lit, docval in WANT:
    m = re.search(r'^#define IRRIP_%s (.*)$' % knob, POLICY, re.M)
    check('IRRIP_%s source default is %s' % (knob, lit),
          m is not None and m.group(1).strip() == lit,
          'source has %r' % (m.group(1).strip() if m else None))
    check('IRRIP_%s appears in the design-doc knob table with default `%s`' % (knob, docval),
          re.search(r'`IRRIP_%s`\s*\|\s*%s\s*\|' % (knob, re.escape(docval)), DD) is not None)

print('\n== 2. every knob is static_assert range-checked ==')
for knob, _, _ in WANT:
    if knob == 'MAX_RRPV':
        continue
    check('static_assert mentions IRRIP_%s' % knob,
          ('IRRIP_%s' % knob) in POLICY.split('static_assert', 1)[1].split('uint8_t l2_irrip_rrpv')[0],
          'no static_assert found')

print('\n== 3. storage arithmetic ==')
sets = int(re.search(r'#define L2C_SET (\d+)', CACHEH).group(1))
ways = int(re.search(r'#define L2C_WAY (\d+)', CACHEH).group(1))
check('L2C_SET x L2C_WAY == 8192 lines', sets * ways == 8192, '%d x %d' % (sets, ways))
for mx, bits in [(1, 1), (3, 2), (7, 3)]:
    b = 1
    while (1 << b) - 1 < mx:
        b += 1
    check('maxRRPV %d needs %d bits' % (mx, bits), b == bits)
check('shipped (1-bit) storage is 1024 B and the doc says so',
      sets * ways * 1 // 8 == 1024 and '1 024 B' in DD)
check('LRU needs 3 bits/line = 3072 B and the doc says so',
      sets * ways * 3 // 8 == 3072 and '3 072 B' in DD)
check('doc claims the -1024 B / -33% saving', '−1 024 B (−33 %)' in DD)

print('\n== 4. source line references cited in the docs ==')
lines_c = CACHEC.split('\n')
lines_h = CACHEH.split('\n')


def at(lst, n, needle):
    return 0 < n <= len(lst) and needle in lst[n - 1]


check('src/cache.cc:60 declares fill_packet_type', at(lines_c, 60, 'fill_packet_type'))
check('src/cache.cc:2929 sets block[].instruction = 1', at(lines_c, 2929, 'instruction = 1'))
check('src/cache.cc:1885 is the MSHR[-1] UB site', at(lines_c, 1885, 'MSHR.entry[mshr_index]'))
check('src/cache.cc:56 is the handle_fill find_victim', at(lines_c, 56, 'find_victim'))
check('src/cache.cc:553 is the handle_fill fill_cache', at(lines_c, 553, 'fill_cache'))
for n in (140, 527, 819, 1080, 1766, 2452):
    check('src/cache.cc:%d is an update_replacement_state call site' % n,
          at(lines_c, n, 'update_replacement_state'))
    check('src/cache.cc:%d passes .instruction' % n, at(lines_c, n, '.instruction)'))
check('inc/cache.h:93 defines L2C_SET', at(lines_h, 93, 'L2C_SET'))
check('inc/cache.h:94 defines L2C_WAY', at(lines_h, 94, 'L2C_WAY'))
check('inc/cache.h:152-160 declare the evicting counters',
      all('evicting' in lines_h[n - 1] for n in range(152, 161)))
check('rrip.l2c_repl:38 is the 9-param declaration',
      'isInstruction' in read('replacement/rrip.l2c_repl').split('\n')[37])
mm = read('src/main.cc').split('\n')
check('src/main.cc:198 prints INSTRUCTION LOAD MPKI', at(mm, 198, 'INSTRUCTION LOAD MPKI'))
check('src/main.cc:306-314 print the nine evicting counters',
      all('victing' in mm[n - 1] for n in range(306, 315)))
check('src/main.cc:1329 assigns l2c_update_replacement_state',
      at(mm, 1329, 'l2c_update_replacement_state'))

print('\n== 5. the signature change is complete and uniform ==')
import glob
files = sorted(set(['inc/cache.h', 'replacement/base_replacement.cc']
                   + glob.glob('replacement/*_repl')
                   + glob.glob('replacement/*_replacement.cc')))
sigs = []
for f in files:
    for m in re.finditer(r'\w*update_replacement_state[\)]?\((?:uint32_t cpu[^)]*)\)', read(f)):
        sigs.append((f, len([x for x in m.group(0).split('(', 1)[1].rstrip(')').split(',') if x.strip()])))
check('all %d update_replacement_state definitions have 9 params' % len(sigs),
      all(k == 9 for _, k in sigs),
      str([s for s in sigs if s[1] != 9]))
check('design doc claims 27 EDITED declarations',
      '27 declarations' in DD and '**27**' in DD)
check('%d nine-param definitions now in tree (grows as policies are added)' % len(sigs),
      len(sigs) >= 29, 'counted %d across %d files' % (len(sigs), len(files)))
calls = []
for f in sorted(glob.glob('src/*.cc')):
    body = read(f)
    for m in re.finditer(r'update_replacement_state\)\((.*?)\);', body):
        args = re.sub(r'/\*.*?\*/', '', m.group(1))
        calls.append((f, body[:m.start()].count('\n') + 1,
                      len([a for a in args.split(',') if a.strip()])))
check('9 call sites tree-wide (6 in cache.cc + 3 BTB in ooo_cpu.cc)',
      len(calls) == 9, 'found %d: %s' % (len(calls), calls))
check('every call site passes 9 arguments',
      all(n == 9 for _, _, n in calls), str([c for c in calls if c[2] != 9]))
check('the three BTB sites are in src/ooo_cpu.cc',
      sorted(set(f for f, _, _ in calls)) == ['src/cache.cc', 'src/ooo_cpu.cc'],
      str(sorted(set(f for f, _, _ in calls))))
check('design doc documents 9 call sites', 'The 9 call sites' in DD)

print('\n== 6. policy line count claimed in the docs ==')
n = len(POLICY.rstrip('\n').split('\n'))
claimed = re.search(r'(\d+) lines, all knobs in one block', RUN)
check('run doc\'s line count for irrip.l2c_repl matches the file (%d)' % n,
      claimed is not None and int(claimed.group(1)) == n,
      'doc says %s' % (claimed.group(1) if claimed else 'nothing'))

print('\n== 7. baseline numbers quoted in the design doc match the Task 1 logs ==')
BASE = {}
for tr in ('trace1', 'trace2', 'trace3'):
    p = 'results/task1/baseline_%s.txt' % tr
    if not os.path.exists(p):
        print('  SKIP  %s absent' % p)
        continue
    t = read(p)
    BASE[tr] = dict(
        load=float(re.search(r'^L2C LOAD\s+ACCESS:.*MPKI:\s*([\d.]+)', t, re.M).group(1)),
        instr=float(re.search(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)', t, re.M).group(1)),
        data=float(re.search(r'^L2C DATA LOAD MPKI:\s*([\d.]+)', t, re.M).group(1)),
        dei=int(re.search(r'^L2C Data Evicting Instructions\s+(\d+)', t, re.M).group(1)),
        iei=int(re.search(r'^L2C Instructions Evicting Instructions\s+(\d+)', t, re.M).group(1)),
        tei=int(re.search(r'^L2C Translations Evicting Instructions\s+(\d+)', t, re.M).group(1)))
for tr, want in [('trace1', ('17.6956', '10.3377', '7.3580', 120225, 112800)),
                 ('trace2', ('27.3568', '18.8533', '8.5035', 136147, 298635)),
                 ('trace3', ('3.9542', '1.1241', '2.8302', 19415, 8097))]:
    if tr not in BASE:
        continue
    b = BASE[tr]
    check('%s load MPKI %s in doc == log %.4f' % (tr, want[0], b['load']),
          want[0] in DD and abs(float(want[0]) - b['load']) < 5e-4)
    check('%s instr MPKI %s in doc == log %.4f' % (tr, want[1], b['instr']),
          want[1] in DD and abs(float(want[1]) - b['instr']) < 5e-4)
    check('%s data MPKI %s in doc == log %.4f' % (tr, want[2], b['data']),
          want[2] in DD and abs(float(want[2]) - b['data']) < 5e-4)
    check('%s data->instr %d matches log' % (tr, want[3]), want[3] == b['dei'],
          'log says %d' % b['dei'])
    check('%s instr->instr %d matches log' % (tr, want[4]), want[4] == b['iei'],
          'log says %d' % b['iei'])
    vic = b['dei'] + b['iei'] + b['tei']
    pct = 100.0 * b['dei'] / vic
    doc_pct = {'trace1': 46.6, 'trace2': 29.4, 'trace3': 63.2}[tr]
    check('%s "killed by a data fill" share %.1f%% matches doc %.1f%%' % (tr, pct, doc_pct),
          abs(pct - doc_pct) < 0.1, 'computed %.2f' % pct)
    doc_share = {'trace1': 58.4, 'trace2': 68.9, 'trace3': 28.4}[tr]
    share = 100.0 * b['instr'] / b['load']
    check('%s instruction share of load MPKI %.1f%% matches doc %.1f%%' % (tr, share, doc_share),
          abs(share - doc_share) < 0.1, 'computed %.2f' % share)

print('\n== 8. scripts exist, are syntactically valid, and the docs name them right ==')
import ast
for s in ['run_task2a.sh', 'parse_task2a.py', 'plot_task2a.py', 'sweep_task2a.py',
          'verify_task2a.py']:
    p = 'scripts/' + s
    check('%s exists' % p, os.path.exists(p))
    if p.endswith('.py') and os.path.exists(p):
        try:
            ast.parse(read(p)); good = True
        except SyntaxError as e:
            good = False
        check('%s parses' % p, good)
    check('%s is referenced in the run doc' % s, s in RUN)

print('\n== 9. sweep variant count claimed in the docs ==')
sw = read('scripts/sweep_task2a.py')
nvar = len(re.findall(r"^ \('", sw, re.M))
check('both docs state the live variant count (%d)' % nvar,
      ('%d variants' % nvar) in DD and ('%d variants' % nvar) in RUN,
      'docs disagree with the %d variants in sweep_task2a.py' % nvar)
check('run doc states the live simulation count (%d)' % (nvar * 3),
      ('%d simulations' % (nvar * 3)) in RUN)

print('\n== 10. the three harness gates added after the first bad run (13) ==')
MAINC = read('src/main.cc').split('\n')
l1d = [i+1 for i,l in enumerate(MAINC) if 'l1d_prefetcher_final_stats()' in l]
l2r = [i+1 for i,l in enumerate(MAINC) if 'l2c_replacement_final_stats()' in l]
check('ChampSim still has exactly one multi-core-only call site to work around',
      len(l1d) == 2, 'l1d_prefetcher_final_stats at %s' % l1d)
check('l2c_replacement_final_stats is called in the single-core loop',
      len(l1d) == 2 and any(abs(n - l1d[1]) <= 10 for n in l2r),
      'single-core loop near line %s, replacement calls at %s'
      % (l1d[1] if len(l1d) > 1 else '?', l2r))
RUNSH = read('scripts/run_task2a.sh')
check('run_task2a.sh rejects a non-ELF (clang/macOS) binary', "grep -q '^ELF'" in RUNSH)
check('run_task2a.sh rejects a binary older than src/ or inc/', '-newer "$b"' in RUNSH)
SW = read('scripts/sweep_task2a.py')
check('sweep_task2a.py refuses to run outside GCC 7 on Linux',
      'assert_gcc7_linux' in SW and "sys.platform != 'linux'" in SW
      and 'assert_gcc7_linux()' in SW.split('def main')[1])
PA = read('scripts/parse_task2a.py')
check('parse_task2a.py reconstructs and enforces the I-RRIP config identity',
      'expected_irrip_config' in PA and 'EXPECTED_CFG' in PA
      and 'has no "L2C I-RRIP config" line' in PA)
import importlib.util as _ilu
_s = _ilu.module_from_spec(_ilu.spec_from_file_location('swv', 'scripts/sweep_task2a.py'))
_ilu.spec_from_file_location('swv', 'scripts/sweep_task2a.py').loader.exec_module(_s)
_shipped = None
for k in ('MAX_RRPV',):
    pass
_v = {}
for _k in ('MAX_RRPV', 'INSERT_INSTR', 'INSERT_DATA', 'INSERT_TRANSL',
           'PROMOTE_INSTR', 'PROMOTE_DATA', 'PROMOTE_TRANSL',
           'EVICT_PREFER_DATA', 'EVICT_SLACK', 'WB_PROMOTES'):
    _m = re.search(r'^#define IRRIP_%s (.*)$' % _k, POLICY, re.M)
    _v[_k] = eval(_m.group(1).strip().replace('IRRIP_MAX_RRPV', str(_v.get('MAX_RRPV', 0))))
_cfg = ('MAX_RRPV %d | INSERT instr %d data %d transl %d | PROMOTE instr %d data %d transl %d | '
        'EVICT_PREFER_DATA %d slack %d | WB_PROMOTES %d') % tuple(
    _v[x] for x in ('MAX_RRPV', 'INSERT_INSTR', 'INSERT_DATA', 'INSERT_TRANSL',
                    'PROMOTE_INSTR', 'PROMOTE_DATA', 'PROMOTE_TRANSL',
                    'EVICT_PREFER_DATA', 'EVICT_SLACK', 'WB_PROMOTES'))
_match = [v[1] for v in _s.VARIANTS if _s.expected_cfg(v[3]) == _cfg]
check('shipped defaults are exactly a swept variant (expect max1_prod1)',
      _match == ['max1_prod1'], 'matched %s for cfg %s' % (_match, _cfg))

check('design doc records all three harness failures',
      '## 13. Three ways the harness lied' in DD and '13.1' in DD and '13.2' in DD and '13.3' in DD)

print('\n== 11. every number quoted in design-doc 14 matches the logs ==')
DDN = re.sub(r'(?<=\d)[ \u2009\u202f\u00a0](?=\d)', '', DD)
TRS = ['trace1', 'trace2', 'trace3']


def _m(path):
    txt = read(path)
    roi = txt.find('Region of Interest Statistics')
    tl = txt[roi:] if roi >= 0 else txt
    def g(pat, c=float):
        mm = re.search(pat, tl, re.M)
        return c(mm.group(1)) if mm else None
    d = dict(ipc=g(r'CPU 0 cumulative IPC:\s*([\d.]+)'),
             instrs=g(r'CPU 0 cumulative IPC:\s*[\d.]+\s*instructions:\s*(\d+)', int),
             i=g(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)'),
             d=g(r'^L2C DATA LOAD MPKI:\s*([\d.]+)'),
             miss=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*\d+\s+MISS:\s*(\d+)', int))
    if d['miss'] and d['instrs']:
        d['l2c'] = d['miss'] * 1000.0 / d['instrs']
    for k, pat in (('dei', r'^L2C Data Evicting Instructions\s+(\d+)'),
                   ('iei', r'^L2C Instructions Evicting Instructions\s+(\d+)'),
                   ('tei', r'^L2C Translations Evicting Instructions\s+(\d+)')):
        d[k] = g(pat, int) or 0
    for k, pat in (('ins_i', r'IRRIP INSERTS instr (\d+)'),
                   ('ins_d', r'IRRIP INSERTS instr \d+ data (\d+)'),
                   ('pro_i', r'IRRIP PROMOTES instr (\d+)'),
                   ('pro_d', r'IRRIP PROMOTES instr \d+ data (\d+)'),
                   ('bytes', r'IRRIP STORAGE .*total_bytes (\d+)')):
        mm = re.search(pat, txt)
        d[k] = int(mm.group(1)) if mm else 0
    return d


def _mean(xs):
    return sum(xs) / float(len(xs))


def _geo(xs):
    p_ = 1.0
    for x in xs:
        p_ *= x
    return p_ ** (1.0 / len(xs))


if all(os.path.exists('results/task2a/%s_%s.txt' % (c, t_))
       for c in ('lru_t2a', 'rrip', 'irrip') for t_ in TRS):
    R = {c: {t_: _m('results/task2a/%s_%s.txt' % (c, t_)) for t_ in TRS}
         for c in ('lru_t2a', 'rrip', 'irrip')}
    for cfg, mi, md, ml, sp in (('lru_t2a', '10.1050', '6.2305', '16.3356', '1.0000'),
                                ('rrip',    '9.8467',  '5.9613', '15.8080', '1.0004'),
                                ('irrip',   '6.2219',  '8.5371', '14.7590', '1.0138')):
        gi = _mean([R[cfg][t_]['i'] for t_ in TRS])
        gd = _mean([R[cfg][t_]['d'] for t_ in TRS])
        gl = _mean([R[cfg][t_]['l2c'] for t_ in TRS])
        gs = _geo([R[cfg][t_]['ipc'] / R['lru_t2a'][t_]['ipc'] for t_ in TRS])
        check('14.1 %-8s instr %s' % (cfg, mi), mi in DD and abs(float(mi) - gi) < 5e-5, 'computed %.5f' % gi)
        check('14.1 %-8s data  %s' % (cfg, md), md in DD and abs(float(md) - gd) < 5e-5, 'computed %.5f' % gd)
        check('14.1 %-8s L2C   %s' % (cfg, ml), ml in DD and abs(float(ml) - gl) < 5e-5, 'computed %.5f' % gl)
        check('14.1 %-8s spdup %s' % (cfg, sp), sp in DD and abs(float(sp) - gs) < 5e-5, 'computed %.5f' % gs)
    for t_, want in (('trace1', ('9.238', '9.996', '19.234', '0.9967', 200049, 103643, 77919)),
                     ('trace2', ('8.715', '12.344', '21.058', '1.0384', 189603, 70729, 103316)),
                     ('trace3', ('0.713', '3.271', '3.985', '1.0068', 16064, 8580, 5650))):
        r = R['irrip'][t_]
        check('14.1 %s instr %s' % (t_, want[0]), want[0] in DD and abs(float(want[0]) - r['i']) < 1e-3, '%.4f' % r['i'])
        check('14.1 %s data %s' % (t_, want[1]), want[1] in DD and abs(float(want[1]) - r['d']) < 1e-3, '%.4f' % r['d'])
        check('14.1 %s L2C %s' % (t_, want[2]), want[2] in DD and abs(float(want[2]) - r['l2c']) < 1e-3, '%.4f' % r['l2c'])
        check('14.1 %s spdup %s' % (t_, want[3]),
              want[3] in DD and abs(float(want[3]) - r['ipc'] / R['lru_t2a'][t_]['ipc']) < 5e-5)
        check('14.1 %s instr victims %d' % (t_, want[4]),
              str(want[4]) in DDN and r['dei'] + r['iei'] + r['tei'] == want[4],
              'computed %d' % (r['dei'] + r['iei'] + r['tei']))
        check('14.1 %s d->i %d' % (t_, want[5]), str(want[5]) in DDN and r['dei'] == want[5], '%d' % r['dei'])
        check('14.1 %s i->i %d' % (t_, want[6]), str(want[6]) in DDN and r['iei'] == want[6], '%d' % r['iei'])
    for t_, wi, wd in (('trace1', '0.54', '0.13'), ('trace2', '3.06', '0.19'), ('trace3', '1.12', '0.12')):
        r = R['irrip'][t_]
        ri = r['pro_i'] / float(r['ins_i']); rd = r['pro_d'] / float(r['ins_d'])
        check('14.2 %s instr reuse %s' % (t_, wi), wi in DD and abs(float(wi) - ri) < 5e-3, '%.3f' % ri)
        check('14.2 %s data reuse %s' % (t_, wd), wd in DD and abs(float(wd) - rd) < 5e-3, '%.3f' % rd)
    check('14.6 storage 1024 B, printed by the run',
          R['irrip']['trace1']['bytes'] == 1024 and '1024B' in DDN.replace(' B', 'B')
          and 'total_bytes 1024' in DD)
    if all(os.path.exists('results/task2a_sweep/ev0_wb0_trev_%s.txt' % t_) for t_ in TRS):
        A = {t_: _m('results/task2a_sweep/ev0_wb0_trev_%s.txt' % t_) for t_ in TRS}
        ai = _mean([A[t_]['i'] for t_ in TRS]); al = _mean([A[t_]['l2c'] for t_ in TRS])
        asp = _geo([A[t_]['ipc'] / R['lru_t2a'][t_]['ipc'] for t_ in TRS])
        check('14.5 ev0_wb0_trev instr 7.776', '7.776' in DD and abs(7.776 - ai) < 5e-4, '%.4f' % ai)
        check('14.5 ev0_wb0_trev L2C 14.384', '14.384' in DD and abs(14.384 - al) < 5e-4, '%.4f' % al)
        check('14.5 ev0_wb0_trev spdup 1.0069', '1.0069' in DD and abs(1.0069 - asp) < 5e-5, '%.5f' % asp)
    if all(os.path.exists('results/task2a_sweep/max7_ev4_%s.txt' % t_) for t_ in TRS):
        B = {t_: _m('results/task2a_sweep/max7_ev4_%s.txt' % t_) for t_ in TRS}
        bl = _mean([B[t_]['l2c'] for t_ in TRS])
        bsp = _geo([B[t_]['ipc'] / R['lru_t2a'][t_]['ipc'] for t_ in TRS])
        check('14.4 max7_ev4 L2C 14.247 (worse MPKI than shipped)',
              '14.247' in DD and abs(14.247 - bl) < 5e-4, '%.4f' % bl)
        check('14.4 max7_ev4 spdup 1.0092 (lower IPC than shipped)',
              '1.0092' in DD and abs(1.0092 - bsp) < 5e-5, '%.5f' % bsp)
else:
    print('  SKIP  results/task2a incomplete')

print('\n== 12. every translation unit front-end-compiles, for all 3 policies ==')
import shutil, subprocess
units = sorted(subprocess.run(['find', 'src', 'branch', 'replacement', 'prefetcher',
                               '-name', '*.cc'], stdout=subprocess.PIPE
                              ).stdout.decode().split())
cxx = shutil.which('g++')
if not cxx:
    print('  SKIP  no g++ on this machine')
elif not os.path.exists('replacement/lru.l2c_repl'):
    print('  SKIP  policy sources missing')
else:
    saved = read('replacement/l2c_replacement.cc')
    for pol in ('lru', 'rrip', 'irrip'):
        shutil.copy('replacement/%s.l2c_repl' % pol, 'replacement/l2c_replacement.cc')
        broken = []
        for u in units:
            r = subprocess.run([cxx, '-std=c++11', '-Iinc', '-fsyntax-only', u],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                broken.append(u)
        check('L2C=%-5s all %d translation units compile' % (pol, len(units)),
              not broken, str(broken))
    io.open('replacement/l2c_replacement.cc', 'w', encoding='utf-8').write(saved)

print('\n%s  %d passed, %d failed' % ('OK' if fail == 0 else 'PROBLEMS', ok, fail))
sys.exit(1 if fail else 0)
