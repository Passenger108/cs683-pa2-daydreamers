### 8.1 IPC and speedup

| Trace | IPC baseline | IPC ip_stride | IPC SPP | Speedup ip_stride | Speedup SPP |
|---|---|---|---|---|---|
| trace1 | 0.2323 | 0.2335 | 0.2345 | 1.0048 | 1.0091 |
| trace2 | 0.2512 | 0.2513 | 0.2542 | 1.0004 | 1.0123 |
| trace3 | 0.3821 | 0.3829 | 0.3913 | 1.0021 | 1.0241 |
| **geomean** | -- | -- | -- | **1.0024** | **1.0151** |

### 8.2 L1D load MPKI

| Trace | baseline | ip_stride | SPP | SPP reduction vs baseline |
|---|---|---|---|---|
| trace1 | 10.678 | 10.119 | 9.497 | 11.06 % |
| trace2 | 13.538 | 13.438 | 12.990 | 4.05 % |
| trace3 | 3.403 | 3.318 | 2.730 | 19.79 % |
| **average** | **9.206** | **8.958** | **8.405** | |

### 8.3 Prefetch accuracy and L1D coverage

Accuracy is ChampSim's own `ACCURACY` field (`pf_useful / pf_lower_level`); `useful/issued` is given in brackets.

| Trace | acc ip_stride | acc SPP | coverage ip_stride | coverage SPP |
|---|---|---|---|---|
| trace1 | 52.71 % (5.46 %) | 55.60 % (3.09 %) | 5.24 % | 11.06 % |
| trace2 | 38.18 % (2.89 %) | 53.96 % (2.01 %) | 0.74 % | 4.05 % |
| trace3 | 15.99 % (1.36 %) | 48.30 % (1.30 %) | 2.51 % | 19.79 % |
| *equal-weight mean* | 35.63 % | 52.62 % | 2.83 % | 11.63 % |
| **pooled (sum/sum)** | **39.38 %** | **53.35 %** | **2.70 %** | **8.70 %** |

*Pooled is the row to quote.* SPP wins on **every individual trace** as well, so the conclusion does not depend on the choice of aggregate.

### 8.4 SPP internal behaviour

From `l1d_prefetcher_final_stats()`. These are **our** counters, which ChampSim does not reset at the ROI boundary, so unlike every other table here they describe the **whole run (25M warmup + 25M ROI)**.

| Trace | uniform path | non-uniform path | mean windowed usefulness | windows | degree histogram | IP-table hit rate | pattern entries conf>=2 | chains cut by conf |
|---|---|---|---|---|---|---|---|---|
| trace1 | 31.80 % | 68.20 % | 62.85 % | 1486 | d1=87 d2=345 d3=0 d4=347 d5=0 d6=0 d7=0 d8=707 | 67.86 % | 329 / 1024 | 431141 |
| trace2 | 19.07 % | 80.93 % | 66.60 % | 866 | d1=62 d2=189 d3=0 d4=153 d5=0 d6=0 d7=0 d8=462 | 43.44 % | 257 / 1024 | 338200 |
| trace3 | 54.03 % | 45.97 % | 59.82 % | 1001 | d1=134 d2=189 d3=0 d4=232 d5=0 d6=0 d7=0 d8=446 | 86.69 % | 351 / 1024 | 210952 |

### 8.5 Page-confinement check (independent of our code)

`prefetch_line()` in `src/cache.cc` counts cross-page prefetch requests itself, so this is ChampSim auditing us rather than us auditing ourselves.

| Trace | config | cross-page prefetch requests | same-page prefetch requests |
|---|---|---|---|
| trace1 | IP-stride | **0** | 547035 |
| trace1 | SPP | **0** | 1712590 |
| trace2 | IP-stride | **0** | 149721 |
| trace2 | SPP | **0** | 1262232 |
| trace3 | IP-stride | **0** | 363276 |
| trace3 | SPP | **0** | 1652096 |

### 8.6 Run provenance

| Trace | config | warmup instrs | simulated instrs | simulated cycles |
|---|---|---|---|---|
| trace1 | No prefetcher | 25000004 | 25000000 | 107598652 |
| trace1 | IP-stride | 25000004 | 25000000 | 107088310 |
| trace1 | SPP | 25000004 | 25000000 | 106630882 |
| trace2 | No prefetcher | 25000002 | 25000001 | 99538958 |
| trace2 | IP-stride | 25000002 | 25000001 | 99498688 |
| trace2 | SPP | 25000002 | 25000001 | 98328946 |
| trace3 | No prefetcher | 25000002 | 25000001 | 65433974 |
| trace3 | IP-stride | 25000002 | 25000001 | 65297638 |
| trace3 | SPP | 25000002 | 25000001 | 63894785 |
