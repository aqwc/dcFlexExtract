# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# The processing sequence (fort.NN files, calc_etadot call, order of the output messages) follows
# flex_extract (Mods/prepare_flexpart.py and Classes/EcFlexpart.py).

"""Raw ERA5 GRIB -> hourly FLEXPART input files.

For each output hour T the model-level fields are handed to the Fortran program calc_etadot
(through the fort.NN files it expects, in a private scratch directory), and the result is
concatenated with the cloud water fields, the fluxes, the surface fields and the static fields:

    [calc_etadot: U V ETADOT T SP Q] [CLWC] [CIWC] [6 fluxes] [9 surface] [4 static]

Existing complete output files are skipped, raw data is never touched.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import era5, gribio
from .config import Config
from .rawindex import RawIndex

_ID = era5.PARAM_ID
LOG = logging.getLogger("dcfe")


def prefix_for(grid: float) -> str:
    """Output name prefix, e.g. EA025 for 0.25 degrees (as in the original CONTROL files)."""
    return f"EA{round(grid * 100):03d}"


def hours(cfg: Config) -> list[datetime]:
    t = datetime.combine(cfg.start, datetime.min.time())
    end = datetime.combine(cfg.end, datetime.min.time()) + timedelta(hours=23)
    out = []
    while t <= end:
        out.append(t)
        t += timedelta(hours=1)
    return out


def out_name(cfg: Config, T: datetime) -> str:
    return f"{prefix_for(cfg.grid)}{T:%y%m%d%H}"


def namelist(cfg: Config, mnauf: int) -> str:
    """fort.4 for calc_etadot, ERA5 case: ETADOT from MARS (meta=1), regular lat-lon, no omega."""
    west, east = cfg.west, cfg.east
    if east < west:
        east += 360
    maxl = int(round((east - west) / cfg.grid)) + 1
    maxb = int(round((cfg.north - cfg.south) / cfg.grid)) + 1
    return (
        "&NAMGEN\n"
        f"  maxl = {maxl},\n  maxb = {maxb},\n  mlevel = {era5.MAX_LEVEL},\n"
        f'  mlevelist = "{cfg.level_first}/to/{cfg.level_last}",\n'
        f"  mnauf = {mnauf},\n  metapar = 77,\n"
        f"  rlo0 = {west},\n  rlo1 = {east},\n  rla0 = {cfg.south},\n  rla1 = {cfg.north},\n"
        "  momega = 0,\n  momegadiff = 0,\n  mgauss = 0,\n  msmooth = 0,\n"
        "  meta = 1,\n  metadiff = 0,\n  mdpdeta = 1\n/\n"
    )


def missing(ix: RawIndex, cfg: Config, T: datetime) -> list[str]:
    miss = ix.missing_for(T)
    if T not in ix.lnsp:
        miss.append("LNSP")
    for name in era5.ML_VARS:
        absent = [lv for lv in range(cfg.level_first, cfg.level_last + 1) if (_ID[name], T, lv) not in ix.ml]
        if absent:
            miss.append(f"{name}(levels {absent[0]}..{absent[-1]}, {len(absent)} missing)")
    return miss


def _ml_msgs(ix: RawIndex, cfg: Config, name: str, T: datetime) -> list[bytes]:
    return [gribio.read(ix.ml[(_ID[name], T, lv)]) for lv in range(cfg.level_first, cfg.level_last + 1)]


def build_hour(ix: RawIndex, cfg: Config, T: datetime, exe: str | Path, outdir: Path, scratch: Path,
               keep_scratch: bool = False) -> Path:
    final = outdir / out_name(cfg, T)
    if final.exists():
        return final
    miss = missing(ix, cfg, T)
    if miss:
        raise RuntimeError(f"cannot build {final.name}: missing {', '.join(miss)}")
    work = scratch / f"{T:%Y%m%d%H}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    wr = lambda name, msgs: (work / name).write_bytes(b"".join(msgs))

    lnsp = gribio.read(ix.lnsp[T])
    nl = namelist(cfg, gribio.get_int(lnsp, "pentagonalResolutionParameterJ"))
    wr("fort.4", [nl.encode()])
    LOG.debug("%s: scratch dir %s; fort.4 namelist:\n%s", out_name(cfg, T), work, nl.rstrip())
    wr("fort.10", _ml_msgs(ix, cfg, "U", T) + _ml_msgs(ix, cfg, "V", T))
    wr("fort.11", _ml_msgs(ix, cfg, "T", T))
    wr("fort.12", [lnsp])      # LNSP, spectral (fort.13 would be the divergence, unused for ETA=1)
    wr("fort.17", _ml_msgs(ix, cfg, "Q", T))
    wr("fort.21", _ml_msgs(ix, cfg, "ETADOT", T))
    refs = [ix.lnsp[T]] + [ix.ml[(_ID[n], T, lv)] for n in era5.ML_VARS
                           for lv in range(cfg.level_first, cfg.level_last + 1)]
    refs += ix.flux_refs(T) + ix.surface_refs(T) + ix.static_refs()
    LOG.debug("%s: input messages come from: %s", out_name(cfg, T), ", ".join(sorted({r.path for r in refs})))
    LOG.debug("%s: running (cd %s && %s) with inputs fort.10 (U,V) fort.11 (T) fort.12 (LNSP) fort.17 (Q) "
              "fort.21 (ETADOT)", out_name(cfg, T), work, exe)
    r = subprocess.run([str(exe)], cwd=work, capture_output=True, text=True)
    text = r.stdout + r.stderr
    LOG.debug("%s: calc_etadot exit status %d; last output lines:\n%s", out_name(cfg, T), r.returncode,
              "\n".join(text.strip().splitlines()[-6:]))
    if r.returncode != 0 or "CONGRATULATIONS" not in text:
        (outdir / f"{final.name}.calc_etadot.log").write_text(text)
        LOG.error("%s: calc_etadot failed (exit status %d); full output:\n%s", out_name(cfg, T), r.returncode, text)
        raise RuntimeError(f"calc_etadot failed for {T} (log next to the output)")

    part = final.with_name(final.name + ".part")
    with open(part, "wb") as f:
        f.write((work / "fort.15").read_bytes())
        for name in ("CLWC", "CIWC"):
            f.write(b"".join(_ml_msgs(ix, cfg, name, T)))
        for m in ix.flux_messages(T) + ix.surface_messages(T) + ix.static_messages():
            f.write(m)
    os.replace(part, final)
    if not keep_scratch:
        shutil.rmtree(work, ignore_errors=True)
        LOG.debug("%s: scratch dir %s removed", out_name(cfg, T), work)
    return final
