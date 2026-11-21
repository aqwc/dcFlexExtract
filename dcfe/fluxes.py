# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# Ported from flex_extract Source/Python/Mods/disaggregation.py (dapoly, darain; A. Philipp,
# L. Haimberger; method of Hittmeir, Philipp and Seibert 2018, GMD 11, 2503-2523) and changed here.

"""Flux fields (LSP, CP, SSHF, EWSS, NSSS, SSR): hourly accumulations -> instantaneous values.

ERA5 delivers hourly accumulations, labelled by the end of the hour. FLEXPART wants instantaneous
rates at each full hour. Like the original flex_extract, the accumulation a(t) (valid t = end of
the hour) is converted to a rate (precipitation: mm/h, others: W m-2 or N m-2) and then
disaggregated with the 4 surrounding hourly means:

    rate(T) = f( a(T-1), a(T), a(T+1), a(T+2) )     f = darain (rain) or dapoly (others)

Edges as in the original: first hour = a(first), last hour = a(last), second-last = f applied to
the reversed last four values.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Iterable

import numpy as np

# paramId -> (is_rain, divisor). Rain: m of water -> mm (divide by 1/1000). Others: J m-2 -> W m-2.
FLUX_PARAMS = {142: True, 143: True, 146: False, 176: False, 180: False, 181: False}
RAIN_DIV, FLUX_DIV = 1.0 / 1000.0, 3600.0


def dapoly(a):
    """Cubic polynomial disaggregation (original: Mods/disaggregation.py)."""
    return -1. / 12. * a[0] + 7. / 12. * a[1] + 7. / 12. * a[2] - 1. / 12. * a[3]


def darain(a):
    """Modified linear disaggregation for rain (original: Mods/disaggregation.py). Negative input
    values are clipped to zero (done on copies here, the original clipped in place)."""
    xa, xb, xc, xd = (np.where(x < 0., 0., x) for x in a)
    xac = 0.5 * xb
    m = xa + xc > 0.
    xac[m] = xb[m] * xc[m] / (xa[m] + xc[m])
    xbd = 0.5 * xc
    m = xb + xd > 0.
    xbd[m] = xb[m] * xc[m] / (xb[m] + xd[m])
    return xac + xbd


def to_rate(values: np.ndarray, param_id: int) -> np.ndarray:
    return values / (RAIN_DIV if FLUX_PARAMS[param_id] else FLUX_DIV)


def disaggregate(series: dict[datetime, np.ndarray], rain: bool) -> dict[datetime, np.ndarray]:
    """series: valid time -> hourly mean rate (already converted). Returns instantaneous rate at the
    same times. Needs at least 4 consecutive hours."""
    times = sorted(series)
    if len(times) < 4:
        raise ValueError("need at least 4 consecutive hourly flux values")
    for t0, t1 in zip(times, times[1:]):
        if t1 - t0 != timedelta(hours=1):
            raise ValueError(f"flux data not hourly-contiguous between {t0} and {t1}")
    f = darain if rain else dapoly
    a = [series[t] for t in times]
    out = {times[0]: a[0], times[-1]: a[-1]}
    for i in range(1, len(times) - 2):
        out[times[i]] = f([a[i - 1], a[i], a[i + 1], a[i + 2]])
    out[times[-2]] = f([a[-1], a[-2], a[-3], a[-4]])
    return out
