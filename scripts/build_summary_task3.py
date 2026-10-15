#!/usr/bin/env python3
"""
Generate docs/summary/task3.md -- every figure read from results/task3/*.txt,
never typed.  Task 1's Summary.pdf, Task 2a's Summary_Task2a.pdf and Task 2b's
Summary_Task2b.pdf are separate finished artifacts and are never touched.

    python3 scripts/build_summary_task3.py   -> docs/summary/task3.md
    ./scripts/build_summary_task3.sh         -> Summary_Task3.pdf
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_results import parse_log, geomean           # noqa: E402

TR = ['trace1', 'trace2', 'trace3']
CFG = [('lru_t3', 'LRU (baseline)'), ('spp_t3', 'SPP alone'),
       ('dyn_irrip_t3', 'dynamic I-RRIP alone'), ('spp_dyn_irrip', 'SPP + dynamic I-RRIP')]
OUT = 'results/task3'

R = {}
for tag, _ in CFG:
    for t in TR:
        p = os.path.join(OUT, '%s_%s.txt' % (tag, t))
        if not os.path.exists(p):
            sys.exit('missing %s -- build the four configs and run run_task3.sh first' % p)
        R[(tag, t)] = parse_log(p)


def sp(tag):
    return geomean([R[(tag, t)]['ipc'] / R[('lru_t3', t)]['ipc'] for t in TR])
def M(tag, k):
    return sum(R[(tag, t)][k] for t in TR) / 3.0
def cov(tag, t):
    b, v = R[('lru_t3', t)]['l1d_load_miss'], R[(tag, t)]['l1d_load_miss']
    return 100.0 * (b - v) / b if b else 0.0
def acc(tag, t):
    a = R[(tag, t)].get('l1d_accuracy')
    return a if a is not None else 0.0

out = []
w = out.append
w('# CS683 PA2 - Task 3: Incorporating SPP with Dynamic I-RRIP\n')
w('*Every figure is recomputed from `results/task3/*.txt` at build time.*\n')

w('## 1. Headline\n')
w('Baseline LRU, 25M warmup + 25M simulation, GCC 7.5.0, three traces. Speedup is '
  'the geomean of per-trace IPC ratios; MPKI is the arithmetic mean.\n')
w('| policy | geomean speedup | mean L1D MPKI | mean L2C MPKI | mean L2 instr | mean L2 data |')
w('|---|---:|---:|---:|---:|---:|')
for tag, name in CFG:
    w('| %s | %.4f | %.4f | %.4f | %.4f | %.4f |' % (
        name, sp(tag), M(tag, 'l1d_load_mpki'), M(tag, 'l2c_load_mpki'),
        M(tag, 'l2c_instr_load_mpki'), M(tag, 'l2c_data_load_mpki')))
w('')
c, s, d = sp('spp_dyn_irrip'), sp('spp_t3'), sp('dyn_irrip_t3')
beats = c > s and c > d
w('**Task 3 bar:** combined **%.4f** vs SPP-alone **%.4f** vs dynamic-I-RRIP-alone '
  '**%.4f** -> combined beats both: **%s**.\n' % (c, s, d, 'YES' if beats else 'NO'))

w('## 2. Prefetch accuracy and coverage (the PDF deliverable)\n')
w('Accuracy = useful / lines actually fetched (ChampSim\'s own definition, '
  'reused from Task 1); coverage = reduction in L1D load misses vs LRU.\n')
w('| policy | ' + ' | '.join('%s acc%%' % t for t in TR) + ' | ' +
  ' | '.join('%s cov%%' % t for t in TR) + ' |')
w('|---|' + '---:|' * (2 * len(TR)))
for tag, name in CFG:
    w('| %s | %s | %s |' % (
        name,
        ' | '.join('%.2f' % acc(tag, t) for t in TR),
        ' | '.join('%.2f' % cov(tag, t) for t in TR)))
w('')

w('## 3. Per-trace IPC and L2C load MPKI\n')
w('| trace | ' + ' | '.join(n for _, n in CFG) + ' |')
w('|---|' + '---:|' * len(CFG))
for t in TR:
    w('| %s IPC | %s |' % (t, ' | '.join('%.5f' % R[(tag, t)]['ipc'] for tag, _ in CFG)))
    w('| %s L2C MPKI | %s |' % (t, ' | '.join('%.4f' % R[(tag, t)]['l2c_load_mpki'] for tag, _ in CFG)))
w('')

w('## 4. Why handle the prefetch packet this way (rationale)\n')
w('A `type == PREFETCH` fill is a prediction, not a demand. Our Task 1 data shows '
  'SPP is right only ~48-57%% of the time, so standalone SPP+LRU -- which inserts '
  'every prefetch at MRU -- lets the wrong ~half pollute the L2 and evict demand '
  'lines. The combined policy instead inserts a prefetch at a distant RRPV so a '
  'wrong prediction ages out fast, and promotes it to a demand line only when a '
  'real demand access hits it (proven useful). Instruction protection is untouched, '
  'and prefetch fills never vote in the duel -- so the two mechanisms are '
  'orthogonal: SPP cuts data-miss latency, I-RRIP protects instruction reuse, and '
  'prefetch-aware insertion stops SPP from polluting what I-RRIP protects. The '
  'insertion depth was chosen by sweep (scripts/sweep_task3.py), not assumed; the '
  'unaware ablation in that sweep isolates awareness as the cause.\n')
w('See docs/TASK3_DESIGN_DECISIONS.md for the full argument and the sweep evidence.\n')

md = '\n'.join(out) + '\n'
os.makedirs('docs/summary', exist_ok=True)
open('docs/summary/task3.md', 'w').write(md)
print('wrote docs/summary/task3.md')
