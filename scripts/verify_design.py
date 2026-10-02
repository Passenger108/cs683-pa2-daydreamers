#!/usr/bin/env python3
"""
Offline verification of the SPP design decisions, before writing any C++.

We check three things:
  (A) Does the uniform-stride detector with threshold T ever mis-classify the
      PDF's own non-uniform example (+1,+2,+2,+2,+3)^n as "uniform"?
  (B) Does the 10-bit signature (sig = ((sig<<3) ^ (stride & 0x7F)) & 0x3FF)
      give a DISTINCT signature for every phase of that period-5 cycle?
      (If two phases share a signature, one of them can never be predicted.)
  (C) Once trained, does the chained lookahead (sig -> stride -> sig' -> ...)
      actually reproduce the next `degree` strides of the cycle?
"""

SIG_BITS = 10
SIG_MASK = (1 << SIG_BITS) - 1
SIG_SHIFT = 3

def upd(sig, stride):
    return ((sig << SIG_SHIFT) ^ (stride & 0x7F)) & SIG_MASK

PATTERN = [1, 2, 2, 2, 3]          # the PDF's example, in cache lines
REPS = 40

stream = PATTERN * REPS

# ---------------------------------------------------------------- (A)
print("=== (A) uniform-stride detector on the PDF's non-uniform example ===")
for T in (1, 2, 3):
    conf, last, false_uniform = 0, None, 0
    for s in stream:
        if last is not None and s == last:
            conf = min(conf + 1, 3)
        else:
            conf = 0
        last = s
        if conf >= T:
            false_uniform += 1
    print(f"  threshold T={T}: declared UNIFORM on {false_uniform:4d} of "
          f"{len(stream)} accesses  -> {'WRONG' if false_uniform else 'correct'}")

# ---------------------------------------------------------------- (B)
print("\n=== (B) signature uniqueness for each phase of the period-5 cycle ===")
sig = 0
seen = {}            # signature -> set of "next stride" outcomes
for i, s in enumerate(stream):
    # sig here is the signature BEFORE observing s, i.e. the one that must
    # predict s.  Skip the first period (cold history).
    if i >= len(PATTERN):
        seen.setdefault(sig, set()).add(s)
    sig = upd(sig, s)

print(f"  distinct signatures used: {len(seen)} (expect {len(PATTERN)})")
ok = True
for sg, outcomes in sorted(seen.items()):
    flag = "OK" if len(outcomes) == 1 else "AMBIGUOUS"
    if len(outcomes) != 1:
        ok = False
    print(f"    sig 0x{sg:03x} -> next stride {sorted(outcomes)}  [{flag}]")
print("  verdict:", "signature fully disambiguates the pattern" if ok else "COLLISION")

# ---------------------------------------------------------------- (C)
print("\n=== (C) chained lookahead after training ===")
# train a direct-mapped pattern table exactly like the C++ will
table = {}           # sig -> [stride, conf]
CONF_MAX, CONF_PREDICT = 3, 2

def train(sig, stride):
    e = table.setdefault(sig, [0, 0])
    if e[1] > 0 and e[0] == stride:
        e[1] = min(e[1] + 1, CONF_MAX)
    elif e[1] == 0:
        e[0], e[1] = stride, 1
    else:
        e[1] -= 1

sig = 0
for s in stream:
    train(sig, s)
    sig = upd(sig, s)

# now, standing at an arbitrary phase, walk the chain
for start in range(len(PATTERN)):
    # replay enough history to land on phase `start`
    sig = 0
    for k in range(20 + start):
        sig = upd(sig, PATTERN[k % len(PATTERN)])
    expected = [PATTERN[(20 + start + j) % len(PATTERN)] for j in range(4)]
    got, s2 = [], sig
    for _ in range(4):
        e = table.get(s2)
        if e is None or e[1] < CONF_PREDICT or e[0] == 0:
            break
        got.append(e[0])
        s2 = upd(s2, e[0])
    print(f"  phase {start}: expected next 4 strides {expected}, "
          f"lookahead gave {got}  [{'OK' if got == expected else 'MISMATCH'}]")

# ---------------------------------------------------------------- extra
print("\n=== (D) same checks for a few other repeating sequences ===")
for pat in ([1, 2, 3], [4, -1], [1, 1, 2], [8, 8, 8, 1], [2], [1, 2, 4, 8, 16]):
    st = pat * 40
    tbl = {}
    def tr(sg, s, tbl=tbl):
        e = tbl.setdefault(sg, [0, 0])
        if e[1] > 0 and e[0] == s:
            e[1] = min(e[1] + 1, CONF_MAX)
        elif e[1] == 0:
            e[0], e[1] = s, 1
        else:
            e[1] -= 1
    sg = 0
    for s in st:
        tr(sg, s)
        sg = upd(sg, s)
    # check prediction accuracy of a 1-step prediction over the last period
    sg = 0
    for k in range(60):
        sg = upd(sg, pat[k % len(pat)])
    good = 0
    for j in range(len(pat)):
        e = tbl.get(sg)
        nxt = pat[(60 + j) % len(pat)]
        if e and e[1] >= CONF_PREDICT and e[0] == nxt:
            good += 1
        sg = upd(sg, nxt)
    print(f"  pattern {str(pat):22s} period {len(pat)}: "
          f"{good}/{len(pat)} phases predicted correctly")
