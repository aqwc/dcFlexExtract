# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

from datetime import datetime, timedelta

import numpy as np
import pytest

from dcfe.fluxes import dapoly, darain, disaggregate


def series(vals):
    t0 = datetime(2023, 8, 30)
    return {t0 + timedelta(hours=i): np.full((2, 3), float(v)) for i, v in enumerate(vals)}


def test_constant_flux_is_unchanged():
    for rain in (True, False):
        out = disaggregate(series([5.0] * 8), rain)
        assert all(np.allclose(v, 5.0) for v in out.values())


def test_linear_ramp_poly_is_exact_at_hour_boundaries():
    # hourly means of a linear instantaneous flux r(t) = t  ->  mean over [k-1,k] = k - 0.5
    s = series([k - 0.5 for k in range(10)])
    out = disaggregate(s, rain=False)
    times = sorted(out)
    for i in range(1, len(times) - 2):
        assert np.allclose(out[times[i]], i)       # instantaneous value at the hour boundary T=i


def test_rain_stays_nonnegative_and_conserves_zero():
    out = disaggregate(series([0, 0, 2.0, 0, 0, 0]), rain=True)
    assert all((v >= 0).all() for v in out.values())
    assert np.allclose(out[sorted(out)[0]], 0)


def test_negative_rain_is_clipped_without_mutating_input():
    s = series([1, -1, 1, 1, 1])
    before = {t: v.copy() for t, v in s.items()}
    disaggregate(s, rain=True)
    assert all(np.array_equal(s[t], before[t]) for t in s)


def test_gap_and_too_short_are_rejected():
    s = series([1] * 6)
    del s[sorted(s)[3]]
    with pytest.raises(ValueError, match="contiguous"):
        disaggregate(s, False)
    with pytest.raises(ValueError, match="at least 4"):
        disaggregate(series([1, 2, 3]), False)


def test_edges_follow_original_rules():
    s = series([1, 2, 3, 4, 5, 6])
    t = sorted(s)
    out = disaggregate(s, False)
    assert np.allclose(out[t[0]], 1) and np.allclose(out[t[-1]], 6)
    assert np.allclose(out[t[-2]], dapoly([s[t[-1]], s[t[-2]], s[t[-3]], s[t[-4]]]))
