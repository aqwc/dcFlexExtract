# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

import sys, numpy as np, eccodes as ec
KEYS = ("edition", "paramId", "typeOfLevel", "level", "dataDate", "dataTime", "step")
def box(g):
    """(lat, lon) grid -> boolean-free index slice of the 59-61N 21-25E box in a regular_ll field."""
    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
    la0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"); lo0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
    dj = ec.codes_get(g, "jDirectionIncrementInDegrees"); di = ec.codes_get(g, "iDirectionIncrementInDegrees")
    lo0 = lo0 - 360 if lo0 > 180 else lo0
    j0 = int(round((la0 - 61) / dj)); i0 = int(round((21 - lo0) / di))
    return ni, nj, j0, i0, int(round(2 / dj)) + 1, int(round(4 / di)) + 1
def load(path, limit=None):
    out = []
    with open(path, "rb") as fh:
        while (g := ec.codes_grib_new_from_file(fh)):
            ni, nj, j0, i0, nlat, nlon = box(g)
            v = ec.codes_get_values(g)
            if v.size == ni * nj:
                v = v.reshape(nj, ni)[j0:j0 + nlat, i0:i0 + nlon]
            out.append((tuple(ec.codes_get(g, k) for k in KEYS), np.array(v, float), (ni, nj)))
            ec.codes_release(g)
    return out
a = load(sys.argv[1]); b = load(sys.argv[2])
print("messages mine/ref:", len(a), len(b))
bad = [(i, x[0], y[0]) for i, (x, y) in enumerate(zip(a, b)) if x[0] != y[0]]
print("header mismatches:", len(bad), bad[:4])
print("shape mismatches:", sum(x[1].shape != y[1].shape for x, y in zip(a, b)))
worst = {}
for x, y in zip(a, b):
    if x[1].shape != y[1].shape: continue
    d = np.abs(x[1] - y[1]).max(); sc = np.abs(y[1]).max() or 1
    w = worst.get(x[0][1], (0, 0)); worst[x[0][1]] = (max(w[0], d), max(w[1], d / sc))
for k, (ab, rel) in sorted(worst.items()):
    print(f"paramId {k:4d}: max abs {ab:.4g}  rel {rel:.2g}")
