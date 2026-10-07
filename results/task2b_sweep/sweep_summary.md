# Task 2b knob sweep

Each row: 3 traces, 25M warmup + 25M simulation, GCC 7 `-O3`. Speedup is the
geometric mean against the LRU baseline; MPKIs are arithmetic means.
`% prioritising` is the share of decision windows that chose I-RRIP mode, per
trace -- the column that says whether the selector is reading the right signal.
`switches` is the total across the three traces: a large number means the
selector is thrashing rather than tracking phases.

| grp | variant | question | speedup | L2C MPKI | instr MPKI | data MPKI | % prioritising (t1/t2/t3) | switches | storage (B) |
|---|---|---|---|---|---|---|---|---|---|
| A | `pdf_t15` | PDF formula, threshold 15% | 1.0072 | 14.8774 | 6.5299 | 8.3475 | 99/91/99 | 9 | 2058 |
| A | `pdf_t25` | PDF formula, threshold 25% (the value the PDF suggests) | 1.0056 | 14.9021 | 6.6110 | 8.2912 | 99/90/89 | 10 | 2058 |
| A | `pdf_t35` | PDF formula, threshold 35% | 1.0052 | 14.9244 | 6.6655 | 8.2588 | 96/89/80 | 14 | 2058 |
| A | `pdf_t45` | PDF formula, threshold 45% | 1.0049 | 14.9273 | 6.7793 | 8.1479 | 92/88/67 | 26 | 2058 |
| A | `pdf_t60` | PDF formula, threshold 60% | 1.0067 | 14.4881 | 7.3603 | 7.1277 | 1/81/9 | 23 | 2058 |
| B | `hit_t30` | hit rate, threshold 30% (below all three traces) | 1.0064 | 14.5540 | 7.1687 | 7.3853 | 25/83/33 | 46 | 2058 |
| B | `hit_t40` | hit rate, threshold 40% | 1.0050 | 14.6526 | 7.6845 | 6.9681 | 12/71/17 | 38 | 2058 |
| B | `hit_t45` | hit rate, threshold 45% (shipped default) | 1.0050 | 14.7022 | 7.8427 | 6.8595 | 9/61/12 | 42 | 2058 |
| B | `hit_t55` | hit rate, threshold 55% | 1.0042 | 14.8643 | 8.2711 | 6.5932 | 2/46/11 | 32 | 2058 |
| B | `hit_t70` | hit rate, threshold 70% (above all but trace2) | 1.0003 | 15.8138 | 9.8378 | 5.9760 | 0/0/4 | 4 | 2058 |
| C | `psel_w1` | DIP duel, instruction misses weighted 1 (DIP as published) | 1.0059 | 14.7477 | 7.8044 | 6.9433 | 6/63/32 | 91 | 2058 |
| C | `psel_w2` | DIP duel, instruction misses weighted 2 | 1.0069 | 14.6040 | 7.0660 | 7.5380 | 21/90/73 | 56 | 2058 |
| D | `lead8` | 8 leader sets per group (0.8% of the cache) | 1.0054 | 14.6296 | 7.7139 | 6.9157 | 11/67/5 | 44 | 2058 |
| D | `lead128` | 128 leader sets per group (12.5% of the cache) | 1.0045 | 14.8108 | 8.0242 | 6.7867 | 8/61/15 | 42 | 2058 |
| E | `max7` | 3-bit RRPV instead of 2-bit | 1.0034 | 15.1026 | 8.2600 | 6.8426 | 4/57/12 | 38 | 3082 |
| F | `psel_lead8` | the shipped duel with 8 leader sets per group (1.6% sacrificed) | 1.0068 | 14.5693 | 7.2543 | 7.3150 | 12/83/68 | 73 | 2058 |
| F | `psel_lead16` | the shipped duel with 16 leader sets per group (3.1% sacrificed) | 1.0027 | 15.3713 | 8.8785 | 6.4929 | 18/31/32 | 92 | 2058 |

## Per trace -- and does the row regress anything?

The point of Task 2b is to fix static I-RRIP's regression without giving
back its win. `REGRESSES` marks an L2C load MPKI worse than LRU on at least
one trace. The `static` row is Task 2a's policy, for comparison.

| variant | trace1 L2C | trace1 sp | trace2 L2C | trace2 sp | trace3 L2C | trace3 sp | verdict |
|---|---|---|---|---|---|---|---|
| LRU baseline | 17.696 | 1.0000 | 27.357 | 1.0000 | 3.954 | 1.0000 | - |
| I-RRIP static (2a) | 19.234 | 0.9967 | 21.058 | 1.0384 | 3.985 | 1.0068 | **REGRESSES trace1,trace3** |
| `pdf_t15` | 19.059 | 0.9935 | 21.610 | 1.0256 | 3.964 | 1.0028 | **REGRESSES trace1,trace3** |
| `pdf_t25` | 19.059 | 0.9935 | 21.601 | 1.0252 | 4.047 | 0.9985 | **REGRESSES trace1,trace3** |
| `pdf_t35` | 19.058 | 0.9938 | 21.665 | 1.0243 | 4.050 | 0.9978 | **REGRESSES trace1,trace3** |
| `pdf_t45` | 19.042 | 0.9936 | 21.670 | 1.0232 | 4.070 | 0.9979 | **REGRESSES trace1,trace3** |
| `pdf_t60` | 17.638 | 0.9995 | 21.769 | 1.0221 | 4.057 | 0.9986 | **REGRESSES trace3** |
| `hit_t30` | 17.757 | 0.9977 | 21.798 | 1.0235 | 4.106 | 0.9983 | **REGRESSES trace1,trace3** |
| `hit_t40` | 17.655 | 0.9986 | 22.205 | 1.0183 | 4.097 | 0.9984 | **REGRESSES trace3** |
| `hit_t45` | 17.613 | 0.9990 | 22.396 | 1.0177 | 4.098 | 0.9985 | **REGRESSES trace3** |
| `hit_t55` | 17.615 | 0.9992 | 22.881 | 1.0148 | 4.098 | 0.9985 | **REGRESSES trace3** |
| `hit_t70` | 17.639 | 0.9995 | 25.746 | 1.0026 | 4.057 | 0.9987 | **REGRESSES trace3** |
| `psel_w1` | 17.799 | 0.9993 | 22.431 | 1.0189 | 4.014 | 0.9996 | **REGRESSES trace1,trace3** |
| `psel_w2` | 18.085 | 0.9976 | 21.742 | 1.0232 | 3.985 | 1.0001 | **REGRESSES trace1,trace3** |
| `lead8` | 17.581 | 0.9988 | 22.219 | 1.0189 | 4.089 | 0.9987 | **REGRESSES trace3** |
| `lead128` | 17.592 | 0.9991 | 22.750 | 1.0159 | 4.091 | 0.9986 | **REGRESSES trace3** |
| `max7` | 18.039 | 0.9973 | 23.116 | 1.0154 | 4.153 | 0.9976 | **REGRESSES trace1,trace3** |
| `psel_lead8` | 17.776 | 0.9990 | 21.940 | 1.0229 | 3.992 | 0.9987 | **REGRESSES trace1,trace3** |
| `psel_lead16` | 17.894 | 0.9982 | 24.175 | 1.0107 | 4.046 | 0.9992 | **REGRESSES trace1,trace3** |

## Exact configuration of each row

* `pdf_t15` -- MAX_RRPV 3 | SELECTOR 0 thresh 15 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `pdf_t25` -- MAX_RRPV 3 | SELECTOR 0 thresh 25 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `pdf_t35` -- MAX_RRPV 3 | SELECTOR 0 thresh 35 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `pdf_t45` -- MAX_RRPV 3 | SELECTOR 0 thresh 45 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `pdf_t60` -- MAX_RRPV 3 | SELECTOR 0 thresh 60 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `hit_t30` -- MAX_RRPV 3 | SELECTOR 1 thresh 30 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `hit_t40` -- MAX_RRPV 3 | SELECTOR 1 thresh 40 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `hit_t45` -- MAX_RRPV 3 | SELECTOR 1 thresh 45 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `hit_t55` -- MAX_RRPV 3 | SELECTOR 1 thresh 55 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `hit_t70` -- MAX_RRPV 3 | SELECTOR 1 thresh 70 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `psel_w1` -- MAX_RRPV 3 | SELECTOR 2 thresh 45 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 1
* `psel_w2` -- MAX_RRPV 3 | SELECTOR 2 thresh 45 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `lead8` -- MAX_RRPV 3 | SELECTOR 1 thresh 45 hyst 3 | LEADERS 8 stride 128 | WINDOW 8192 | INSTR_WEIGHT 2
* `lead128` -- MAX_RRPV 3 | SELECTOR 1 thresh 45 hyst 3 | LEADERS 128 stride 8 | WINDOW 8192 | INSTR_WEIGHT 2
* `max7` -- MAX_RRPV 7 | SELECTOR 1 thresh 45 hyst 3 | LEADERS 32 stride 32 | WINDOW 8192 | INSTR_WEIGHT 2
* `psel_lead8` -- MAX_RRPV 3 | SELECTOR 2 thresh 45 hyst 3 | LEADERS 8 stride 128 | WINDOW 8192 | INSTR_WEIGHT 2
* `psel_lead16` -- MAX_RRPV 3 | SELECTOR 2 thresh 45 hyst 3 | LEADERS 16 stride 64 | WINDOW 8192 | INSTR_WEIGHT 2
