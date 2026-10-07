#!/usr/bin/env python3
"""
CS683 PA2 - Task 2b knob sweep.

15 variants x 3 traces = 45 runs. Smaller than Task 2a's 26 variants on
purpose: 2a established that its ten knobs all moved a single axis, so most of
those runs bought nothing. Here every group answers a question the deliverable
asks or that the design genuinely cannot settle by argument.

The deliverable requires a sensitivity study over five threshold values. It is
run for BOTH threshold-based selectors -- the PDF's suggested formula and the
instruction-hit-rate alternative -- because comparing one tuned selector against
one untuned one would be a rigged comparison.

MUST run inside the GCC 7 container: a clang build produces different simulated
counters (measured: up to 3.82% on trace2 for an identical policy), which is the
same size as the effects being measured here.

    python3 scripts/sweep_task2b.py [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task2b.py --list
    python3 scripts/sweep_task2b.py --only A,B [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task2b.py --summary-only
"""
import io, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SRC = 'replacement/dyn_irrip.l2c_repl'
VAR = 'replacement/dyn_sweep.l2c_repl'
OUT = 'results/task2b_sweep'
TRACES = ['trace1', 'trace2', 'trace3']
N_WARM = N_SIM = 25000000
BINPRE = ('bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-dyn_sweep'
          '-lru-lru-lru-lru-1core-')

KNOBS = ('MAX_RRPV', 'SELECTOR', 'THRESH_PCT', 'HYST_PCT',
         'NUM_LEADERS', 'WINDOW', 'INSTR_WEIGHT')

# The shipped defaults. Every variant below is this with one or two changes,
# and write_variant() pins ALL of them, so a variant is a complete,.
# self-contained specification rather than something that inherits whatever the
# source happens to say today. (In Task 2a it did inherit, and ten variants
# silently stopped building when the shipped default changed.)
CENTRE = dict(MAX_RRPV=3, SELECTOR=1, THRESH_PCT=45, HYST_PCT=3,
              NUM_LEADERS=32, WINDOW=8192, INSTR_WEIGHT=2)

VARIANTS = [
 # ---- A: the PDF's suggested formula, swept over five thresholds -----------
 # Required by the deliverable. The formula measures instruction VOLUME, and
 # the Task 2a data says volume is not monotone in the right answer: trace3 has
 # the LOWEST instruction share (28.4%) yet prioritising helps it, while trace1
 # has 58.4% and prioritising hurts. If that holds, no threshold on this axis
 # separates them -- which is the point of sweeping five of them.
 ('A', 'pdf_t15', "PDF formula, threshold 15%", dict(SELECTOR=0, THRESH_PCT=15)),
 ('A', 'pdf_t25', "PDF formula, threshold 25% (the value the PDF suggests)",
      dict(SELECTOR=0, THRESH_PCT=25)),
 ('A', 'pdf_t35', "PDF formula, threshold 35%", dict(SELECTOR=0, THRESH_PCT=35)),
 ('A', 'pdf_t45', "PDF formula, threshold 45%", dict(SELECTOR=0, THRESH_PCT=45)),
 ('A', 'pdf_t60', "PDF formula, threshold 60%", dict(SELECTOR=0, THRESH_PCT=60)),

 # ---- B: instruction hit rate, swept over five thresholds -----------------
 # The Task 2a signal. Measured instruction hit rates were 35.0 / 52.8 / 75.4%
 # for trace1 / trace3 / trace2, perfectly ordered against their IPC gains, so
 # the useful boundary should sit between 35 and 53. These five bracket it.
 ('B', 'hit_t30', "hit rate, threshold 30% (below all three traces)",
      dict(SELECTOR=1, THRESH_PCT=30)),
 ('B', 'hit_t40', "hit rate, threshold 40%", dict(SELECTOR=1, THRESH_PCT=40)),
 ('B', 'hit_t45', "hit rate, threshold 45% (shipped default)",
      dict(SELECTOR=1, THRESH_PCT=45)),
 ('B', 'hit_t55', "hit rate, threshold 55%", dict(SELECTOR=1, THRESH_PCT=55)),
 ('B', 'hit_t70', "hit rate, threshold 70% (above all but trace2)",
      dict(SELECTOR=1, THRESH_PCT=70)),

 # ---- C: true DIP set-duelling, weighted and unweighted -------------------
 # The only selector that measures WHICH POLICY WINS rather than what kind of
 # workload this is, and the only one with no threshold to tune. Weight 1 is
 # DIP as published. Weight 2 encodes Task 2a 14.4: trace3 gets MORE total
 # misses and BETTER IPC under prioritisation, so a duel counting raw misses
 # should get trace3 wrong, and weighting instruction misses should fix it.
 # If weight 1 and weight 2 disagree on trace3 specifically, that is the
 # cleanest confirmation available that the two miss types differ in cost.
 ('C', 'psel_w1', "DIP duel, instruction misses weighted 1 (DIP as published)",
      dict(SELECTOR=2, INSTR_WEIGHT=1)),
 ('C', 'psel_w2', "DIP duel, instruction misses weighted 2", dict(SELECTOR=2, INSTR_WEIGHT=2)),

 # ---- D: how many leader sets? -------------------------------------------
 # The deliverable asks for the rationale behind this number, and it is a real
 # trade-off: more leaders give a less noisy signal but pin more of the cache
 # to a policy that may be the wrong one. 8 of 1024 is 0.8% sacrificed, 128 is
 # 12.5%. If 8 is as good as 32, the measurement was never the bottleneck.
 ('D', 'lead8',   "8 leader sets per group (0.8% of the cache)",  dict(NUM_LEADERS=8)),
 ('D', 'lead128', "128 leader sets per group (12.5% of the cache)", dict(NUM_LEADERS=128)),

 # ---- E: does the duel need a wider RRPV? --------------------------------
 # 3 is the minimum for the two modes to differ at all. 7 gives longer
 # deadlines and a slower aging loop; Task 2a found wider was not better as a
 # static policy, but a duel has different needs, so it is measured not assumed.
 ('E', 'max7', "3-bit RRPV instead of 2-bit", dict(MAX_RRPV=7)),

 # ---- F: stage 2, one question the first pass left open -------------------
 # Group D found FEWER leaders is better -- 8 leaders (0.8% of the cache) beat
 # 32 (3.1%) beat 128 (12.5%) -- so the sacrificed capacity dominates the
 # benefit of a less noisy signal. But D was measured with SELECTOR 1, which
 # uses ONE leader group. The shipped selector is the duel, which needs TWO and
 # therefore sacrifices twice as much: 6.25% at 32 leaders. If the leader cost
 # transfers, shrinking the groups should help the duel MORE than it helped the
 # threshold selector. Untested combinations do not get shipped on a hunch, so
 # this measures it: 3 runs each.
 ('F', 'psel_lead8',  "the shipped duel with 8 leader sets per group (1.6% sacrificed)",
      dict(SELECTOR=2, INSTR_WEIGHT=2, NUM_LEADERS=8)),
 ('F', 'psel_lead16', "the shipped duel with 16 leader sets per group (3.1% sacrificed)",
      dict(SELECTOR=2, INSTR_WEIGHT=2, NUM_LEADERS=16)),
]


def write_variant(knobs):
    """Copy the policy with EVERY knob pinned to CENTRE plus these overrides."""
    full = dict(CENTRE); full.update(knobs)
    t = io.open(SRC, encoding='utf-8').read()
    for k, v in full.items():
        pat = re.compile(r'^#define DYN_%s .*$' % re.escape(k), re.M)
        if not pat.search(t):
            raise SystemExit('knob DYN_%s not found in %s' % (k, SRC))
        t = pat.sub('#define DYN_%s %d' % (k, v), t)
    io.open(VAR, 'w', encoding='utf-8').write(t)


def expected_cfg(knobs):
    """The config line the built variant must print. Mirrors the policy's cout."""
    k = dict(CENTRE); k.update(knobs)
    sets = int(re.search(r'#define L2C_SET (\d+)',
                         io.open('inc/cache.h', encoding='utf-8').read()).group(1))
    return ('MAX_RRPV %d | SELECTOR %d thresh %d hyst %d | LEADERS %d stride %d'
            ' | WINDOW %d | INSTR_WEIGHT %d') % (
        k['MAX_RRPV'], k['SELECTOR'], k['THRESH_PCT'], k['HYST_PCT'],
        k['NUM_LEADERS'], sets // k['NUM_LEADERS'], k['WINDOW'], k['INSTR_WEIGHT'])


def assert_gcc7_linux():
    if sys.platform != 'linux':
        raise SystemExit('REFUSING TO RUN: platform is %r, not Linux. This sweep must\n'
                         'run inside the GCC 7 container; a macOS/clang build gives\n'
                         'different simulated counters.' % sys.platform)
    try:
        v = subprocess.run(['g++', '--version'], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).stdout.decode('utf-8', 'replace')
    except OSError:
        raise SystemExit('REFUSING TO RUN: no g++ on PATH.')
    if not re.search(r'\b7\.\d+\.\d+', v):
        raise SystemExit('REFUSING TO RUN: g++ is not 7.x --\n  %s\nUse '
                         'update-alternatives to select g++-7.' % v.strip().split('\n')[0])
    print('toolchain OK: %s' % v.strip().split('\n')[0])


def build(vid):
    print('  building sw_%s ...' % vid, flush=True)
    r = subprocess.run(['./build_champsim.sh', 'no', 'dyn_sweep', 'sw_' + vid],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    binp = BINPRE + 'sw_' + vid
    if r.returncode != 0 or not os.path.exists(binp):
        io.open(os.path.join(OUT, 'BUILD_FAIL_%s.txt' % vid), 'w',
                encoding='utf-8').write(r.stdout.decode('utf-8', 'replace'))
        print('  BUILD FAILED for %s (see %s/BUILD_FAIL_%s.txt)' % (vid, OUT, vid))
        return None
    return binp


def done(vid):
    for t in TRACES:
        p = os.path.join(OUT, '%s_%s.txt' % (vid, t))
        if not os.path.exists(p):
            return False
        if 'Region of Interest' not in io.open(p, encoding='utf-8', errors='replace').read():
            return False
    return True


def run_all(binp, vid, trace_dir, jobs):
    procs = []
    for t in TRACES:
        log = os.path.join(OUT, '%s_%s.txt' % (vid, t))
        if os.path.exists(log) and 'Region of Interest' in io.open(
                log, encoding='utf-8', errors='replace').read():
            print('    [skip] %s' % log); continue
        fh = io.open(log, 'wb')
        print('    [run ] %s on %s' % (vid, t), flush=True)
        procs.append((subprocess.Popen(
            [binp, '-warmup_instructions', str(N_WARM),
             '-simulation_instructions', str(N_SIM),
             '-traces', os.path.join(trace_dir, t + '.gz')],
            stdout=fh, stderr=subprocess.STDOUT), fh))
        while len([p for p, _ in procs if p.poll() is None]) >= jobs:
            procs[0][0].wait()
    for p, fh in procs:
        p.wait(); fh.close()


def read_log(path):
    t = io.open(path, encoding='utf-8', errors='replace').read()
    roi = t.find('Region of Interest Statistics')
    if roi < 0:
        return None
    tl = t[roi:]

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
             nb=g(r'DYN STORAGE .*total_bytes (\d+)', int, t, 0),
             cfg=g(r'^L2C DYN-IRRIP config\s+(.*)$', str, t, ''))
    if d['ipc'] is None or d['miss'] is None:
        return None
    d['ml'] = d['miss'] * 1000.0 / d['instrs']
    return d


def geo(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def summarise(selected):
    base, static = {}, {}
    for t in TRACES:
        for store, path in ((base, 'results/task2b/lru_t2a_%s.txt' % t),
                            (static, 'results/task2b/irrip_%s.txt' % t)):
            if os.path.exists(path):
                d = read_log(path)
                if d:
                    store[t] = d
    if len(base) < len(TRACES):
        print('note: results/task2b/lru_t2a_*.txt incomplete -- speedup column will be '
              'blank. Run ./scripts/run_task2b.sh first.')

    rows, bad = [], []
    for grp, vid, desc, kn in selected:
        per = {}
        for t in TRACES:
            p = os.path.join(OUT, '%s_%s.txt' % (vid, t))
            if os.path.exists(p):
                d = read_log(p)
                if d:
                    per[t] = d
        if len(per) < len(TRACES):
            continue
        want, got = expected_cfg(kn), per[TRACES[0]]['cfg'].strip()
        if got and got != want:
            bad.append((vid, want, got)); continue
        sps = ([per[t]['ipc'] / base[t]['ipc'] for t in TRACES]
               if len(base) == len(TRACES) else None)
        rows.append(dict(grp=grp, vid=vid, desc=desc, per=per, cfg=got,
                         sp=(geo(sps) if sps else None),
                         sp_per=({t: per[t]['ipc'] / base[t]['ipc'] for t in TRACES}
                                 if sps else None),
                         ml=sum(per[t]['ml'] for t in TRACES) / 3.0,
                         mi=sum(per[t]['mi'] for t in TRACES) / 3.0,
                         md=sum(per[t]['md'] for t in TRACES) / 3.0,
                         pct={t: per[t]['pct'] for t in TRACES},
                         sw=sum(per[t]['sw'] for t in TRACES),
                         nb=per[TRACES[0]]['nb']))
    if bad:
        print('\n!! SKIPPED -- compiled config != requested config')
        for vid, want, got in bad:
            print('   %s\n     wanted: %s\n     got   : %s' % (vid, want, got))

    o = ['# Task 2b knob sweep\n',
         'Each row: 3 traces, 25M warmup + 25M simulation, GCC 7 `-O3`. Speedup is the',
         'geometric mean against the LRU baseline; MPKIs are arithmetic means.',
         '`% prioritising` is the share of decision windows that chose I-RRIP mode, per',
         'trace -- the column that says whether the selector is reading the right signal.',
         '`switches` is the total across the three traces: a large number means the',
         'selector is thrashing rather than tracking phases.\n',
         '| grp | variant | question | speedup | L2C MPKI | instr MPKI | data MPKI |'
         ' % prioritising (t1/t2/t3) | switches | storage (B) |',
         '|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        o.append('| %s | `%s` | %s | %s | %.4f | %.4f | %.4f | %.0f/%.0f/%.0f | %d | %d |' % (
            r['grp'], r['vid'], r['desc'], ('%.4f' % r['sp']) if r['sp'] else '-',
            r['ml'], r['mi'], r['md'],
            r['pct']['trace1'], r['pct']['trace2'], r['pct']['trace3'],
            r['sw'], r['nb']))

    # Per-trace, with a regression flag. Task 2a shipped on an aggregate that
    # concealed a per-trace regression; that must not happen twice.
    o += ['\n## Per trace -- and does the row regress anything?\n',
          'The point of Task 2b is to fix static I-RRIP\'s regression without giving',
          'back its win. `REGRESSES` marks an L2C load MPKI worse than LRU on at least',
          'one trace. The `static` row is Task 2a\'s policy, for comparison.\n']
    if len(base) == len(TRACES):
        hdr = '| variant |'
        for t in TRACES:
            hdr += ' %s L2C | %s sp |' % (t, t)
        o.append(hdr + ' verdict |')
        o.append('|---|' + '---|' * (2 * len(TRACES) + 1))
        b = '| LRU baseline |'
        for t in TRACES:
            b += ' %.3f | 1.0000 |' % base[t]['ml']
        o.append(b + ' - |')
        if len(static) == len(TRACES):
            s = '| I-RRIP static (2a) |'
            worse = []
            for t in TRACES:
                s += ' %.3f | %.4f |' % (static[t]['ml'], static[t]['ipc'] / base[t]['ipc'])
                if static[t]['ml'] > base[t]['ml'] * 1.001:
                    worse.append(t)
            o.append(s + (' **REGRESSES %s** |' % ','.join(worse) if worse else ' clean |'))
        for r in rows:
            if not r['sp_per']:
                continue
            line = '| `%s` |' % r['vid']
            worse = []
            for t in TRACES:
                line += ' %.3f | %.4f |' % (r['per'][t]['ml'], r['sp_per'][t])
                if r['per'][t]['ml'] > base[t]['ml'] * 1.001:
                    worse.append(t)
            o.append(line + (' **REGRESSES %s** |' % ','.join(worse) if worse else ' clean |'))
    o.append('\n## Exact configuration of each row\n')
    for r in rows:
        o.append('* `%s` -- %s' % (r['vid'], r['cfg']))
    p = os.path.join(OUT, 'sweep_summary.md')
    io.open(p, 'w', encoding='utf-8').write('\n'.join(o) + '\n')
    print('\nwrote %s  (%d variants tabulated)' % (p, len(rows)))


def main():
    args, only, summary_only, rest = sys.argv[1:], None, False, []
    i = 0
    while i < len(args):
        if args[i] == '--list':
            for grp, vid, desc, kn in VARIANTS:
                print('  [%s] %-9s %s' % (grp, vid, desc))
                print('              %s' % expected_cfg(kn))
            return
        elif args[i] == '--only':
            only = set(x.strip() for x in args[i + 1].split(',')); i += 1
        elif args[i] == '--summary-only':
            summary_only = True
        else:
            rest.append(args[i])
        i += 1

    trace_dir = rest[0] if rest else '../traces'
    jobs = int(rest[1]) if len(rest) > 1 else 3
    selected = [v for v in VARIANTS if only is None or v[0] in only or v[1] in only]
    os.makedirs(OUT, exist_ok=True)

    if not summary_only:
        assert_gcc7_linux()
        print('%d variant(s) x %d traces = %d simulations, plus %d rebuilds.\n'
              % (len(selected), len(TRACES), len(selected) * len(TRACES), len(selected)))
        for n, (grp, vid, desc, kn) in enumerate(selected, 1):
            print('[%d/%d] %s  (%s)' % (n, len(selected), vid, desc))
            if done(vid):
                print('  all three traces already complete, skipping build'); continue
            write_variant(kn)
            binp = build(vid)
            if binp:
                run_all(binp, vid, trace_dir, jobs)
        if os.path.exists(VAR):
            os.remove(VAR)
    # Always tabulate every variant whose logs exist, never just this run's --
    # passing only the selection would make --only truncate the summary.
    summarise(VARIANTS)


if __name__ == '__main__':
    main()
