# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# The request contents (parameters, times, forecast steps for the fluxes) follow what flex_extract
# sends to CDS (Classes/MarsRetrieval.py, Classes/EcFlexpart.py).

"""Pure request builder: Config -> list of download units. No I/O, no network.

A *unit* (Request) is the smallest thing that is downloaded, stored and skipped on restart:
one day x group x variable subset x level block x set of hours. Its file name is a deterministic
function of its content, so a restarted run finds what was already downloaded. If CDS refuses a
unit (cost limit), `Request.split()` gives smaller units; because GRIB files can simply be
concatenated, the split is invisible to post-processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from . import era5
from .config import Config

# groups
ML, LNSP, GLNSP, SP, SL, FLUX, STATIC = "ML", "LNSP", "GLNSP", "SP", "SL", "FLUX", "STATIC"

_GROUP_VARS = {
    ML: tuple(era5.ML_VARS),
    LNSP: ("LNSP",),         # spectral
    GLNSP: ("LNSP",),        # on the regular grid, like the model-level fields
    SP: ("SP",),             # ECMWF surface pressure, single levels
    SL: tuple(era5.SFC_AN_VARS),
    FLUX: tuple(era5.SFC_FLUX_VARS),
    STATIC: tuple(era5.SFC_STATIC_VARS),
}
_GROUP_DATASET = {
    ML: era5.DATASET_MARS, LNSP: era5.DATASET_MARS, GLNSP: era5.DATASET_MARS, SP: era5.DATASET_SFC,
    SL: era5.DATASET_SFC, FLUX: era5.DATASET_SFC, STATIC: era5.DATASET_SFC,
}


def _fmt(x: float) -> str:
    return f"{x:g}"


def _hours_tag(hours: tuple[int, ...]) -> str:
    runs, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h != prev + 1:
            runs.append((start, prev))
            start = h
        prev = h
    runs.append((start, prev))
    return "h" + "_".join(f"{a:02d}" if a == b else f"{a:02d}-{b:02d}" for a, b in runs)


@dataclass(frozen=True)
class Request:
    group: str
    day: date
    vars: tuple[str, ...]
    hours: tuple[int, ...]
    levels: Optional[tuple[int, int]]      # model levels (first, last); None for surface groups
    domain: str                            # Config.domain_tag
    area: tuple[float, float, float, float]  # N, W, S, E (a sub-rectangle if tiled)
    grid: float
    tiled: bool = False                    # True when `area` is a tile of the domain
    ndays: int = 1                         # consecutive days covered, starting at `day`

    # ---- (de)serialisation, used by the download manifest ------------------------------------
    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["day"] = self.day.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        return cls(group=d["group"], day=date.fromisoformat(d["day"]), vars=tuple(d["vars"]),
                   hours=tuple(d["hours"]), levels=tuple(d["levels"]) if d["levels"] else None,
                   domain=d["domain"], area=tuple(d["area"]), grid=d["grid"], tiled=d["tiled"],
                   ndays=d.get("ndays", 1))

    # ---- identity -------------------------------------------------------------------------
    @property
    def dataset(self) -> str:
        return _GROUP_DATASET[self.group]

    @property
    def queue(self) -> str:
        """Server-side queue this request waits in. MARS (tape) and single-levels are separate
        services, so one request may be in flight in each at the same time."""
        return self.dataset

    @property
    def relpath(self) -> str:
        full = _GROUP_VARS[self.group]
        vtag = "all" if self.vars == full else "-".join(self.vars)
        parts = [self.group, vtag]
        if self.levels:
            parts.append(f"L{self.levels[0]:03d}-{self.levels[1]:03d}")
        if self.hours != era5.HOURS and self.group != STATIC:
            parts.append(_hours_tag(self.hours))
        if self.tiled:
            n, w, s, e = self.area
            parts.append("T" + "_".join(_fmt(x).replace("-", "m").replace(".", "p") for x in (n, w, s, e)))
        span = f"{self.day:%Y%m%d}" if self.ndays == 1 else f"{self.day:%Y%m%d}-{self.last_day:%Y%m%d}"
        return f"{self.domain}/{span}/{'_'.join(parts)}.grb"

    unit_id = relpath

    @property
    def last_day(self) -> date:
        return self.day + timedelta(days=self.ndays - 1)

    @property
    def days(self) -> list[date]:
        return [self.day + timedelta(days=i) for i in range(self.ndays)]

    @property
    def nlevels(self) -> int:
        return 1 if self.levels is None else self.levels[1] - self.levels[0] + 1

    @property
    def expected_messages(self) -> int:
        """Number of GRIB messages the finished file must contain (used for sanity checks)."""
        if self.group == STATIC:
            return len(self.vars)
        return len(self.vars) * self.nlevels * len(self.hours) * self.ndays

    # ---- CDS request body -----------------------------------------------------------------
    def cds_request(self) -> dict:
        n, w, s, e = self.area
        times = [f"{h:02d}" for h in self.hours]
        if self.dataset == era5.DATASET_MARS:
            if self.group == LNSP:
                params, levelist, grid = era5.LNSP_PARAM, "1", "OFF"   # spectral, as before
            elif self.group == GLNSP:
                params, levelist, grid = era5.LNSP_PARAM, "1", f"{_fmt(self.grid)}/{_fmt(self.grid)}"
            else:
                params = "/".join(era5.ML_VARS[v] for v in self.vars)
                a, b = self.levels
                levelist = f"{a}/to/{b}" if b > a else str(a)
                grid = f"{_fmt(self.grid)}/{_fmt(self.grid)}"
            return {
                "class": "ea", "expver": "1", "stream": "oper", "type": "an", "levtype": "ml",
                "accuracy": "24",           # 24-bit packing, as in the original (ETADOT needs it)
                "date": (f"{self.day:%Y%m%d}" if self.ndays == 1
                         else f"{self.day:%Y%m%d}/to/{self.last_day:%Y%m%d}"),
                "time": "/".join(times),
                "levelist": levelist, "param": params, "grid": grid,
                "area": "/".join(_fmt(x) for x in (n, w, s, e)),
            }
        table = {SP: {"SP": era5.SP_VAR}, SL: era5.SFC_AN_VARS, FLUX: era5.SFC_FLUX_VARS, STATIC: era5.SFC_STATIC_VARS}[self.group]
        return {
            "product_type": ["reanalysis"],
            "variable": [table[v] for v in self.vars],
            "year": f"{self.day:%Y}", "month": f"{self.day:%m}",
            "day": [f"{d:%d}" for d in self.days],          # plan() keeps single-level spans inside one month
            "time": [f"{t}:00" for t in times],
            "data_format": "grib", "download_format": "unarchived",
            "area": [n, w, s, e], "grid": [self.grid, self.grid],
        }

    # ---- splitting after a "request too large" error --------------------------------------
    def split(self) -> list["Request"]:
        """Smaller units covering exactly the same data. Order: fewer days, then variables, then hours,
        then geographic tiles. Levels are never split. Returns [] when nothing is left to divide.
        Parts are plain GRIB; hours/variables parts are simply concatenated, tiles must be
        mosaicked back to the domain by the post-processor."""
        def halves(seq):
            m = (len(seq) + 1) // 2
            return seq[:m], seq[m:]

        rep = lambda **kw: Request(**{**self.__dict__, **kw})
        if self.ndays > 1:                                   # fewer days per request first
            k = (self.ndays + 1) // 2
            return [rep(ndays=k), rep(day=self.day + timedelta(days=k), ndays=self.ndays - k)]
        if len(self.vars) > 1:
            a, b = halves(self.vars)
            return [rep(vars=a), rep(vars=b)]
        if len(self.hours) > 1 and self.group != STATIC:
            a, b = halves(self.hours)
            return [rep(hours=a), rep(hours=b)]
        tiles = split_area(self.area, self.grid)
        if tiles:
            return [rep(area=t, tiled=True) for t in tiles]
        return []


def split_area(area, grid):
    """Halve a rectangle along its longer side (in grid points) without overlap: the two parts
    share no grid point, so they can be mosaicked without duplicates. [] if too small."""
    n, w, s, e = area
    if e < w:
        e += 360
    nlat = int(round((n - s) / grid)) + 1
    nlon = int(round((e - w) / grid)) + 1
    wrap = lambda x: x - 360 if x > 180 else x
    if nlat >= nlon and nlat > 1:
        k = nlat // 2                       # points in the southern part
        mid = s + (k - 1) * grid
        return [(n, w, round(mid + grid, 6), wrap(e)), (round(mid, 6), w, s, wrap(e))]
    if nlon > 1:
        k = nlon // 2                       # points in the western part
        mid = w + (k - 1) * grid
        return [(n, w, s, wrap(round(mid, 6))), (n, wrap(round(mid + grid, 6)), s, wrap(e))]
    return []


def level_blocks(first: int, last: int) -> list[tuple[int, int]]:
    """Canonical blocks clipped to the wanted range."""
    out = []
    for a, b in era5.LEVEL_BLOCKS:
        lo, hi = max(a, first), min(b, last)
        if lo <= hi:
            out.append((lo, hi))
    return out


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# Days per request to *try* first (CDS size limits are not documented; the downloader learns the
# largest accepted size and shrinks from there). Single-level groups never cross a month boundary.
DEFAULT_SPANS = {ML: 7, LNSP: 31, GLNSP: 31, SP: 31, SL: 31, FLUX: 31}
ONE_DAY = {ML: 1, LNSP: 1, GLNSP: 1, SP: 1, SL: 1, FLUX: 1}


def _chunks(days: list[date], span: int, same_month: bool):
    """Consecutive runs of at most `span` days (and within one month if same_month)."""
    out, cur = [], []
    for d in days:
        if cur and (len(cur) >= span or (same_month and (d.year, d.month) != (cur[0].year, cur[0].month))):
            out.append(cur)
            cur = []
        cur.append(d)
    if cur:
        out.append(cur)
    return out


def plan(cfg: Config, spans: Optional[dict] = None) -> list[Request]:
    """All units needed for cfg, ordered by start day. `spans` = days per request by group."""
    spans = {**DEFAULT_SPANS, **(spans or {})}
    common = dict(domain=cfg.domain_tag, area=(cfg.north, cfg.west, cfg.south, cfg.east), grid=cfg.grid)
    pad = timedelta(days=era5.FLUX_PAD_DAYS)
    main_days = list(_daterange(cfg.start, cfg.end))
    flux_days = list(_daterange(cfg.start - pad, cfg.end + pad))

    units = []
    def add(group, days, levels):
        for ch in _chunks(days, spans[group], same_month=_GROUP_DATASET[group] == era5.DATASET_SFC):
            units.append(Request(group, ch[0], _GROUP_VARS[group], era5.HOURS, levels, ndays=len(ch), **common))
    add(SL, main_days, None)
    if cfg.pressure == "spectral":
        add(LNSP, main_days, (1, 1))
    elif cfg.pressure == "lnsp":
        add(GLNSP, main_days, (1, 1))
    else:
        add(SP, main_days, None)
    for blk in level_blocks(cfg.level_first, cfg.level_last):
        add(ML, main_days, blk)
    add(FLUX, flux_days, None)
    order = {STATIC: 0, SL: 1, SP: 1, FLUX: 2, LNSP: 3, GLNSP: 3, ML: 4}
    units.sort(key=lambda u: (u.day, order[u.group]))
    return [Request(STATIC, cfg.start, _GROUP_VARS[STATIC], (0,), None, **common)] + units
