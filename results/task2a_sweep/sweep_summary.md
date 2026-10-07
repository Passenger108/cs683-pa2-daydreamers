# Task 2a knob sweep

One knob at a time around the shipped I-RRIP defaults.
Each row: 3 traces, 25M warmup + 25M simulation, GCC 7 `-O3`.

Columns: speedup is the **geometric mean** over the three traces
against the LRU baseline (`results/task2a/lru_t2a_*`); the MPKIs are
arithmetic means; `data->instr` is the total over the three traces of
ChampSim's "Data Evicting Instructions" counter, i.e. the conflict
this policy exists to reduce; `storage` is the policy's own bit
accounting in bytes.

| grp | variant | question | speedup | L2C MPKI | instr MPKI | data MPKI | data->instr | evict-pref fired | storage (B) |
|---|---|---|---|---|---|---|---|---|---|
| base | `base` | the shipped I-RRIP defaults | 1.0035 | 15.4645 | 9.0846 | 6.3799 | 252103 | 0 | 2048 |
| A | `max1` | 1-bit RRPV: is a single bit of protection enough? | 1.0089 | 14.4305 | 7.0274 | 7.4031 | 213128 | 0 | 1024 |
| A | `max7` | 3-bit RRPV: does a longer deadline help? | 1.0044 | 15.2352 | 8.6631 | 6.5721 | 241129 | 0 | 3072 |
| A | `max7mid` | 3-bit RRPV, instructions not pinned at the top | 1.0047 | 15.0099 | 8.5924 | 6.4175 | 237474 | 0 | 3072 |
| B | `ins_i1` | instructions at 1: keep RRPV 0 for proven reuse only | 1.0030 | 15.4237 | 9.2381 | 6.1856 | 251781 | 0 | 2048 |
| B | `ins_i2` | instructions at 2 = NO bias at all; must reproduce RRIP exactly | 1.0004 | 15.8080 | 9.8467 | 5.9613 | 258275 | 0 | 2048 |
| C | `ins_d3` | data inserted evict-next: protect instructions by demoting data | 1.0077 | 14.8496 | 7.3935 | 7.4562 | 220531 | 0 | 2048 |
| C | `ins_d1` | data MORE protected than SRRIP (reverse control) | 1.0019 | 15.7641 | 9.5581 | 6.2059 | 261789 | 0 | 2048 |
| D | `tr_instr` | translations treated like instructions | 1.0030 | 15.7385 | 9.2809 | 6.4576 | 256960 | 0 | 2048 |
| D | `tr_evict` | translations inserted evict-next | 1.0037 | 15.2123 | 8.8677 | 6.3447 | 246242 | 0 | 2048 |
| E | `pro_d1` | data hits promote to 1, not 0 (weakened, iTP-style) | 1.0050 | 15.1668 | 8.5825 | 6.5843 | 246433 | 0 | 2048 |
| E | `pro_d2` | data hits promote to 2 (strongly weakened) | 1.0058 | 14.9673 | 8.1930 | 6.7743 | 237656 | 0 | 2048 |
| E | `pro_i1` | instruction hits promote to 1 (reverse control) | 1.0030 | 15.7844 | 9.4920 | 6.2923 | 263750 | 0 | 2048 |
| F | `ev_s0` | eviction prefers data, no slack | 1.0058 | 14.9525 | 8.3674 | 6.5852 | 243537 | 1978457 | 3072 |
| F | `ev_s1` | eviction prefers data, slack 1 | 1.0089 | 14.2819 | 6.5475 | 7.7344 | 201649 | 2620746 | 3072 |
| F | `ev_s2` | eviction prefers data, slack 2 | 1.0093 | 14.2800 | 6.3362 | 7.9439 | 191728 | 2710103 | 3072 |
| G | `wb0` | writeback hits do not promote (LRU's view) | 1.0052 | 14.9821 | 8.5441 | 6.4380 | 245124 | 0 | 2048 |
| H | `ev0_prod2` | eviction preference + weakened data promotion | 1.0073 | 14.6116 | 7.6901 | 6.9215 | 230896 | 2038660 | 3072 |
| H | `ev0_wb0` | eviction preference + no writeback promotion | 1.0071 | 14.5886 | 7.9528 | 6.6359 | 236838 | 1979958 | 3072 |
| H | `ev0_trev` | eviction preference + translations evict-next | 1.0058 | 14.7489 | 8.1852 | 6.5637 | 238293 | 2004978 | 3072 |
| H | `ev0_wb0_trev` | all three CLEAN (non-regressing) winners together | 1.0069 | 14.3841 | 7.7764 | 6.6077 | 231212 | 2004283 | 3072 |
| H | `ev0_prod2_wb0` | ev_s0 + wb0 + weakened data promotion (pro_d2 alone regressed trace1) | 1.0075 | 14.5943 | 7.6557 | 6.9386 | 230405 | 2043193 | 3072 |
| I | `max7_ev4` | 3-bit RRPV, eviction slack 4 (beyond Stage 1 reach) | 1.0092 | 14.2471 | 6.3987 | 7.8484 | 194909 | 2670152 | 4096 |
| I | `max7_ev6` | 3-bit RRPV, eviction slack 6 (near-absolute preference) | 1.0099 | 14.3386 | 6.2801 | 8.0585 | 187115 | 2750195 | 4096 |
| I | `max1_ev0` | 1-bit RRPV + eviction preference: best result per bit? | 1.0091 | 14.2657 | 6.5141 | 7.7516 | 200681 | 2631426 | 2048 |
| I | `max1_prod1` | 1-bit RRPV + weakened data promotion | 1.0138 | 14.7590 | 6.2219 | 8.5371 | 182952 | 0 | 1024 |

## Per trace -- does the row regress any single trace?

`instr` and `L2C` are MPKI (lower better); `sp` is speedup vs LRU on that
trace. **REGRESSES** marks a row whose L2C load MPKI is worse than LRU on
at least one trace -- i.e. a row whose aggregate win is paid for by a loss
somewhere. A configuration that regresses a trace is not a Pareto
improvement and should not be shipped on the strength of its mean alone.

| variant | trace1 instr | trace1 L2C | trace1 sp | trace2 instr | trace2 L2C | trace2 sp | trace3 instr | trace3 L2C | trace3 sp | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| LRU baseline | 10.338 | 17.696 | 1.0000 | 18.853 | 27.357 | 1.0000 | 1.124 | 3.954 | 1.0000 | - |
| `base` | 10.106 | 17.663 | 0.9996 | 16.072 | 24.785 | 1.0111 | 1.076 | 3.946 | 0.9999 | clean |
| `max1` | 9.564 | 18.547 | 0.9974 | 10.626 | 20.761 | 1.0297 | 0.892 | 3.983 | 0.9998 | **REGRESSES trace1,trace3** |
| `max7` | 9.930 | 17.746 | 0.9991 | 15.024 | 24.008 | 1.0144 | 1.035 | 3.951 | 0.9997 | **REGRESSES trace1** |
| `max7mid` | 9.997 | 17.611 | 0.9994 | 14.713 | 23.448 | 1.0153 | 1.067 | 3.971 | 0.9996 | **REGRESSES trace3** |
| `ins_i1` | 10.202 | 17.531 | 1.0000 | 16.392 | 24.759 | 1.0095 | 1.121 | 3.982 | 0.9995 | **REGRESSES trace3** |
| `ins_i2` | 10.562 | 17.639 | 0.9995 | 17.781 | 25.746 | 1.0026 | 1.197 | 4.039 | 0.9991 | **REGRESSES trace3** |
| `ins_d3` | 9.643 | 18.636 | 0.9972 | 11.622 | 21.897 | 1.0262 | 0.915 | 4.015 | 1.0000 | **REGRESSES trace1,trace3** |
| `ins_d1` | 10.237 | 17.599 | 0.9999 | 17.335 | 25.755 | 1.0061 | 1.103 | 3.938 | 0.9998 | clean |
| `tr_instr` | 10.169 | 17.808 | 0.9995 | 16.581 | 25.429 | 1.0095 | 1.093 | 3.979 | 1.0000 | **REGRESSES trace1,trace3** |
| `tr_evict` | 10.045 | 17.560 | 0.9987 | 15.493 | 24.150 | 1.0128 | 1.065 | 3.927 | 0.9995 | clean |
| `pro_d1` | 9.987 | 17.720 | 0.9995 | 14.730 | 23.874 | 1.0154 | 1.031 | 3.906 | 1.0002 | **REGRESSES trace1** |
| `pro_d2` | 9.862 | 17.915 | 0.9988 | 13.746 | 23.124 | 1.0181 | 0.971 | 3.863 | 1.0006 | **REGRESSES trace1** |
| `pro_i1` | 10.280 | 17.801 | 0.9994 | 17.093 | 25.582 | 1.0098 | 1.103 | 3.970 | 0.9999 | **REGRESSES trace1,trace3** |
| `ev_s0` | 9.955 | 17.698 | 0.9993 | 14.107 | 23.231 | 1.0185 | 1.041 | 3.928 | 0.9997 | clean |
| `ev_s1` | 9.377 | 18.668 | 0.9951 | 9.421 | 20.211 | 1.0319 | 0.845 | 3.967 | 1.0002 | **REGRESSES trace1,trace3** |
| `ev_s2` | 9.252 | 18.879 | 0.9937 | 8.959 | 20.008 | 1.0334 | 0.798 | 3.954 | 1.0013 | **REGRESSES trace1** |
| `wb0` | 9.912 | 17.673 | 0.9991 | 14.742 | 23.439 | 1.0159 | 0.979 | 3.834 | 1.0006 | clean |
| `ev0_prod2` | 9.739 | 18.029 | 0.9982 | 12.388 | 21.955 | 1.0234 | 0.944 | 3.852 | 1.0005 | **REGRESSES trace1** |
| `ev0_wb0` | 9.795 | 17.758 | 0.9990 | 13.112 | 22.184 | 1.0219 | 0.951 | 3.823 | 1.0005 | **REGRESSES trace1** |
| `ev0_trev` | 9.899 | 17.613 | 0.9983 | 13.627 | 22.723 | 1.0197 | 1.029 | 3.910 | 0.9995 | clean |
| `ev0_wb0_trev` | 9.733 | 17.681 | 0.9982 | 12.660 | 21.677 | 1.0228 | 0.937 | 3.795 | 0.9999 | clean |
| `ev0_prod2_wb0` | 9.729 | 18.058 | 0.9982 | 12.304 | 21.877 | 1.0238 | 0.935 | 3.848 | 1.0006 | **REGRESSES trace1** |
| `max7_ev4` | 9.301 | 18.776 | 0.9944 | 9.080 | 20.010 | 1.0325 | 0.814 | 3.956 | 1.0009 | **REGRESSES trace1** |
| `max7_ev6` | 9.209 | 18.951 | 0.9932 | 8.867 | 20.125 | 1.0344 | 0.764 | 3.940 | 1.0027 | **REGRESSES trace1** |
| `max1_ev0` | 9.373 | 18.688 | 0.9953 | 9.324 | 20.135 | 1.0324 | 0.845 | 3.974 | 1.0000 | **REGRESSES trace1,trace3** |
| `max1_prod1` | 9.237 | 19.234 | 0.9967 | 8.715 | 21.058 | 1.0384 | 0.713 | 3.985 | 1.0068 | **REGRESSES trace1,trace3** |


## Exact configuration of each row

* `base` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `max1` -- MAX_RRPV 1 | INSERT instr 0 data 1 transl 1 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `max7` -- MAX_RRPV 7 | INSERT instr 0 data 6 transl 6 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `max7mid` -- MAX_RRPV 7 | INSERT instr 2 data 6 transl 6 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `ins_i1` -- MAX_RRPV 3 | INSERT instr 1 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `ins_i2` -- MAX_RRPV 3 | INSERT instr 2 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `ins_d3` -- MAX_RRPV 3 | INSERT instr 0 data 3 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `ins_d1` -- MAX_RRPV 3 | INSERT instr 0 data 1 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `tr_instr` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 0 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `tr_evict` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 3 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `pro_d1` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 1 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `pro_d2` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 2 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `pro_i1` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 1 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
* `ev_s0` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 1
* `ev_s1` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 1 | WB_PROMOTES 1
* `ev_s2` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 2 | WB_PROMOTES 1
* `wb0` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 0
* `ev0_prod2` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 2 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 1
* `ev0_wb0` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 0
* `ev0_trev` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 3 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 1
* `ev0_wb0_trev` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 3 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 0
* `ev0_prod2_wb0` -- MAX_RRPV 3 | INSERT instr 0 data 2 transl 2 | PROMOTE instr 0 data 2 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 0
* `max7_ev4` -- MAX_RRPV 7 | INSERT instr 0 data 6 transl 6 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 4 | WB_PROMOTES 1
* `max7_ev6` -- MAX_RRPV 7 | INSERT instr 0 data 6 transl 6 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 6 | WB_PROMOTES 1
* `max1_ev0` -- MAX_RRPV 1 | INSERT instr 0 data 1 transl 1 | PROMOTE instr 0 data 0 transl 0 | EVICT_PREFER_DATA 1 slack 0 | WB_PROMOTES 1
* `max1_prod1` -- MAX_RRPV 1 | INSERT instr 0 data 1 transl 1 | PROMOTE instr 0 data 1 transl 0 | EVICT_PREFER_DATA 0 slack 0 | WB_PROMOTES 1
