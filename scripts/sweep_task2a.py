#!/usr/bin/env python3
"""
CS683 PA2 - Task 2a knob sweep.

Every tunable in replacement/irrip.l2c_repl is a design decision, and a design
decision that was never measured is just an opinion.  This script turns each of
them into an experiment: it rewrites ONE "#define" in a throwaway copy of the
policy, rebuilds, runs all three traces at the PDF's 25M+25M, and tabulates the
result.  One knob at a time, around a fixed centre point, so every row is
attributable to a single change.

How a variant is built
----------------------
The knob block at the top of irrip.l2c_repl is the only part of the file this
script touches: it copies the policy to replacement/irrip_sweep.l2c_repl with
the requested "#define" lines rewritten, then runs

    ./build_champsim.sh no irrip_sweep sw_<id>

Nothing else in the tree is modified, and build_champsim.sh restores the stock
LRU policy when it finishes, so an interrupted sweep cannot leave the repo in a
state where a later build silently picks up sweep settings.

As a cross-check the policy prints its own configuration into every run's log,
and this script reads it back and refuses to tabulate a run whose compiled
configuration does not match what was requested.  That makes it impossible for
a stale binary or a failed rebuild to be reported as a result.

MUST be run inside the GCC 7 container (g++ resolving to g++-7).

usage:
    python3 scripts/sweep_task2a.py [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task2a.py --list
    python3 scripts/sweep_task2a.py --only F,G [TRACE_DIR] [JOBS]
    python3 scripts/sweep_task2a.py --summary-only
"""
import io, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SRC   = 'replacement/irrip.l2c_repl'
VAR   = 'replacement/irrip_sweep.l2c_repl'
OUT   = 'results/task2a_sweep'
TRACES = ['trace1', 'trace2', 'trace3']
N_WARM = N_SIM = 25000000

BINPRE  = 'bin/hashed_perceptron-no-no-no-no-no-no-no-lru-lru-lru-irrip_sweep-lru-lru-lru-lru-1core-'

# The centre point: the shipped I-RRIP defaults.  Every variant below is this
# dictionary with one or two entries changed.
CENTRE = dict(MAX_RRPV=3,
              INSERT_INSTR=0, INSERT_DATA=2, INSERT_TRANSL=2,
              PROMOTE_INSTR=0, PROMOTE_DATA=0, PROMOTE_TRANSL=0,
              EVICT_PREFER_DATA=0, EVICT_SLACK=0,
              WB_PROMOTES=1)

# (group, id, what question this row answers, overrides)
VARIANTS = [
 ('base', 'base', 'the shipped I-RRIP defaults', {}),

 # ---- A: how wide should the RRPV be? -------------------------------------
 # The user asked for the 0..7 range.  0 is excluded by construction (see the
 # comment on IRRIP_MAX_RRPV in the policy); the storage-meaningful widths are
 # 1, 3 and 7 bits-worth.  Note max=1 needs data at 1, not at max-1=0, because
 # max-1=0 would make instruction and data insertion identical, i.e. no bias.
 ('A', 'max1',   '1-bit RRPV: is a single bit of protection enough?',
      dict(MAX_RRPV=1, INSERT_INSTR=0, INSERT_DATA=1, INSERT_TRANSL=1)),
 ('A', 'max7',   '3-bit RRPV: does a longer deadline help?',
      dict(MAX_RRPV=7, INSERT_INSTR=0, INSERT_DATA=6, INSERT_TRANSL=6)),
 ('A', 'max7mid','3-bit RRPV, instructions not pinned at the top',
      dict(MAX_RRPV=7, INSERT_INSTR=2, INSERT_DATA=6, INSERT_TRANSL=6)),

 # ---- B: where should an instruction line be inserted? --------------------
 ('B', 'ins_i1', 'instructions at 1: keep RRPV 0 for proven reuse only',
      dict(INSERT_INSTR=1)),
 ('B', 'ins_i2', 'instructions at 2 = NO bias at all; must reproduce RRIP exactly',
      dict(INSERT_INSTR=2)),

 # ---- C: should data be demoted as well as instructions promoted? ---------
 ('C', 'ins_d3', 'data inserted evict-next: protect instructions by demoting data',
      dict(INSERT_DATA=3)),
 ('C', 'ins_d1', 'data MORE protected than SRRIP (reverse control)',
      dict(INSERT_DATA=1)),

 # ---- D: are address translations frontend-critical too? ------------------
 # 6-10% of instruction-line evictions on these traces are caused by a
 # translation fill, and an instruction page walk stalls the frontend as surely
 # as an instruction miss does.
 ('D', 'tr_instr', 'translations treated like instructions', dict(INSERT_TRANSL=0)),
 ('D', 'tr_evict', 'translations inserted evict-next',       dict(INSERT_TRANSL=3)),

 # ---- E: should promotion be type-aware? ----------------------------------
 # The policy argues promotion should stay type-blind because a hit is evidence
 # rather than a guess.  iTP (ASPLOS'25) disagrees and weakens data promotion.
 # These three rows settle it on our traces instead of by argument.
 ('E', 'pro_d1', 'data hits promote to 1, not 0 (weakened, iTP-style)', dict(PROMOTE_DATA=1)),
 ('E', 'pro_d2', 'data hits promote to 2 (strongly weakened)',          dict(PROMOTE_DATA=2)),
 ('E', 'pro_i1', 'instruction hits promote to 1 (reverse control)',     dict(PROMOTE_INSTR=1)),

 # ---- F: should eviction look at the type bit? ----------------------------
 # Default is no.  Slack 0 = "same candidates RRIP would pick from, prefer a
 # data one"; slack 1-2 = "evict a data line that is not yet due to spare an
 # instruction line that is" (xPTP's bounded diversion).
 ('F', 'ev_s0', 'eviction prefers data, no slack',   dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0)),
 ('F', 'ev_s1', 'eviction prefers data, slack 1',    dict(EVICT_PREFER_DATA=1, EVICT_SLACK=1)),
 ('F', 'ev_s2', 'eviction prefers data, slack 2',    dict(EVICT_PREFER_DATA=1, EVICT_SLACK=2)),

 # ---- G: does a writeback hit deserve a promotion? ------------------------
 # LRU says no ("writeback hit does not update LRU state"); the supplied RRIP
 # says yes. We keep RRIP's answer so the comparison is clean, and measure it.
 ('G', 'wb0', 'writeback hits do not promote (LRU\'s view)', dict(WB_PROMOTES=0)),

 # ======================= STAGE 2 ========================================
 # Stage 1 produced two findings that it could not itself resolve:
 #
 #  (a) In EVERY group the most aggressive setting was best on the 3-trace
 #      aggregate. "The most extreme value I tried won" is not a stopping
 #      point -- the turning point has not been bracketed. Group I pushes
 #      past Stage 1's reach: slack is capped below maxRRPV, so slack > 2
 #      needs a 3-bit RRPV.
 #  (b) Every knob moves the SAME single axis (how hard to favour
 #      instructions) at a near-constant exchange rate of ~0.5 data misses
 #      per instruction miss saved. Whether two moderate knobs compose or
 #      merely slide to the same point on that axis is untested. Group H
 #      combines the knobs that each helped WITHOUT regressing trace1.
 #
 # Group H -- do the non-regressing moderate knobs compose?
 ('H', 'ev0_prod2', 'eviction preference + weakened data promotion',
      dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0, PROMOTE_DATA=2)),
 ('H', 'ev0_wb0', 'eviction preference + no writeback promotion',
      dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0, WB_PROMOTES=0)),
 ('H', 'ev0_trev', 'eviction preference + translations evict-next',
      dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0, INSERT_TRANSL=3)),
 # The three knobs that each improved every metric WITHOUT regressing any
 # single trace in Stage 1 were ev_s0, wb0 and tr_evict.  This row is the
 # leading candidate for the shipped configuration, so it matters most.
 ('H', 'ev0_wb0_trev', 'all three CLEAN (non-regressing) winners together',
      dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0, WB_PROMOTES=0, INSERT_TRANSL=3)),
 ('H', 'ev0_prod2_wb0', 'ev_s0 + wb0 + weakened data promotion (pro_d2 alone regressed trace1)',
      dict(EVICT_PREFER_DATA=1, EVICT_SLACK=0, PROMOTE_DATA=2, WB_PROMOTES=0)),

 # Group I -- bracket the far end, and squeeze the cheapest configuration
 ('I', 'max7_ev4', '3-bit RRPV, eviction slack 4 (beyond Stage 1 reach)',
      dict(MAX_RRPV=7, INSERT_INSTR=0, INSERT_DATA=6, INSERT_TRANSL=6,
           EVICT_PREFER_DATA=1, EVICT_SLACK=4)),
 ('I', 'max7_ev6', '3-bit RRPV, eviction slack 6 (near-absolute preference)',
      dict(MAX_RRPV=7, INSERT_INSTR=0, INSERT_DATA=6, INSERT_TRANSL=6,
           EVICT_PREFER_DATA=1, EVICT_SLACK=6)),
 ('I', 'max1_ev0', '1-bit RRPV + eviction preference: best result per bit?',
      dict(MAX_RRPV=1, INSERT_INSTR=0, INSERT_DATA=1, INSERT_TRANSL=1,
           EVICT_PREFER_DATA=1, EVICT_SLACK=0)),
 ('I', 'max1_prod1', '1-bit RRPV + weakened data promotion',
      dict(MAX_RRPV=1, INSERT_INSTR=0, INSERT_DATA=1, INSERT_TRANSL=1,
           PROMOTE_DATA=1)),
]


# --------------------------------------------------------------------------
def write_variant(knobs):
    """Copy the policy, pinning EVERY knob to CENTRE plus this variant's overrides.

    It used to rewrite only the overrides and let the rest inherit whatever the
    shipped source happened to say.  That silently broke the moment Task 2a's
    chosen configuration changed the default MAX_RRPV from 3 to 1: ten variants
    were defined against a MAX_RRPV=3 centre without restating it, so they
    inherited 1 and then failed their own static_asserts (INSERT_INSTR=2 with a
    maximum of 1, EVICT_SLACK=2 with a maximum of 1, and so on).  The sweep had
    stopped being reproducible from the current source, which is exactly the
    kind of silent rot the identity check downstream exists to catch.

    Pinning all ten makes each variant a complete, self-contained
    specification, independent of whatever the shipped default is today.
    """
    full = dict(CENTRE)
    full.update(knobs)
    t = io.open(SRC, encoding='utf-8').read()
    for k, v in full.items():
        pat = re.compile(r'^#define IRRIP_%s .*$' % re.escape(k), re.M)
        if not pat.search(t):
            raise SystemExit('knob IRRIP_%s not found in %s' % (k, SRC))
        t = pat.sub('#define IRRIP_%s %d' % (k, v), t)
    io.open(VAR, 'w', encoding='utf-8').write(t)


def assert_gcc7_linux():
    """Refuse to run outside the GCC 7 Linux container.

    The first time this sweep was run it was launched on the macOS host, so
    every variant was built by Apple clang into a Mach-O binary.  Those runs
    complete and look perfectly normal, but the simulated counters differ from
    the GCC 7 build by up to 3.8% on trace2 (measured with an identical
    policy), which is the same order as the knob effects being measured -- so
    the whole sweep was unusable and had to be thrown away.  Hence this gate.
    """
    if sys.platform != 'linux':
        raise SystemExit(
            'REFUSING TO RUN: platform is %r, not Linux.\n'
            'This sweep must run inside the GCC 7 container. A macOS/clang build\n'
            'produces different simulated counters and its numbers cannot be\n'
            'compared with the GCC 7 results.' % sys.platform)
    try:
        v = subprocess.run(['g++', '--version'], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).stdout.decode('utf-8', 'replace')
    except OSError:
        raise SystemExit('REFUSING TO RUN: no g++ on PATH.')
    if not re.search(r'\b7\.\d+\.\d+', v):
        raise SystemExit(
            'REFUSING TO RUN: g++ is not version 7.x --\n  %s\n'
            'ChampSim deadlocks under g++ 11 at -O3 and gives different counters\n'
            'under clang. Use update-alternatives to select g++-7.'
            % v.strip().split('\n')[0])
    print('toolchain OK: %s' % v.strip().split('\n')[0])


def build(vid):
    print('  building sw_%s ...' % vid, flush=True)
    r = subprocess.run(['./build_champsim.sh', 'no', 'irrip_sweep', 'sw_' + vid],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = r.stdout.decode('utf-8', 'replace')
    binp = BINPRE + 'sw_' + vid
    if r.returncode != 0 or not os.path.exists(binp):
        io.open(os.path.join(OUT, 'BUILD_FAIL_%s.txt' % vid), 'w',
                encoding='utf-8').write(log)
        print('  BUILD FAILED for %s (see %s/BUILD_FAIL_%s.txt)' % (vid, OUT, vid))
        return None
    return binp


def run_all(binp, vid, trace_dir, jobs):
    procs = []
    for t in TRACES:
        log = os.path.join(OUT, '%s_%s.txt' % (vid, t))
        if os.path.exists(log) and 'Region of Interest' in io.open(log, encoding='utf-8', errors='replace').read():
            print('    [skip] %s' % log)
            continue
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


# ---------------------------------------------------------------- summary ----
def grab(text, pat, cast=float, default=None):
    m = re.search(pat, text, re.M)
    return cast(m.group(1)) if m else default


def read_log(path):
    t = io.open(path, encoding='utf-8', errors='replace').read()
    roi = t.find('Region of Interest Statistics')
    if roi < 0:
        return None
    tail = t[roi:]
    d = {}
    d['ipc']     = grab(tail, r'CPU 0 cumulative IPC:\s*([\d.]+)')
    d['instrs']  = grab(tail, r'CPU 0 cumulative IPC:\s*[\d.]+\s*instructions:\s*(\d+)', int)
    d['miss']    = grab(tail, r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*\d+\s+MISS:\s*(\d+)', int)
    d['m_instr'] = grab(tail, r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)')
    d['m_data']  = grab(tail, r'^L2C DATA LOAD MPKI:\s*([\d.]+)')
    d['dei']     = grab(tail, r'^L2C Data Evicting Instructions\s+(\d+)', int, 0)
    d['evpref']  = grab(t,    r'IRRIP EVICT PREF FIRED (\d+)', int, 0)
    d['bytes']   = grab(t,    r'IRRIP STORAGE .*total_bytes (\d+)', int, 0)
    d['cfg']     = grab(t,    r'^L2C I-RRIP config\s+(.*)$', str, '')
    if d['ipc'] is None or d['miss'] is None:
        return None
    d['m_l2c'] = d['miss'] * 1000.0 / d['instrs']
    return d


def expected_cfg(knobs):
    k = dict(CENTRE); k.update(knobs)
    return ('MAX_RRPV %d | INSERT instr %d data %d transl %d | '
            'PROMOTE instr %d data %d transl %d | '
            'EVICT_PREFER_DATA %d slack %d | WB_PROMOTES %d') % (
        k['MAX_RRPV'], k['INSERT_INSTR'], k['INSERT_DATA'], k['INSERT_TRANSL'],
        k['PROMOTE_INSTR'], k['PROMOTE_DATA'], k['PROMOTE_TRANSL'],
        k['EVICT_PREFER_DATA'], k['EVICT_SLACK'], k['WB_PROMOTES'])


def geomean(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def summarise(selected):
    # Speedup denominator: the LRU baseline from the main Task 2a run.
    base = {}
    for t in TRACES:
        p = 'results/task2a/lru_t2a_%s.txt' % t
        if os.path.exists(p):
            d = read_log(p)
            if d:
                base[t] = d['ipc']
    if len(base) < len(TRACES):
        print('note: results/task2a/lru_t2a_*.txt incomplete -- speedup column '
              'will be blank. Run ./scripts/run_task2a.sh first.')

    rows, bad = [], []
    for grp, vid, desc, knobs in selected:
        per = {}
        for t in TRACES:
            p = os.path.join(OUT, '%s_%s.txt' % (vid, t))
            if os.path.exists(p):
                d = read_log(p)
                if d:
                    per[t] = d
        if len(per) < len(TRACES):
            continue
        # refuse to report a run whose compiled config is not what we asked for
        want = expected_cfg(knobs)
        got = per[TRACES[0]]['cfg'].strip()
        if got and got != want:
            bad.append((vid, want, got)); continue
        sp = ([per[t]['ipc'] / base[t] for t in TRACES] if len(base) == len(TRACES) else None)
        rows.append(dict(
            grp=grp, vid=vid, desc=desc, per=per,
            sp_per=({t: per[t]['ipc'] / base[t] for t in TRACES} if len(base) == len(TRACES) else None),
            speedup=(geomean(sp) if sp else None),
            m_l2c=sum(per[t]['m_l2c'] for t in TRACES) / 3.0,
            m_instr=sum(per[t]['m_instr'] for t in TRACES) / 3.0,
            m_data=sum(per[t]['m_data'] for t in TRACES) / 3.0,
            dei=sum(per[t]['dei'] for t in TRACES),
            evpref=sum(per[t]['evpref'] for t in TRACES),
            bytes=per[TRACES[0]]['bytes'],
            cfg=got))

    if bad:
        print('\n!! these variants were SKIPPED: compiled config != requested config')
        for vid, want, got in bad:
            print('   %s\n     wanted: %s\n     got   : %s' % (vid, want, got))

    out = ['# Task 2a knob sweep\n',
           'One knob at a time around the shipped I-RRIP defaults.',
           'Each row: 3 traces, 25M warmup + 25M simulation, GCC 7 `-O3`.\n',
           'Columns: speedup is the **geometric mean** over the three traces',
           'against the LRU baseline (`results/task2a/lru_t2a_*`); the MPKIs are',
           'arithmetic means; `data->instr` is the total over the three traces of',
           "ChampSim's \"Data Evicting Instructions\" counter, i.e. the conflict",
           'this policy exists to reduce; `storage` is the policy\'s own bit',
           'accounting in bytes.\n',
           '| grp | variant | question | speedup | L2C MPKI | instr MPKI | data MPKI | data->instr | evict-pref fired | storage (B) |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        out.append('| %s | `%s` | %s | %s | %.4f | %.4f | %.4f | %d | %d | %d |' % (
            r['grp'], r['vid'], r['desc'],
            ('%.4f' % r['speedup']) if r['speedup'] else '-',
            r['m_l2c'], r['m_instr'], r['m_data'], r['dei'], r['evpref'], r['bytes']))
    # ---- per-trace table -------------------------------------------------
    # The 3-trace mean above hid a real regression once: the most aggressive
    # variants looked best on aggregate while making trace1 WORSE than plain
    # LRU, because their whole gain came from trace2.  An aggregate that can
    # conceal a regression is a misleading summary, so every row is also
    # broken out per trace, with an explicit REGRESSES flag.
    bl = {}
    for t_ in TRACES:
        p_ = 'results/task2a/lru_t2a_%s.txt' % t_
        if os.path.exists(p_):
            d_ = read_log(p_)
            if d_:
                bl[t_] = d_
    out.append('\n## Per trace -- does the row regress any single trace?\n')
    if len(bl) < len(TRACES):
        out.append('_(LRU baseline logs incomplete; run ./scripts/run_task2a.sh)_\n')
    else:
        out.append('`instr` and `L2C` are MPKI (lower better); `sp` is speedup vs LRU on that')
        out.append('trace. **REGRESSES** marks a row whose L2C load MPKI is worse than LRU on')
        out.append('at least one trace -- i.e. a row whose aggregate win is paid for by a loss')
        out.append('somewhere. A configuration that regresses a trace is not a Pareto')
        out.append('improvement and should not be shipped on the strength of its mean alone.\n')
        hdr = '| variant |'
        for t_ in TRACES:
            hdr += ' %s instr | %s L2C | %s sp |' % (t_, t_, t_)
        out.append(hdr + ' verdict |')
        out.append('|---|' + '---|' * (3 * len(TRACES) + 1))
        b = '| LRU baseline |'
        for t_ in TRACES:
            b += ' %.3f | %.3f | 1.0000 |' % (bl[t_]['m_instr'], bl[t_]['m_l2c'])
        out.append(b + ' - |')
        for r in rows:
            if not r.get('sp_per'):
                continue
            line = '| `%s` |' % r['vid']
            worse = []
            for t_ in TRACES:
                d_ = r['per'][t_]
                line += ' %.3f | %.3f | %.4f |' % (d_['m_instr'], d_['m_l2c'], r['sp_per'][t_])
                if d_['m_l2c'] > bl[t_]['m_l2c'] * 1.001:   # 0.1% tolerance
                    worse.append(t_)
            out.append(line + (' **REGRESSES %s** |' % ','.join(worse) if worse else ' clean |'))
        out.append('')

    out.append('\n## Exact configuration of each row\n')
    for r in rows:
        out.append('* `%s` -- %s' % (r['vid'], r['cfg']))
    p = os.path.join(OUT, 'sweep_summary.md')
    io.open(p, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('\nwrote %s  (%d variants tabulated)' % (p, len(rows)))


# ------------------------------------------------------------------- main ----
def main():
    args = sys.argv[1:]
    only = None
    summary_only = False
    rest = []
    i = 0
    while i < len(args):
        if args[i] == '--list':
            for grp, vid, desc, knobs in VARIANTS:
                print('  [%s] %-9s %s' % (grp, vid, desc))
                print('              %s' % expected_cfg(knobs))
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
        print('%d variant(s) x %d traces = %d simulations, plus %d rebuilds.'
              % (len(selected), len(TRACES), len(selected) * len(TRACES), len(selected)))
        print('Each rebuild is a full `make clean` + `make`, so budget for that.\n')
        for n, (grp, vid, desc, knobs) in enumerate(selected, 1):
            print('[%d/%d] %s  (%s)' % (n, len(selected), vid, desc))
            done = all(os.path.exists(os.path.join(OUT, '%s_%s.txt' % (vid, t)))
                       and 'Region of Interest' in io.open(
                           os.path.join(OUT, '%s_%s.txt' % (vid, t)),
                           encoding='utf-8', errors='replace').read()
                       for t in TRACES)
            if done:
                print('  all three traces already complete, skipping build')
                continue
            write_variant(knobs)
            binp = build(vid)
            if binp:
                run_all(binp, vid, trace_dir, jobs)
        if os.path.exists(VAR):
            os.remove(VAR)   # leave no half-configured policy behind

    # Always tabulate EVERY variant whose logs exist, not just the ones this
    # invocation ran.  Passing `selected` here meant that running one group
    # (e.g. --only H,I) rewrote sweep_summary.md with only that group's rows
    # and silently discarded every earlier row -- turning a resumable sweep
    # into one that destroys its own history.  summarise() already skips
    # variants whose three logs are not all present, so this is safe.
    summarise(VARIANTS)


if __name__ == '__main__':
    main()
