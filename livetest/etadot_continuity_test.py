# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""Independent check of the half-level vertical velocity H = eta_dot * dp/deta that calc_etadot produces.

Mass continuity in hybrid coordinates, for every layer k:
    H(k+1/2) - H(k-1/2) = - [ d(dp_k)/dt + div( V_k * dp_k ) ],   dp_k = dA_k + dB_k * ps
The right-hand side uses only the winds, the surface pressure at the hours before and after, and A and B, so
it does not depend on the running sum of calc_etadot. We compare it with the layer differences of H from
(a) calc_etadot's running sum started at the top of the retrieved levels (what flex_extract does), and
(b) the same sum started at the ground with H = 0 there.
usage (repository root):  PYTHONPATH=. python livetest/etadot_continuity_test.py [HOURLY_FILE ...]
Each HOURLY_FILE given (an output file for 14 UTC) is checked as written, in addition to (a) and (b)."""
import sys
from datetime import datetime
from pathlib import Path

import eccodes as ec
import numpy as np

from dcfe import gribio
from dcfe.rawindex import RawIndex

ROOT = Path(__file__).resolve().parent.parent
NLAT, NLON = 9, 17
T = datetime(2023, 8, 30, 14)
EARTH = 6.371e6
P00 = 101325.0

ix = RawIndex.from_dir(ROOT / "livetest" / "raw")
g = ec.codes_new_from_message(gribio.read(ix.lnsp[T]))
pv = ec.codes_get_array(g, "pv")
A, B = pv[:138], pv[138:]


def raw(pid, lv):
    g = ec.codes_new_from_message(gribio.read(ix.ml[(pid, T, lv)]))
    v = ec.codes_get_values(g).reshape(NLAT, NLON)
    if pid == 131 and lv == 60:
        global LAT, LON
        LAT = ec.codes_get_array(g, "latitudes").reshape(NLAT, NLON)[:, 0]
        LON = ec.codes_get_array(g, "longitudes").reshape(NLAT, NLON)[0, :]
    ec.codes_release(g)
    return v


def ps_at(h):
    with open(ROOT / "livetest" / "out" / f"EA025230830{h:02d}", "rb") as fh:
        while (g := ec.codes_grib_new_from_file(fh)):
            if ec.codes_get(g, "paramId") == 134:
                v = ec.codes_get_values(g).reshape(NLAT, NLON)
                ec.codes_release(g)
                return v
            ec.codes_release(g)


U = np.zeros((138, NLAT, NLON)); V = np.zeros_like(U); E = np.zeros_like(U)
for lv in range(60, 138):
    U[lv], V[lv], E[lv] = raw(131, lv), raw(132, lv), raw(77, lv)
ps, ps_m, ps_p = ps_at(14), ps_at(13), ps_at(15)
dpsdt = (ps_p - ps_m) / 7200.0

# half-level vertical velocity H(K) = value at the interface below full level K
Et = np.zeros_like(U)
for K in range(60, 138):
    dak, dbk = A[K] - A[K - 1], B[K] - B[K - 1]
    Et[K] = 2 * E[K] * ps * (dak / ps + dbk) / (dak / P00 + dbk)
Htop = np.zeros((139, NLAT, NLON))          # (a) flex_extract: starts at 0 above level 60
Hgnd = np.zeros((139, NLAT, NLON))          # (b) starts at the ground: Hgnd[137] = 0
for K in range(60, 138):
    Htop[K] = Et[K] - Htop[K - 1]
for K in range(137, 59, -1):
    Hgnd[K - 1] = Et[K] - Hgnd[K]

phi = np.deg2rad(LAT)[:, None]
lam = np.deg2rad(LON)[None, :]
def div(fu, fv):
    """(1/(a cos phi)) [ d fu/d lambda + d (fv cos phi)/d phi ] with central differences."""
    dl = np.gradient(fu, np.deg2rad(LON), axis=1)
    dp = np.gradient(fv * np.cos(phi), np.deg2rad(LAT), axis=0)
    return (dl + dp) / (EARTH * np.cos(phi))

inner = (slice(1, NLAT - 1), slice(1, NLON - 1))
res = {"top": [], "gnd": []}; sig = []
for K in range(61, 138):
    dA, dB = A[K] - A[K - 1], B[K] - B[K - 1]
    dp = dA + dB * ps
    rhs = -(dB * dpsdt + div(U[K] * dp, V[K] * dp))
    sig.append(rhs[inner])
    res["top"].append((Htop[K] - Htop[K - 1] - rhs)[inner])
    res["gnd"].append((Hgnd[K] - Hgnd[K - 1] - rhs)[inner])
sig = np.array(sig); rms = lambda x: float(np.sqrt((np.array(x) ** 2).mean()))
files = {}
for path in sys.argv[1:]:
    Hf = np.zeros((139, NLAT, NLON))
    with open(path, "rb") as fh:
        while (g := ec.codes_grib_new_from_file(fh)):
            if ec.codes_get(g, "paramId") == 77:
                Hf[ec.codes_get(g, "level")] = ec.codes_get_values(g).reshape(NLAT, NLON)
            ec.codes_release(g)
    files[path] = [(Hf[K] - Hf[K - 1] - (-(( B[K] - B[K - 1]) * dpsdt + div(U[K] * (A[K] - A[K - 1] + (B[K] - B[K - 1]) * ps),
                                                                          V[K] * (A[K] - A[K - 1] + (B[K] - B[K - 1]) * ps)))))[inner]
                   for K in range(61, 138)]
    files[path + "#ground"] = Hf[137]
print(f"layers 61..137, interior points ({sig.shape[1]}x{sig.shape[2]}), hour 14 UTC")
print(f"  rms of the layer divergence term itself (the signal):      {rms(sig):.4f} Pa/s")
print(f"  rms of the misfit, running sum from the top (flex_extract): {rms(res['top']):.4f} Pa/s")
print(f"  rms of the misfit, running sum from the ground (H=0):       {rms(res['gnd']):.4f} Pa/s")
print(f"  misfit of the two by level pair (odd/even) [mean of residual, Pa/s], flex_extract: "
      f"{np.mean([r.mean() for r in res['top'][0::2]]):+.4f} / {np.mean([r.mean() for r in res['top'][1::2]]):+.4f}")
print(f"  same for the ground-start sum:                              "
      f"{np.mean([r.mean() for r in res['gnd'][0::2]]):+.4f} / {np.mean([r.mean() for r in res['gnd'][1::2]]):+.4f}")
print(f"  H at the ground interface (must be 0): flex_extract {rms(Htop[137]):.4f} rms; ground-start {rms(Hgnd[137]):.4f}")
for path in sys.argv[1:]:
    print(f"  as written in {path}: misfit {rms(files[path]):.4f} Pa/s, H at the ground interface {rms(files[path + '#ground']):.4f} rms")
