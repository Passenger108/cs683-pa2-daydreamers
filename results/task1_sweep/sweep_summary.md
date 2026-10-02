# Task 1 design sweep (GCC 7 -O3, 25M+25M, all three traces)

Speedup is a geometric mean (it is a ratio); MPKI an equal-weight mean
(equal instruction counts); accuracy and coverage are pooled
(sum of numerators over sum of denominators). See TASK1_SPP.md 8.7.0.

| variant | sweep | what it changes | storage B | geomean speedup | d vs base | avg L1D load MPKI | pooled accuracy | pooled coverage | mean IP-table hit rate |
|---|---|---|---|---|---|---|---|---|---|
| `base_64x4` | reference | the submitted design: 64x4 IP table, degree 1-4, window 512 | 2947 | 1.0147 | -- | 8.450 | 53.36 % | 8.22 % | 66.00 % |
| `ipA_256x1` | A  IP geometry | direct mapped, same entry count as base | 2883 | 1.0142 | -0.0005 | 8.482 | 53.33 % | 7.87 % | 59.86 % |
| `ipA_128x2` | A  IP geometry | same entries as base, less associativity | 2915 | 1.0147 | -0.0000 | 8.456 | 53.36 % | 8.15 % | 64.32 % |
| `ipA_128x4` | A  IP geometry | 2x entries of base | 4739 | 1.0148 | +0.0001 | 8.442 | 52.99 % | 8.30 % | 72.70 % |
| `ipA_64x8` | A  IP geometry | 2x entries of base, via associativity | 4803 | 1.0148 | +0.0001 | 8.441 | 52.90 % | 8.31 % | 73.51 % |
| `ipA_128x8` | A  IP geometry | 4x entries of base | 8451 | 1.0145 | -0.0001 | 8.443 | 52.08 % | 8.30 % | 76.97 % |
| `degB_1to3` | B  degree | shallower cap | 2947 | 1.0143 | -0.0004 | 8.463 | 53.18 % | 8.08 % | 65.99 % |
| `degB_1to6` | B  degree | deeper cap | 2947 | 1.0151 | +0.0005 | 8.428 | 52.49 % | 8.46 % | 66.00 % |
| `degB_1to8` | B  degree | much deeper cap | 2947 | 1.0153 | +0.0006 | 8.407 | 49.92 % | 8.68 % | 66.00 % |
| `degB_fixed4` | B  degree | NO throttling, always degree 4 | 2947 | 1.0147 | +0.0000 | 8.428 | 47.01 % | 8.45 % | 65.99 % |
| `degB_fixed2` | B  degree | NO throttling, always degree 2 | 2947 | 1.0138 | -0.0009 | 8.500 | 53.50 % | 7.67 % | 66.00 % |
| `winC_256` | C  acc window | faster adaptation, more measurement bias | 2947 | 1.0149 | +0.0002 | 8.443 | 53.89 % | 8.29 % | 66.00 % |
| `winC_1024` | C  acc window | less bias, slower adaptation | 2948 | 1.0146 | -0.0000 | 8.463 | 52.68 % | 8.07 % | 66.00 % |
| `unifD_2` | D  uniform thr | threshold 2 - provably misclassifies the PDF pattern | 2947 | 1.0150 | +0.0003 | 8.437 | 53.45 % | 8.35 % | 66.00 % |
| `unifD_4` | D  uniform thr | threshold 4 - slower to enter uniform mode | 2979 | 1.0146 | -0.0001 | 8.457 | 53.17 % | 8.14 % | 66.00 % |
