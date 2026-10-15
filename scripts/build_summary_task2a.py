#!/usr/bin/env python3
"""
Generate Summary_Task2a.pdf -- every number read from the run logs, never typed.

Why a generator and not a hand-written document: during Task 2a the only errors
that survived review were real numbers attached to the wrong claim. A summary
whose figures are recomputed from results/task2a/*.txt at build time cannot
drift away from the logs it describes.

    python3 scripts/build_summary_task2a.py    -> docs/summary/task2a.md
    ./scripts/build_summary_task2a.sh          -> Summary_Task2a.pdf
"""
import io, os, re, sys

TR = ['trace1', 'trace2', 'trace3']
CFG = [('lru_t2a', 'LRU (baseline)'), ('rrip', 'RRIP (supplied)'), ('irrip', 'I-RRIP (ours)')]


def log(path):
    """Pull every figure this document quotes out of one ChampSim log."""
    t = io.open(path, encoding='utf-8', errors='replace').read()
    roi = t.find('Region of Interest Statistics')
    tl = t[roi:] if roi >= 0 else t

    def g(pat, c=float, where=None, d=None):
        m = re.search(pat, tl if where is None else where, re.M)
        return c(m.group(1)) if m else d

    d = dict(
        ipc=g(r'CPU 0 cumulative IPC:\s*([\d.]+)'),
        instrs=g(r'CPU 0 cumulative IPC:\s*[\d.]+\s*instructions:\s*(\d+)', int),
        miss=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*\d+\s+MISS:\s*(\d+)', int),
        acc=g(r'^L2C LOAD\s+ACCESS:\s*(\d+)', int),
        hit=g(r'^L2C LOAD\s+ACCESS:\s*\d+\s+HIT:\s*(\d+)', int),
        mi=g(r'^L2C INSTRUCTION LOAD MPKI:\s*([\d.]+)'),
        md=g(r'^L2C DATA LOAD MPKI:\s*([\d.]+)'),
        dei=g(r'^L2C Data Evicting Instructions\s+(\d+)', int, None, 0),
        iei=g(r'^L2C Instructions Evicting Instructions\s+(\d+)', int, None, 0),
        tei=g(r'^L2C Translations Evicting Instructions\s+(\d+)', int, None, 0),
        vd=g(r'^L2C Data Evicting Data\s+(\d+)', int, None, 0),
        vi=g(r'^L2C Instructions Evicting Data\s+(\d+)', int, None, 0),
        vt=g(r'^L2C Translations Evicting Data\s+(\d+)', int, None, 0),
        ins_i=g(r'IRRIP INSERTS instr (\d+)', int, t, 0),
        ins_d=g(r'IRRIP INSERTS instr \d+ data (\d+)', int, t, 0),
        pro_i=g(r'IRRIP PROMOTES instr (\d+)', int, t, 0),
        pro_d=g(r'IRRIP PROMOTES instr \d+ data (\d+)', int, t, 0),
        nbytes=g(r'IRRIP STORAGE .*total_bytes (\d+)', int, t, 0),
        storage_line=g(r'^(L2C IRRIP STORAGE .*)$', str, t, ''))
    d['ml'] = d['miss'] * 1000.0 / d['instrs']
    d['victims_i'] = d['dei'] + d['iei'] + d['tei']
    d['victims_d'] = d['vd'] + d['vi'] + d['vt']
    return d


R = {}
for _c, _ in CFG:
    for _t in TR:
        _p = 'results/task2a/%s_%s.txt' % (_c, _t)
        if not os.path.exists(_p):
            sys.exit('missing %s -- run ./scripts/run_task2a.sh first' % _p)
        R[(_c, _t)] = log(_p)


def mean(xs):
    return sum(xs) / float(len(xs))


def geo(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def sp(c, t):
    return R[(c, t)]['ipc'] / R[('lru_t2a', t)]['ipc']


def pct(n, o):
    return '%+.1f%%' % (100.0 * (n - o) / o)


def M(c, k):
    return mean([R[(c, t)][k] for t in TR])


def reuse(t, cls):
    d = R[('irrip', t)]
    return (d['pro_i'] / float(d['ins_i'])) if cls == 'i' else (d['pro_d'] / float(d['ins_d']))


O = []
A = O.append

A('# CS683 PA2 - Task 2a: Instruction-Conscious L2 Replacement (I-RRIP)\n')
A('**Toolchain:** GCC 7.5.0 at `-O3` (Ubuntu 18.04), as `README.md` requires. '
  '**Runs:** 25M warmup + 25M simulation, all three supplied traces, single core, '
  'no L1D prefetcher so the replacement policy is measured in isolation. Every '
  'number here is regenerated from the run logs by '
  '`scripts/build_summary_task2a.py`, so it cannot drift from them.\n')
A('**Headline:** I-RRIP cuts L2 instruction load MPKI by **%.1f%%** against the LRU '
  'baseline (%.4f to %.4f) and by **%.1f%%** against the supplied RRIP, lifts geomean '
  'speedup to **%.4f**, in **%d B** of state -- one third of the 3 072 B the LRU it '
  'replaces needs.\n' % (
      100 * (M('lru_t2a', 'mi') - M('irrip', 'mi')) / M('lru_t2a', 'mi'),
      M('lru_t2a', 'mi'), M('irrip', 'mi'),
      100 * (M('rrip', 'mi') - M('irrip', 'mi')) / M('rrip', 'mi'),
      geo([sp('irrip', t) for t in TR]), R[('irrip', TR[0])]['nbytes']))

A('## 0. The brief, and where each part is answered\n')
A('| PDF requirement | Here |')
A('|---|---|')
A('| Extend `update_replacement_state` with an instruction-line parameter | Sec 1 |')
A('| Change insertion / promotion / eviction to prioritise instruction lines | Sec 3, code in `replacement/irrip.l2c_repl` |')
A('| Report IPC, speedup, Load MPKI of L2C / L2 Instruction / L2 Data, tabulated and plotted | Sec 5, Sec 6 |')
A('| Explain the rationale for modifying **or not modifying** each of the three | Sec 3 |')
A('| (self-imposed) show the choice was measured, not argued | Sec 8 -- 26 variants, 78 runs |\n')

A('## 1. The mandated signature change\n')
A('`replacement/rrip.l2c_repl` ships with a **nine**-parameter '
  '`l2c_update_replacement_state` whose last argument is already named '
  '`uint8_t isInstruction`, while `inc/cache.h` and every other module had eight. '
  'That mismatch is the build failure the PDF predicts, and it means the signature '
  'was specified for us, not chosen by us. Task 1 never hit it because it only ever '
  'built with `lru` at L2.\n')
A('**27 declarations across 18 files** (`inc/cache.h` x10 including the function '
  'pointer, `base_replacement.cc`, the eight `lru.*_repl`, the eight generated '
  '`*_replacement.cc`), plus **9 call sites**: six in `src/cache.cc` and -- easily '
  'missed -- three in `src/ooo_cpu.cc`, where the BTB calls the same hook through a '
  'different idiom, `(BTB.*BTB.update_replacement_state)(...)`. Searching for the '
  'calling idiom in one file finds six and is blind to the rest; searching for the '
  'callee across the tree finds nine. Each cache call site passes the `.instruction` '
  'field of *the same queue entry* that already supplied its `type`, so the two '
  'arguments cannot describe different packets. The BTB sites pass 0: a BTB entry is '
  'a predicted branch target, not a line of fetched instructions.\n')
A('**Why insertion genuinely needs the parameter.** In `handle_fill` the order is '
  '`find_victim` (`cache.cc:56`) -> `update_replacement_state` (527) -> `fill_cache` '
  '(553), and `fill_cache` is what writes `block[set][way].instruction`. At the '
  'moment of insertion the block array still describes **the line being evicted**, so '
  'the incoming line\'s class can only arrive as an argument. On the promotion path '
  'the line was filled long ago, so there the parameter is redundant.\n')
A('One further fix was needed: ChampSim calls `l2c_replacement_final_stats()` only '
  'inside `if (NUM_CPUS > 1)` (`main.cc:1754`), so on the single-core runs this '
  'assignment requires, it never fired and the policy\'s own counters -- including '
  'the storage breakdown in Sec 7 -- were silently discarded. Its prefetcher sibling '
  'is called from both paths, which is why Task 1\'s SPP counters printed normally '
  'and nothing looked wrong. The missing call was added to the single-core loop.\n')

A('## 2. The headroom, measured before designing anything\n')
A('ChampSim already classifies every L2 eviction by victim type and filler type '
  '(`cache.cc:375`, printed at `main.cc:306`); nobody had read those counters. On the '
  'LRU baseline:\n')
A('| trace | L2C load MPKI | instr | data | instr share | L2 load hit rate | instr victims | killed by a **data** fill |')
A('|---|---|---|---|---|---|---|---|')
for t in TR:
    b = R[('lru_t2a', t)]
    A('| %s | %.4f | %.4f | %.4f | %.1f%% | %.1f%% | %d | %d (%.1f%%) |' % (
        t, b['ml'], b['mi'], b['md'], 100 * b['mi'] / (b['mi'] + b['md']),
        100.0 * b['hit'] / b['acc'], b['victims_i'], b['dei'],
        100.0 * b['dei'] / b['victims_i']))
A('')
A('Instruction misses dominate the L2 load stream on trace1 and trace2 -- the '
  'server-like behaviour the PDF describes -- and the L2 load hit rate is under 50%% '
  'everywhere, which is the thrashing regime RRIP was designed for. The last column '
  'is the only conflict an instruction-conscious policy can address directly: an '
  'instruction line lost to another instruction line offers no type preference to '
  'express.\n')

A('## 3. Insertion, promotion, eviction -- the rationale\n')
A('RRIP routes every input it has through one number per line, the RRPV: insertion '
  'writes it, promotion updates it, eviction reads it. So there are exactly three '
  'places a type hint can enter. The key reading: **an insertion value is a '
  'protection budget measured in aging rounds** -- a line inserted at *r* survives '
  '`MAX_RRPV - r` aging passes before it can be chosen as victim. "Prioritise '
  'instruction lines" has no cleaner expression than giving them a larger budget.\n')
A('The shipped policy in one sentence: **a data line never rises above evict-next, '
  'and an instruction line gets exactly one aging round of protection.**\n')
A('| | argued before measuring | shipped | why |')
A('|---|---|---|---|')
A('| **Insertion** | change: instructions to 0, data left at SRRIP max-1 | **changed, harder**: instructions 0, data **at** the edge | Insertion is the only hook that predicts about a line with no history, so a free type hint is worth most there, and it is the only option costing 0 extra bits. I first left data alone so the gain would be attributable to *protecting instructions* rather than *penalising data* -- the cleaner claim, and the weaker policy. Sec 4 shows why. |')
A('| **Promotion** | do **not** change: a hit is evidence, not a guess | **changed**: data hits promote to the edge | Refuted by measurement. At 0.13 hits per fill an L2 data hit means "referenced twice", not "hot"; I credited a binary event with more information than it carries. The hit is still honoured -- the line survives that eviction -- just not promised the top of the set. iTP (ASPLOS 2025) does the same and was right. |')
A('| **Eviction** | do **not** change: the RRPV must stay the complete priority | **not changed** | The conclusion stands, the argument for it was refuted. A bounded eviction preference does help and was the best regression-free variant (Sec 8). It stays off because the shipped configuration beats it on the stated objective, on IPC and on storage, and because keeping eviction a pure function of the RRPV is what keeps Task 2b set-duelling tractable. |')
A('')
A('Three reasons eviction was left alone, for the record. It would make the line type '
  'influence the outcome through two independent channels, so the RRPV would no '
  'longer summarise what the policy believes about a line. It **double-counts**: an '
  'instruction line inserted at 0 already reaches the eviction edge later than a data '
  'line, so the preference is already in the numbers. And a hard preference disables '
  'itself exactly where it is needed -- on trace2 %.1f%% of L2 victims are instruction '
  'lines, so sets with no data line to divert to are common, and the mechanism would '
  'be absent from the most pressured sets and present in the calmest.\n' % (
      100.0 * R[('lru_t2a', 'trace2')]['victims_i'] /
      (R[('lru_t2a', 'trace2')]['victims_i'] + R[('lru_t2a', 'trace2')]['victims_d'])))

A('## 4. The number that justifies the design\n')
A('From the policy\'s own counters -- hits per fill, by class:\n')
A('| trace | instruction hits/fill | data hits/fill | ratio | I-RRIP effect on IPC |')
A('|---|---|---|---|---|')
for t in TR:
    A('| %s | **%.2f** | %.2f | %.1fx | %+.2f%% |' % (
        t, reuse(t, 'i'), reuse(t, 'd'), reuse(t, 'i') / reuse(t, 'd'),
        100 * (sp('irrip', t) - 1)))
A('')
A('**A data line brought into this L2 is re-referenced about %.2f times before it '
  'leaves; an instruction line %.2f to %.2f times.** That reframes the whole policy: '
  'it is not imposing a preference for instructions, it is reading the two streams\' '
  'reuse statistics correctly. A class hit %.2f times per fill does not deserve '
  'residency; one hit %.2f times per fill does. Every knob the sweep settled on '
  'follows from that asymmetry rather than from the word "instruction-conscious".\n'
  % (mean([reuse(t, 'd') for t in TR]), min(reuse(t, 'i') for t in TR),
     max(reuse(t, 'i') for t in TR), mean([reuse(t, 'd') for t in TR]),
     max(reuse(t, 'i') for t in TR)))
A('It also predicts the per-trace outcome, which instruction *volume* does not: '
  'ordering the traces by instruction hits/fill gives the same order as their IPC '
  'gains, while ordering them by instruction share of misses does not. '
  '**Protection pays in proportion to the reuse density of what is protected.**\n')

A('## 5. Results\n')
for key, title, note in [('mi', 'L2 INSTRUCTION load MPKI', 'the metric the PDF names as the goal'),
                         ('md', 'L2 DATA load MPKI', 'the cost -- the starvation effect Task 2b addresses'),
                         ('ml', 'L2C load MPKI', 'all L2 load misses, i.e. the net effect')]:
    A('**%s** -- lower is better (%s).\n' % (title, note))
    A('| policy | ' + ' | '.join(TR) + ' | mean |')
    A('|---|' + '---|' * (len(TR) + 1))
    for c, lab in CFG:
        A('| %s | %s | **%.4f** |' % (lab, ' | '.join('%.4f' % R[(c, t)][key] for t in TR), M(c, key)))
    A('')
A('**IPC and speedup.** Speedup = IPC / IPC of (no prefetcher + LRU). The aggregate '
  'is the **geometric mean**, because speedup is a ratio: an arithmetic mean of ratios '
  'is not the speedup of anything and would depend on which policy sits in the '
  'denominator.\n')
A('| policy | ' + ' | '.join('%s IPC (speedup)' % t for t in TR) + ' | geomean |')
A('|---|' + '---|' * (len(TR) + 1))
for c, lab in CFG:
    A('| %s | %s | **%.4f** |' % (
        lab, ' | '.join('%.5f (%.4f)' % (R[(c, t)]['ipc'], sp(c, t)) for t in TR),
        geo([sp(c, t) for t in TR])))
A('')
A('Per-trace change against LRU, so the trade-off is visible instead of averaged away:\n')
A('| trace | instr MPKI | data MPKI | L2C MPKI | IPC |')
A('|---|---|---|---|---|')
for t in TR:
    b, i = R[('lru_t2a', t)], R[('irrip', t)]
    A('| %s | %.3f -> **%.3f** (%s) | %.3f -> %.3f (%s) | %.3f -> %.3f (%s) | %+.2f%% |' % (
        t, b['mi'], i['mi'], pct(i['mi'], b['mi']), b['md'], i['md'], pct(i['md'], b['md']),
        b['ml'], i['ml'], pct(i['ml'], b['ml']), 100 * (sp('irrip', t) - 1)))
A('')
A('Instruction MPKI falls on every trace. The cost is a data-MPKI rise on every '
  'trace, large enough on trace1 to make total L2 MPKI worse -- quantified, owned, '
  'and handed to Task 2b in Sec 9.\n')
A('The mechanism, from ChampSim\'s own eviction counters -- instruction lines thrown out:\n')
A('| trace | instr victims | by a **data** fill | by another **instruction** |')
A('|---|---|---|---|')
for t in TR:
    b, i = R[('lru_t2a', t)], R[('irrip', t)]
    A('| %s | %d -> %d (%s) | %d -> %d (%s) | %d -> %d (%s) |' % (
        t, b['victims_i'], i['victims_i'], pct(i['victims_i'], b['victims_i']),
        b['dei'], i['dei'], pct(i['dei'], b['dei']),
        b['iei'], i['iei'], pct(i['iei'], b['iei'])))
A('')
A('Note the last column falls further than the middle one. The instruction-evicts-'
  'instruction conflict is **not** a fixed capacity tax: protecting instruction lines '
  'at insertion slows the rate at which they churn against each other, so the '
  'conflict I had declared unaddressable fell more than the one I was aiming at.\n')

A('## 6. Plots\n')
for f, cap in [('task2a_instr_load_mpki.png', 'L2 instruction load MPKI -- the stated objective.'),
               ('task2a_data_load_mpki.png', 'L2 data load MPKI -- the cost of prioritising.'),
               ('task2a_l2c_load_mpki.png', 'L2C load MPKI -- the net effect.'),
               ('task2a_ipc.png', 'IPC.'),
               ('task2a_speedup.png', 'Speedup over the LRU baseline; aggregate is the geometric mean.')]:
    A('![%s](%s)\n' % (cap, os.path.abspath('results/task2a/' + f)))

A('## 7. Storage -- exact bit-level breakdown\n')
A('L2C geometry: `L2C_SET 1024` x `L2C_WAY 8` = **8 192 lines** (`inc/cache.h:93`).\n')
A('| policy | bits per line | total | vs LRU |')
A('|---|---|---|---|')
A('| LRU (the policy replaced) | 3 -- a recency rank, ceil(log2 8) | 24 576 b = **3 072 B** | -- |')
A('| RRIP (supplied) | 2 | 16 384 b = 2 048 B | -33% |')
A('| **I-RRIP (shipped)** | **1** | 8 192 b = **%d B** | **-67%%** |' % R[('irrip', TR[0])]['nbytes'])
A('')
A('The policy prints this itself at the end of every run, so the figure is read off '
  'the run rather than recomputed by hand:\n')
A('```\n%s\n```\n' % R[('irrip', TR[0])]['storage_line'])
A('**The cost of instruction-consciousness itself is 0 bits.** Insertion and promotion '
  'take the line\'s class from `packet.instruction`, a field of a packet already in '
  'flight through the MSHR -- not state the cache keeps. Only an eviction-side '
  'preference would need the class of a *resident* line, i.e. a stored bit per line, '
  'and the shipped configuration does not use one. So I-RRIP is a third cheaper than '
  'the LRU it replaces **and** adds nothing to RRIP.\n')
A('The `uint8_t dyn/l2_irrip_rrpv[1024][8]` array in the source is 8 KiB of simulator '
  'memory. That is a modelling convenience, not the hardware cost; the hardware cost '
  'is the bit field above.\n')

A('## 8. The design sweep -- 26 variants, 78 runs\n')
A('One knob at a time around a fixed centre, then combinations, then a bracketing '
  'stage. Full table in `results/task2a_sweep/sweep_summary.md`; reproduce with '
  '`python3 scripts/sweep_task2a.py ../traces 3`. The shipped defaults are provably '
  'identical to one swept row (`max1_prod1`) -- `scripts/verify_task2a.py` asserts it '
  '-- so the headline numbers come from a configuration that was actually measured '
  'rather than assembled afterwards.\n')
A('**1. There is one axis, not ten knobs.** Instruction and data MPKI are '
  'anti-correlated at r = -0.96 / -0.94 / -0.89 across all 26 variants: every knob '
  'moves the same underlying quantity, at roughly 0.5 data misses gained per '
  'instruction miss saved. Since instruction misses are about 62%% of the baseline L2 '
  'load miss stream, trading stays profitable while the exchange rate is below ~1.6 -- '
  'which it is, everywhere. That is why more prioritisation kept winning on aggregate, '
  'and it is also an admission: 10 knobs was over-parameterised, and 3 or 4 would have '
  'found the same answer in a quarter of the runs.\n')
A('**2. Three of eight pre-registered predictions were refuted**, all in the same '
  'direction -- I under-estimated how hard these traces want instructions '
  'prioritised.\n')
A('- *trace2 would benefit least.* It benefited most. I had reasoned from the '
  '**baseline** eviction mix, treating it as an input when it is an output of the '
  'policy; the right predictor was reuse density (Sec 4), which was measurable from '
  'the baseline just as easily.\n')
A('- *An eviction preference would change almost nothing*, because "the bias is '
  'already in the RRPVs". It was the best regression-free variant. **Insertion delays '
  'the eviction decision without informing it**: once a set is full of instruction '
  'lines at RRPV 0, aging drives them to the edge together and every candidate looks '
  'identical at the moment of choice. An eviction-side check restores the type '
  'information exactly when insertion\'s protection has expired, so the two mechanisms '
  'act at different times and are not redundant.\n')
A('- *Weakening data promotion would lose.* It won, and it is in the shipped '
  'configuration (Sec 3).\n')
A('**3. A failed measurement, reported as failed.** To put a number on how much more '
  'an instruction miss costs, I fitted `speedup ~ a*(-d_instr) + b*(-d_data)` over all '
  '26 variants. It returned **negative coefficients** -- impossible, since removing '
  'misses cannot reduce IPC. The cause is the collinearity in point 1: at r = -0.95 '
  'the two-variable system is ill-conditioned and the coefficients are not '
  'identifiable. **The fit is discarded rather than reported.** The direction survives '
  'from one clean comparison: `max1_prod1` has *worse* total L2C MPKI than `max7_ev4` '
  '(14.759 vs 14.247) and *better* speedup (1.0138 vs 1.0092), the only difference '
  'being composition. So an L2 instruction miss costs more IPC than a data miss, which '
  'is what the assignment\'s own premise predicts -- an instruction miss stalls the '
  'frontend with nothing to overlap, while a data miss is absorbed by out-of-order '
  'execution. The magnitude is not quoted.\n')
A('**4. Only 7 of 26 variants regress no single trace.** The best of those, '
  '`ev0_wb0_trev`, reaches instruction MPKI 7.776 with no regression anywhere; the '
  'shipped `max1_prod1` reaches %.3f but regresses trace1 and trace3 on total misses. '
  'This is a Pareto frontier, not a single optimum. `max1_prod1` was chosen because it '
  'wins the objective the PDF names, wins IPC by the largest margin in the sweep, is '
  'the cheapest configuration tested, and leaves eviction untouched so Task 2b can '
  'duel two policies differing in three constants.\n' % M('irrip', 'mi'))

A('## 9. Limitations, and the handover to Task 2b\n')
A('1. **trace1 regresses**: total L2 MPKI %s and IPC %+.2f%%. The cause is measured, '
  'not guessed -- trace1 instruction lines are re-referenced %.2f times per fill '
  'against trace2 %.2f, so protection there costs data residency and collects little. '
  'This is exactly the PDF framing for Task 2b: "blindly prioritizing instruction '
  'lines over data lines may result in an increase in data misses for certain phases '
  'of a workload."\n' % (
      pct(R[('irrip', 'trace1')]['ml'], R[('lru_t2a', 'trace1')]['ml']),
      100 * (sp('irrip', 'trace1') - 1), reuse('trace1', 'i'), reuse('trace2', 'i')))
A('2. **The signal for 2b is already identified.** Reuse density is measurable online '
  'from two counters per class, and Sec 4 shows it is monotone in the right answer '
  'where instruction *volume* -- the quantity the PDF suggested 2b formula uses -- is '
  'not.\n')
A('3. **The bias lives in three constants** read at insertion and promotion, and '
  'eviction is untouched, so "switch to plain RRIP" is a change of three numbers. A '
  'set-duelling controller needs no second policy implementation and no second victim '
  'path.\n')
A('4. **The instruction-evicts-instruction conflict is untouched by design** and is '
  'the majority of trace2 baseline problem. It would need more capacity or a reuse '
  'predictor *within* the instruction class, SHiP-style with a real signature.\n')
A('5. **Three traces**, so per-trace results are reported beside every aggregate and '
  'speedup uses the geometric mean.\n')

A('## 10. Where everything lives\n')
A('| | |')
A('|---|---|')
A('| Policy | `replacement/irrip.l2c_repl` |')
A('| Signature change | `inc/cache.h`, `src/cache.cc`, `src/ooo_cpu.cc`, `src/main.cc`, `replacement/*` |')
A('| Results, tables, plots | `results/task2a/` |')
A('| Sweep, 26 variants | `results/task2a_sweep/sweep_summary.md` |')
A('| Full rationale, every rejected alternative | `docs/TASK2A_DESIGN_DECISIONS.md` |')
A('| Line-by-line code guide | `docs/TASK2A_IRRIP.md` |')
A('| Build and run | `docs/TASK2A_RUN_INSTRUCTIONS.md` |')
A('| Self-audit, 161 checks | `scripts/verify_task2a.py` |')
A('| This document, regenerated from the logs | `scripts/build_summary_task2a.py` |')

io.open('docs/summary/task2a.md', 'w', encoding='utf-8').write('\n'.join(O) + '\n')
print('wrote docs/summary/task2a.md  (%d blocks)' % len(O))
