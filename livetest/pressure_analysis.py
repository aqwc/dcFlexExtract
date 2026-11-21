# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""How different are two surface-pressure data sets, and what does that do to the model-level heights?

usage (from the repository root):
  python livetest/pressure_analysis.py [GRIDDED_LNSP.grb]

Compares, over the test box and all 24 hours of 2023-08-30,
  A  = SP from the spectral route (LNSP -> calc_etadot) in our hourly files in livetest/out  (taken as reference)
  B  = ECMWF's gridded surface pressure from the single-levels dataset (livetest/sp/sp.grb, fetched if missing)
  C  = exp(gridded LNSP from MARS), only if a file is given
and converts the differences into differences of model-level pressure and of height above ground, with the
hybrid coefficients A,B from the LNSP message and the T, q profiles of the raw model-level data (hydrostatic,
virtual temperature, ECMWF IFS documentation part III, eq. 2.21-2.23)."""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import eccodes as ec
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dcfe import gribio                                  # noqa: E402
from dcfe.rawindex import RawIndex                       # noqa: E402

G, RD, RV = 9.80665, 287.06, 461.5
DAY = datetime(2023, 8, 30)
NLAT, NLON = 9, 17


def fetch_sl_sp(path):
    from dcfe.client import DatastoresClient
    c = DatastoresClient()
    body = {"product_type": ["reanalysis"], "variable": ["surface_pressure"], "year": "2023", "month": "08",
            "day": "30", "time": [f"{h:02d}:00" for h in range(24)], "data_format": "grib",
            "download_format": "unarchived", "area": [61, 21, 59, 25], "grid": [0.25, 0.25]}
    job = c.submit("reanalysis-era5-single-levels", body)
    while True:
        st, msg = c.poll(job)
        if st in ("done", "failed"):
            break
        time.sleep(10)
    if st != "done":
        raise SystemExit(f"download failed: {msg}")
    path.parent.mkdir(parents=True, exist_ok=True)
    c.download(job, str(path))
    c.cleanup(job)


def read_box(path, pid, hour=None):
    """{hour: 2-D array (lat from north to south, lon west to east)} for paramId pid."""
    out = {}
    with open(path, "rb") as fh:
        while (g := ec.codes_grib_new_from_file(fh)):
            if ec.codes_get(g, "paramId") == pid:
                h = ec.codes_get(g, "validityTime") // 100
                v = ec.codes_get_values(g)
                if v.size == NLAT * NLON:
                    out[h] = v.reshape(NLAT, NLON)
            ec.codes_release(g)
    return out


def stats(name, d, ref):
    rel = d / ref
    print(f"  {name:34s} mean {d.mean():9.3f} Pa  rms {np.sqrt((d**2).mean()):8.3f} Pa  max|d| {np.abs(d).max():8.3f} Pa"
          f"   relative: mean {rel.mean()*1e6:8.1f} ppm  rms {np.sqrt((rel**2).mean())*1e6:8.1f} ppm"
          f"  max {np.abs(rel).max()*1e6:8.1f} ppm")


def heights(ps, T, q, A, B):
    """Heights above ground [m] of the model full levels for ONE column. ps in Pa, T/q for levels 60..137
    (index 0 = level 60), A and B the 138 half-level coefficients (half level 0 = model top)."""
    levels = np.arange(60, 138)
    ph = A + B * ps                                     # half-level pressures, ph[i] between full levels i and i+1
    Tv = T * (1 + (RV / RD - 1) * q)
    z_half = np.zeros(138)                              # height of half levels; ph[137] = surface -> 0
    z_full = np.zeros(len(levels))
    for n in range(len(levels) - 1, -1, -1):            # from the surface upward
        k = levels[n]
        p_lo, p_up = ph[k], ph[k - 1]                   # lower / upper half level of full level k
        z_half[k - 1] = z_half[k] + RD * Tv[n] / G * np.log(p_lo / p_up)
        alpha = np.log(2.0) if k == 1 else 1 - p_up / (p_lo - p_up) * np.log(p_lo / p_up)
        z_full[n] = z_half[k] + alpha * RD * Tv[n] / G
    return z_full, 0.5 * (ph[levels] + ph[levels - 1]), None


def main():
    sl = ROOT / "livetest" / "sp" / "sp.grb"
    if not sl.exists():
        fetch_sl_sp(sl)
    sp_spec = {}
    for h in range(24):
        with open(ROOT / "livetest" / "out" / f"EA025230830{h:02d}", "rb") as fh:
            while (g := ec.codes_grib_new_from_file(fh)):
                if ec.codes_get(g, "paramId") == 134:
                    sp_spec[h] = ec.codes_get_values(g).reshape(NLAT, NLON)
                ec.codes_release(g)
    sp_sl = read_box(sl, 134)
    sp_lnsp = None
    if len(sys.argv) > 1:
        sp_lnsp = {h: np.exp(v) for h, v in read_box(sys.argv[1], 152).items()}

    print("=== 1. relative differences of surface pressure, 24 hours x 153 points")
    ref = np.stack([sp_spec[h] for h in range(24)])
    print(f"  spectral-route SP: range {ref.min():.0f} .. {ref.max():.0f} Pa, mean {ref.mean():.0f} Pa")
    sl_arr = np.stack([sp_sl[h] for h in range(24)])
    stats("B: ECMWF gridded SP - A", sl_arr - ref, ref)
    if sp_lnsp:
        for h, v in sp_lnsp.items():
            stats(f"C: exp(gridded LNSP), {h:02d} UTC - A", v - sp_spec[h], sp_spec[h])
    d = sl_arr - ref
    print("  by hour (B - A): " + " ".join(f"{h:02d}:{d[h].mean():+.1f}/{d[h].std():.1f}" for h in range(24)) + "  (mean/std, Pa)")
    zraw = read_box(ROOT / "livetest" / "out" / "EA02523083014", 129)[14]
    lsm = read_box(ROOT / "livetest" / "out" / "EA02523083014", 172)[14]
    oro = zraw / G
    print(f"  orography in the box: {oro.min():.0f} .. {oro.max():.0f} m; land fraction {lsm.mean():.2f}")
    print(f"  correlation of (B-A) with orography: {np.corrcoef(d.reshape(24, -1).mean(0), oro.ravel())[0, 1]:+.2f}, "
          f"with land-sea mask: {np.corrcoef(d.reshape(24, -1).mean(0), lsm.ravel())[0, 1]:+.2f}")
    print(f"  (B-A) vs A across all points: slope {np.polyfit(ref.ravel(), d.ravel(), 1)[0]*1e3:+.3f} Pa per kPa")

    print("\n=== 2. effect on the model levels, hour 14 UTC (levels 60..137)")
    ix = RawIndex.from_dir(ROOT / "livetest" / "raw")
    T14 = datetime(2023, 8, 30, 14)
    lnsp_msg = gribio.read(ix.lnsp[T14])
    g = ec.codes_new_from_message(lnsp_msg)
    pv = ec.codes_get_array(g, "pv"); ec.codes_release(g)
    A, B = pv[:138], pv[138:]
    Tl = np.zeros((78, NLAT, NLON)); ql = np.zeros((78, NLAT, NLON))
    for i, lv in enumerate(range(60, 138)):
        for arr, pid in ((Tl, 130), (ql, 133)):
            g = ec.codes_new_from_message(gribio.read(ix.ml[(pid, T14, lv)]))
            arr[i] = ec.codes_get_values(g).reshape(NLAT, NLON); ec.codes_release(g)
    cases = {"B (ECMWF gridded SP)": sl_arr[14]}
    if sp_lnsp and 14 in sp_lnsp:
        cases["C (exp gridded LNSP)"] = sp_lnsp[14]
    z0 = np.zeros((78, NLAT, NLON)); p0 = np.zeros((78, NLAT, NLON))
    for j in range(NLAT):
        for i in range(NLON):
            z0[:, j, i], p0[:, j, i], _ = heights(sp_spec[14][j, i], Tl[:, j, i], ql[:, j, i], A, B)
    for name, sp in cases.items():
        dz = np.zeros_like(z0); dp = np.zeros_like(z0)
        for j in range(NLAT):
            for i in range(NLON):
                z, p, _ = heights(sp[j, i], Tl[:, j, i], ql[:, j, i], A, B)
                dz[:, j, i] = z - z0[:, j, i]; dp[:, j, i] = p - p0[:, j, i]
        print(f"  {name} versus the spectral route: ps difference at this hour: max|d| {np.abs(sp - sp_spec[14]).max():.1f} Pa")
        print("   level  B_k      p_k [hPa]   max|dp| [Pa]   dp/p [ppm]   z_k [m]   mean dz [m]   max|dz| [m]   dz/z [ppm]")
        for lv in (60, 80, 100, 120, 130, 137):
            n = lv - 60
            print(f"   {lv:4d}  {B[lv-1:lv+1].mean():6.3f}  {p0[n].mean()/100:9.1f}  {np.abs(dp[n]).max():12.3f}"
                  f"  {np.abs(dp[n]/p0[n]).max()*1e6:10.1f}  {z0[n].mean():8.1f}  {dz[n].mean():+11.4f}  {np.abs(dz[n]).max():11.4f}  "
                  f"{np.abs(dz[n]/z0[n]).max()*1e6:10.1f}")
        print(f"   rule of thumb H*dps/ps with H=RT/g: {RD*280/G*np.abs(sp - sp_spec[14]).max()/sp_spec[14].mean():.2f} m "
              f"for max |dps|")


main()
