#!/usr/bin/env python3
"""
CS683 PA2 - Task 3 knob sweep: how should the replacement policy treat an
SPP-prefetched line?  4 variants x 3 traces = 12 runs, all built WITH SPP.

This is deliberately small (Task 2a's lesson: do not sweep knobs that move one
axis).  The ONE question Task 3 cannot settle by argument is the prefetch
insertion depth, because it trades two measured effects against each other:
  - accuracy is only ~48-57% (task1.csv), so inserting prefetches shallow
    (protected) reproduces the pollution that SPP+LRU already suffers;
  - but the useful ~50% need to survive to their demand hit, so inserting them
    at evict-next (MAX_RRPV) could throw the good half away and LOSE to SPP+LRU.
So the depth is swept, not guessed, and the unaware ablation is run so we can
PROVE awareness -- not merely adding SPP -- is what moves IPC.

MUST run inside the GCC 7 container (clang gives different simulated counters).

    python3 scripts/sweep_task3.py [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task3.py --list
    python3 scripts/sweep_task3.py --only pf_max [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task3.py --summary-only
"""
import io, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from parse_results import parse_log, geomean            # noqa: E402

SRC = 'replacement/dyn_irrip.l2c_repl'
VAR = 'replacement/dyn_sweep.l2c_repl'
OUT = 'results/task3_sweep'
TRACES = ['trace1', 'trace2', 'trace3']
N_WARM = N_SIM = 25000000
# built WITH spp -> prefetcher slot 2 is spp
BINPRE = ('bin/hashed_perceptron-no-spp-no-no-no-no-no-lru-lru-lru-dyn_sweep'
          '-lru-lru-lru-lru-1core-')

KNOBS = ('MAX_RRPV', 'SELECTOR', 'THRESH_PCT', 'HYST_PCT',
         'NUM_LEADERS', 'WINDOW', 'INSTR_WEIGHT', 'SPP_AWARE', 'PF_INSERT')

# CENTRE = the shipped Task 2b duel, unchanged; only the two Task 3 knobs vary.
CENTRE = dict(MAX_RRPV=3, SELECTOR=2, THRESH_PCT=45, HYST_PCT=3,
              NUM_LEADERS=8, WINDOW=8192, INSTR_WEIGHT=2,
              SPP_AWARE=1, PF_INSERT=3)

VARIANTS = [
 # id            description                                    overrides
 ('unaware', "SPP_AWARE off: a prefetch is treated as ordinary data (ablation)",
      dict(SPP_AWARE=0)),
 ('pf_max',  "aware, insert prefetch at MAX_RRPV=3 (evict-next; max anti-pollution)",
      dict(SPP_AWARE=1, PF_INSERT=3)),
 ('pf_max1', "aware, insert prefetch at MAX_RRPV-1=2 (one reprieve)",
      dict(SPP_AWARE=1, PF_INSERT=2)),
 ('pf_mid',  "aware, insert prefetch at 1 (more protection for the useful half)",
      dict(SPP_AWARE=1, PF_INSERT=1)),
]


def write_variant(knobs):
    full = dict(CENTRE); full.update(knobs)
    t = io.open(SRC, encoding='utf-8').read()
    for k, v in full.items():
        pat = re.compile(r'^#define DYN_%s .*$' % re.escape(k), re.M)
        if not pat.search(t):
            raise SystemExit('knob DYN_%s not found in %s' % (k, SRC))
        t = pat.sub('#define DYN_%s %d' % (k, v), t)
    io.open(VAR, 'w', encoding='utf-8').write(t)


def assert_gcc7_linux():
    if sys.platform != 'linux':
        raise SystemExit('REFUSING TO RUN: platform %r is not Linux; use the GCC 7 '
                         'container (clang gives different simulated counters).' % sys.platform)
    try:
        v = subprocess.run(['g++', '--version'], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).stdout.decode('utf-8', 'replace')
    except OSError:
        raise SystemExit('REFUSING TO RUN: no g++ on PATH.')
    if not re.search(r'\b7\.\d+\.\d+', v):
        raise SystemExit('REFUSING TO RUN: g++ is not 7.x:\n  %s' % v.splitlines()[0])
    print('toolchain OK: %s' % v.splitlines()[0])


def build(vid):
    print('  building sw_%s (spp + dyn_sweep) ...' % vid, flush=True)
    write_variant(dict(VARIANTS_BY_ID[vid]))
    r = subprocess.run(['./build_champsim.sh', 'spp', 'dyn_sweep', 'sw_' + vid],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    binp = BINPRE + 'sw_' + vid
    if r.returncode != 0 or not os.path.exists(binp):
        os.makedirs(OUT, exist_ok=True)
        io.open(os.path.join(OUT, 'BUILD_FAIL_%s.txt' % vid), 'w',
                encoding='utf-8').write(r.stdout.decode('utf-8', 'replace'))
        print('  BUILD FAILED for %s (see %s/BUILD_FAIL_%s.txt)' % (vid, OUT, vid))
        return None
    return binp


def run_all(binp, vid, trace_dir, jobs):
    os.makedirs(OUT, exist_ok=True)
    procs = []
    for t in TRACES:
        log = os.path.join(OUT, '%s_%s.txt' % (vid, t))
        if os.path.exists(log) and 'Region of Interest' in io.open(
                log, encoding='utf-8', errors='replace').read() and os.path.getmtime(binp) <= os.path.getmtime(log):
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


VARIANTS_BY_ID = {vid: kn for vid, _, kn in VARIANTS}


def summary():
    base = {t: parse_log('results/task3/lru_t3_%s.txt' % t)
            for t in TRACES if os.path.exists('results/task3/lru_t3_%s.txt' % t)}
    def spd(recs):
        xs = [recs[t]['ipc'] / base[t]['ipc'] for t in TRACES
              if t in recs and base.get(t, {}).get('ipc')]
        return geomean(xs) if xs else 0.0
    # reference standalones from the main Task 3 run
    refs = {}
    for name in ('spp_t3', 'dyn_irrip_t3'):
        recs = {t: parse_log('results/task3/%s_%s.txt' % (name, t))
                for t in TRACES if os.path.exists('results/task3/%s_%s.txt' % (name, t))}
        recs = {t: r for t, r in recs.items() if r}
        if len(recs) == len(TRACES):
            refs[name] = spd(recs)

    print('\n%-10s %9s %9s %9s  %s' % ('variant', 'speedup', 'L2Cmpki', 'cov%', 'note'))
    print('-' * 78)
    best = None
    for vid, note, _ in VARIANTS:
        recs = {t: parse_log(os.path.join(OUT, '%s_%s.txt' % (vid, t))) for t in TRACES}
        recs = {t: r for t, r in recs.items() if r}
        if len(recs) != len(TRACES):
            print('%-10s %9s  (incomplete: %d/3)' % (vid, '-', len(recs))); continue
        sp = spd(recs)
        ml = sum(recs[t]['l2c_load_mpki'] for t in TRACES) / 3.0
        cov = None
        if base:
            mb = sum(base[t]['l1d_load_miss'] for t in TRACES)
            mv = sum(recs[t]['l1d_load_miss'] for t in TRACES)
            cov = 100.0 * (mb - mv) / mb if mb else 0.0
        print('%-10s %9.4f %9.4f %9s  %s' % (vid, sp, ml, ('%.2f' % cov) if cov is not None else '-', note))
        if vid != 'unaware' and (best is None or sp > best[1]):
            best = (vid, sp)
    if refs:
        print('-' * 78)
        for n, s in refs.items():
            print('%-10s %9.4f   (standalone reference)' % (n, s))
    if best and refs:
        print('\nbest aware variant: %s @ %.4f' % best)
        ok = best[1] > refs.get('spp_t3', 9) and best[1] > refs.get('dyn_irrip_t3', 9)
        print('beats BOTH standalones: %s' % ('YES' if ok else 'NO'))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    only = None
    for a in sys.argv[1:]:
        if a.startswith('--only'):
            idx = sys.argv.index(a)
            only = set(sys.argv[idx + 1].split(',')) if '=' not in a else set(a.split('=', 1)[1].split(','))
    if '--list' in sys.argv:
        for vid, note, kn in VARIANTS:
            print('%-10s %s  %s' % (vid, kn, note))
        return
    if '--summary-only' in sys.argv:
        summary(); return
    trace_dir = args[0] if args else '../traces'
    jobs = int(args[1]) if len(args) > 1 else 3
    assert_gcc7_linux()
    try:
        for vid, note, kn in VARIANTS:
            if only and vid not in only:
                continue
            binp = build(vid)
            if binp:
                run_all(binp, vid, trace_dir, jobs)
    finally:
        if os.path.exists(VAR):
            os.remove(VAR)
    summary()


if __name__ == '__main__':
    main()
