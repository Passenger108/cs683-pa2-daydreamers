### 8.1 IPC and speedup

| Trace | IPC baseline | IPC ip_stride | IPC SPP | Speedup ip_stride | Speedup SPP |
|---|---|---|---|---|---|
| trace1 | 0.2323 | 0.2335 | 0.2345 | 1.0048 | 1.0094 |
| trace2 | 0.2512 | 0.2513 | 0.2542 | 1.0004 | 1.0120 |
| trace3 | 0.3821 | 0.3829 | 0.3909 | 1.0021 | 1.0232 |
| **geomean** | -- | -- | -- | **1.0024** | **1.0149** |

### 8.2 L1D load MPKI

| Trace | baseline | ip_stride | SPP | SPP reduction vs baseline |
|---|---|---|---|---|
| trace1 | 10.678 | 10.119 | 9.556 | 10.51 % |
| trace2 | 13.538 | 13.438 | 12.998 | 3.99 % |
| trace3 | 3.403 | 3.318 | 2.776 | 18.45 % |
| **average** | **9.206** | **8.958** | **8.443** | |

### 8.3 Prefetch accuracy and L1D coverage

Accuracy is ChampSim's own `ACCURACY` field (`pf_useful / pf_lower_level`); `useful/issued` is given in brackets.

| Trace | acc ip_stride | acc SPP | coverage ip_stride | coverage SPP |
|---|---|---|---|---|
| trace1 | 52.71 % (5.46 %) | 56.69 % (3.68 %) | 5.24 % | 10.51 % |
| trace2 | 38.18 % (2.89 %) | 54.61 % (2.27 %) | 0.74 % | 3.99 % |
| trace3 | 15.99 % (1.36 %) | 47.71 % (1.51 %) | 2.51 % | 18.45 % |
| *equal-weight mean* | 35.63 % | 53.01 % | 2.83 % | 10.98 % |
| **pooled (sum/sum)** | **39.38 %** | **53.89 %** | **2.70 %** | **8.29 %** |

*Pooled is the row to quote.* SPP wins on **every individual trace** as well, so the conclusion does not depend on the choice of aggregate.

### 8.4 SPP internal behaviour

From `l1d_prefetcher_final_stats()`. These are **our** counters, which ChampSim does not reset at the ROI boundary, so unlike every other table here they describe the **whole run (25M warmup + 25M ROI)**.

| Trace | uniform path | non-uniform path | mean windowed usefulness | windows | degree histogram | IP-table hit rate | pattern entries conf>=2 | chains cut by conf |
|---|---|---|---|---|---|---|---|---|
| trace1 | 32.36 % | 67.64 % | 64.59 % | 542 | d1=3 d2=105 d3=261 d4=173 | 67.86 % | 320 / 1024 | 438330 |
| trace2 | 18.18 % | 81.82 % | 67.52 % | 322 | d1=15 d2=60 d3=108 d4=139 | 43.43 % | 267 / 1024 | 339561 |
| trace3 | 46.85 % | 53.15 % | 61.44 % | 372 | d1=41 d2=65 d3=133 d4=133 | 86.69 % | 337 / 1024 | 213169 |

### 8.5 Page-confinement check (independent of our code)

`prefetch_line()` in `src/cache.cc` counts cross-page prefetch requests itself, so this is ChampSim auditing us rather than us auditing ourselves.

| Trace | config | cross-page prefetch requests | same-page prefetch requests |
|---|---|---|---|
| trace1 | IP-stride | **0** | 547035 |
| trace1 | SPP | **0** | 1460645 |
| trace2 | IP-stride | **0** | 149721 |
| trace2 | SPP | **0** | 970138 |
| trace3 | IP-stride | **0** | 363276 |
| trace3 | SPP | **0** | 1250130 |

### 8.6 Run provenance

| Trace | config | warmup instrs | simulated instrs | simulated cycles |
|---|---|---|---|---|
| trace1 | No prefetcher | 25000004 | 25000000 | 107598652 |
| trace1 | IP-stride | 25000004 | 25000000 | 107088310 |
| trace1 | SPP | 25000004 | 25000000 | 106591670 |
| trace2 | No prefetcher | 25000002 | 25000001 | 99538958 |
| trace2 | IP-stride | 25000002 | 25000001 | 99498688 |
| trace2 | SPP | 25000002 | 25000001 | 98353834 |
| trace3 | No prefetcher | 25000002 | 25000001 | 65433974 |
| trace3 | IP-stride | 25000002 | 25000001 | 65297638 |
| trace3 | SPP | 25000002 | 25000001 | 63951239 |
