# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""Is exp(gridded LNSP from MARS) equivalent to the SP that the spectral route (calc_etadot) gives?

usage: compare_gridded_lnsp.py GRIDDED_LNSP.grb OUR_HOURLY_FILE REFERENCE_HOURLY_FILE
Compares, at the box points, SP = exp(LNSP) with paramId 134 in our hourly file and in the flex_extract
reference file. Everything is in Pa."""
import sys

import eccodes as ec
import numpy as np


def field(path, pid=None):
    """First message (optionally with paramId pid) as {(lat, lon): value}."""
    with open(path, "rb") as fh:
        while (g := ec.codes_grib_new_from_file(fh)):
            if pid is None or ec.codes_get(g, "paramId") == pid:
                la = ec.codes_get_array(g, "latitudes")
                lo = ec.codes_get_array(g, "longitudes")
                lo = np.where(lo > 180, lo - 360, lo)
                v = ec.codes_get_values(g)
                ec.codes_release(g)
                return {(round(a, 2), round(b, 2)): x for a, b, x in zip(la, lo, v)}
            ec.codes_release(g)
    raise SystemExit(f"no message with paramId {pid} in {path}")


lnsp = field(sys.argv[1])
sp_grid = {k: float(np.exp(v)) for k, v in lnsp.items()}
for label, path in (("our hourly file (spectral LNSP -> calc_etadot)", sys.argv[2]), ("flex_extract reference", sys.argv[3])):
    sp = field(path, 134)
    ks = [k for k in sp_grid if k in sp]
    d = np.array([sp_grid[k] - sp[k] for k in ks])
    print(f"exp(gridded LNSP) - SP in {label}: {len(ks)} points, "
          f"max|diff| {np.abs(d).max():.4g} Pa, rms {np.sqrt((d**2).mean()):.4g} Pa, mean {d.mean():.4g} Pa")
