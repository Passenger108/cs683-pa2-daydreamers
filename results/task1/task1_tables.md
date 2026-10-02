### 8.1 IPC and speedup

| Trace | IPC baseline | IPC ip_stride | IPC SPP | Speedup ip_stride | Speedup SPP |
|---|---|---|---|---|---|
| trace1 | 0.2323 | 0.2335 | 0.2346 | 1.0048 | 1.0095 |
| trace2 | 0.2512 | 0.2513 | 0.2542 | 1.0004 | 1.0121 |
| trace3 | 0.3821 | 0.3829 | 0.3907 | 1.0021 | 1.0225 |
| **geomean** | -- | -- | -- | **1.0024** | **1.0147** |

### 8.2 L1D load MPKI

| Trace | baseline | ip_stride | SPP | SPP reduction vs baseline |
|---|---|---|---|---|
| trace1 | 10.678 | 10.119 | 9.559 | 10.48 % |
| trace2 | 13.538 | 13.438 | 13.000 | 3.97 % |
| trace3 | 3.403 | 3.318 | 2.790 | 18.01 % |
| **average** | **9.206** | **8.958** | **8.450** | |

### 8.3 Prefetch accuracy and L1D coverage

Accuracy is ChampSim's own `ACCURACY` field (`pf_useful / pf_lower_level`); `useful/issued` is given in brackets.

| Trace | acc ip_stride | acc SPP | coverage ip_stride | coverage SPP |
|---|---|---|---|---|
| trace1 | 52.71 % (5.46 %) | 56.41 % (3.67 %) | 5.24 % | 10.48 % |
| trace2 | 38.18 % (2.89 %) | 54.34 % (2.29 %) | 0.74 % | 3.97 % |
| trace3 | 15.99 % (1.36 %) | 46.52 % (1.45 %) | 2.51 % | 18.01 % |
| *equal-weight mean* | 35.63 % | 52.42 % | 2.83 % | 10.82 % |
| **pooled (sum/sum)** | **39.38 %** | **53.36 %** | **2.70 %** | **8.22 %** |

*Pooled is the row to quote.* SPP wins on **every individual trace** as well, so the conclusion does not depend on the choice of aggregate.

### 8.4 SPP internal behaviour

From `l1d_prefetcher_final_stats()`. These are **our** counters, which ChampSim does not reset at the ROI boundary, so unlike every other table here they describe the **whole run (25M warmup + 25M ROI)**.

| Trace | uniform path | non-uniform path | mean windowed usefulness | windows | degree histogram | IP-table hit rate | pattern entries conf>=2 | chains cut by conf |
|---|---|---|---|---|---|---|---|---|
| trace1 | 31.87 % | 68.13 % | 64.46 % | 271 | d1=2 d2=50 d3=146 d4=73 | 67.86 % | 336 / 1024 | 439007 |
| trace2 | 17.87 % | 82.13 % | 67.20 % | 162 | d1=5 d2=35 d3=58 d4=64 | 43.43 % | 261 / 1024 | 342883 |
| trace3 | 45.69 % | 54.31 % | 60.13 % | 190 | d1=17 d2=42 d3=66 d4=65 | 86.69 % | 344 / 1024 | 219369 |

### 8.5 Page-confinement check (independent of our code)

`prefetch_line()` in `src/cache.cc` counts cross-page prefetch requests itself, so this is ChampSim auditing us rather than us auditing ourselves.

| Trace | config | cross-page prefetch requests | same-page prefetch requests |
|---|---|---|---|
| trace1 | IP-stride | **0** | 547035 |
| trace1 | SPP | **0** | 1465693 |
| trace2 | IP-stride | **0** | 149721 |
| trace2 | SPP | **0** | 964912 |
| trace3 | IP-stride | **0** | 363276 |
| trace3 | SPP | **0** | 1273484 |

### 8.6 Run provenance

| Trace | config | warmup instrs | simulated instrs | simulated cycles |
|---|---|---|---|---|
| trace1 | No prefetcher | 25000004 | 25000000 | 107598652 |
| trace1 | IP-stride | 25000004 | 25000000 | 107088310 |
| trace1 | SPP | 25000004 | 25000000 | 106584356 |
| trace2 | No prefetcher | 25000002 | 25000001 | 99538958 |
| trace2 | IP-stride | 25000002 | 25000001 | 99498688 |
| trace2 | SPP | 25000002 | 25000001 | 98351803 |
| trace3 | No prefetcher | 25000002 | 25000001 | 65433974 |
| trace3 | IP-stride | 25000002 | 25000001 | 65297638 |
| trace3 | SPP | 25000002 | 25000001 | 63993453 |
