# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

import sys, subprocess, tempfile, time, numpy as np
from pathlib import Path
from datetime import datetime
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import eccodes as ec
from dcfe import gribio, era5
from dcfe.config import Config
from dcfe.process import namelist
from dcfe.rawindex import RawIndex

T = datetime(2023, 8, 30, 14)
cfg = Config.make("20230830", "20230830", (61, 21, 59, 25), 0.25, levels=(60, 137))
ix = RawIndex.from_dir("livetest/raw")
lnsp = gribio.read(ix.lnsp[T])
mnauf = gribio.get_int(lnsp, "pentagonalResolutionParameterJ")
ref = sys.argv[1]   # a flex_extract hourly reference file, e.g. .../ERA5/20230830/EA02523083014

def cut(msg):
    g = ec.codes_new_from_message(msg)
    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
    v = ec.codes_get_values(g).reshape(nj, ni)
    lon0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"); lat0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees")
    j0 = int(round((lat0 - 61) / 0.25)); lon0 = lon0 if lon0 <= 180 else lon0 - 360
    i0 = int(round((21 - lon0) / 0.25))
    sub = v[j0:j0 + 9, i0:i0 + 17]
    for k, val in (("Ni", 17), ("Nj", 9), ("latitudeOfFirstGridPointInDegrees", 61), ("latitudeOfLastGridPointInDegrees", 59),
                   ("longitudeOfFirstGridPointInDegrees", 21), ("longitudeOfLastGridPointInDegrees", 25)):
        ec.codes_set(g, k, val)
    ec.codes_set_values(g, sub.ravel())
    out = ec.codes_get_message(g); ec.codes_release(g)
    return out

ml = {n: [] for n in ("U", "V", "T", "Q", "ETADOT")}
refsp = None
with open(ref, "rb") as fh:
    while (g := ec.codes_grib_new_from_file(fh)):
        pid, lev = ec.codes_get(g, "paramId"), ec.codes_get(g, "level")
        if pid == 134:
            refsp = ec.codes_get_message(g)
        for n in ml:
            if pid == era5.PARAM_ID[n] and ec.codes_get(g, "typeOfLevel") == "hybrid":
                ml[n].append(ec.codes_get_message(g))
        ec.codes_release(g)
print({n: len(v) for n, v in ml.items()}, "mnauf", mnauf)
work = Path(tempfile.mkdtemp(prefix="sptest_"))
wr = lambda f, msgs: (work / f).write_bytes(b"".join(msgs))
wr("fort.4", [namelist(cfg, mnauf).encode()])
wr("fort.10", [cut(m) for m in ml["U"] + ml["V"]]); wr("fort.11", [cut(m) for m in ml["T"]])
wr("fort.17", [cut(m) for m in ml["Q"]]); wr("fort.21", [cut(m) for m in ml["ETADOT"]]); wr("fort.12", [lnsp])
t0 = time.time()
r = subprocess.run([str(ROOT / "fortran" / "calc_etadot")], cwd=work, capture_output=True, text=True)
print("calc_etadot", "OK" if "CONGRATULATIONS" in r.stdout + r.stderr else "FAILED", f"{time.time()-t0:.1f}s")
print(r.stdout[-600:], r.stderr[-300:])
mine = None
with open(work / "fort.15", "rb") as fh:
    while (g := ec.codes_grib_new_from_file(fh)):
        if ec.codes_get(g, "paramId") == 134:
            la = ec.codes_get_array(g, "latitudes"); lo = ec.codes_get_array(g, "longitudes"); mv = ec.codes_get_values(g)
            mine = {(round(a, 2), round(((b + 180) % 360) - 180, 2)): x for a, b, x in zip(la, lo, mv)}
        ec.codes_release(g)
g = ec.codes_new_from_message(refsp)
la = ec.codes_get_array(g, "latitudes"); lo = ec.codes_get_array(g, "longitudes"); rv = ec.codes_get_values(g)
rd = {(round(a, 2), round(((b + 180) % 360) - 180, 2)): x for a, b, x in zip(la, lo, rv)}
ks = [k for k in mine if k in rd]
d = np.array([mine[k] - rd[k] for k in ks])
print(f"SP: {len(ks)} points, ref range {min(rd[k] for k in ks):.1f}..{max(rd[k] for k in ks):.1f}  max|diff|={np.abs(d).max():.4g} Pa mean={d.mean():.4g}")
print("workdir", work)
