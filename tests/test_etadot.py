# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from dcfe import etadot, gribio

N = 40                                              # model levels of the synthetic atmosphere
ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "fortran" / "calc_etadot"


def hybrid():
    """Synthetic hybrid coefficients: pure pressure at the top, pure sigma at the ground, p00 = 101325."""
    x = np.linspace(0, 1, N + 1)
    B = x ** 2
    A = etadot.P00 * (x - B)
    return A, B


def eta_dot_from_H(H_half, ps, A, B):
    """Invert the conversion: build full-level eta_dot whose half-level flux is H_half (indices 0..N, zero at
    both ends). Full-level value = mean of the interface values."""
    out = {}
    for k in range(1, N + 1):
        dak, dbk = A[k] - A[k - 1], B[k] - B[k - 1]
        et = H_half[k - 1] + H_half[k]                 # = 2 * mean
        out[k] = et * (dak / etadot.P00 + dbk) / (2 * ps * (dak / ps + dbk))
    return out


@pytest.fixture
def atmosphere():
    A, B = hybrid()
    ps = np.array([98000.0, 100000.0, 101500.0])
    x = np.linspace(0, 1, N + 1)
    H = np.sin(np.pi * x)[:, None] * np.array([0.3, -0.2, 0.1])[None, :] * np.sin(3 * np.pi * x)[:, None]
    H[0] = 0
    H[-1] = 0                                          # eta_dot * dp/deta vanishes at the top and at the ground
    return A, B, ps, H


def test_ground_start_recovers_the_true_profile_for_any_range_ending_at_the_ground(atmosphere):
    A, B, ps, H = atmosphere
    ed = eta_dot_from_H(H, ps, A, B)
    for first in (1, 10, 25):
        out = etadot.half_level_flux({k: ed[k] for k in range(first, N + 1)}, ps, A, B, "ground")
        for k in range(first, N + 1):
            assert np.allclose(out[k], H[k], atol=1e-9), (first, k)
        assert np.allclose(out[N], 0)                  # the interface below the lowest level is the ground


def test_top_start_is_right_only_when_it_starts_at_level_1(atmosphere):
    A, B, ps, H = atmosphere
    ed = eta_dot_from_H(H, ps, A, B)
    full = etadot.half_level_flux(ed, ps, A, B, "top")
    assert all(np.allclose(full[k], H[k], atol=1e-9) for k in range(1, N + 1))
    first = 15
    part = etadot.half_level_flux({k: ed[k] for k in range(first, N + 1)}, ps, A, B, "top")
    err = {k: part[k] - H[k] for k in part}
    h = H[first - 1]                                   # the true value at the top of the first retrieved level
    assert np.abs(h).max() > 0.01                      # not zero there, so the assumption is wrong ...
    for k in range(first, N + 1):                      # ... and the error is +-h in alternate levels
        assert np.allclose(err[k], ((-1) ** (k - first)) * h, atol=1e-9)
    assert not np.allclose(part[N], 0)                 # non-zero vertical velocity at the ground


def test_ground_boundary_requires_the_lowest_level(atmosphere):
    A, B, ps, H = atmosphere
    ed = eta_dot_from_H(H, ps, A, B)
    with pytest.raises(ValueError, match="lowest model level"):
        etadot.half_level_flux({k: ed[k] for k in range(5, 20)}, ps, A, B, "ground")
    etadot.half_level_flux({k: ed[k] for k in range(5, 20)}, ps, A, B, "top")      # allowed
    with pytest.raises(ValueError):
        etadot.half_level_flux(ed, ps, A, B, "sideways")


@pytest.mark.skipif(not EXE.exists(), reason="calc_etadot not built")
def test_top_start_reproduces_calc_etadot_on_its_installation_test_data(tmp_path):
    """Our formula must be calc_etadot's: compare with the Fortran on the flex_extract installation test."""
    import eccodes as ec
    for f in (ROOT / "fortran" / "selftest").glob("fort.*"):
        shutil.copy(f, tmp_path)
    r = subprocess.run([str(EXE)], cwd=tmp_path, capture_output=True, text=True)
    assert "CONGRATULATIONS" in r.stdout + r.stderr
    out = gribio.read_all(tmp_path / "fort.15")
    ps = next(gribio.values(m) for m in out if gribio.get_int(m, "paramId") == 134)
    fortran = {gribio.get_int(m, "level"): gribio.values(m) for m in out if gribio.get_int(m, "paramId") == 77}
    pv = gribio.get_array(gribio.read_all(tmp_path / "fort.12")[0], "pv")
    A, B = pv[: len(pv) // 2], pv[len(pv) // 2:]
    raw = {gribio.get_int(m, "level"): gribio.values(m) for m in gribio.read_all(tmp_path / "fort.21")}
    mine = etadot.half_level_flux(raw, ps, A, B, "top")
    assert sorted(mine) == sorted(fortran) and len(mine) > 1
    for k in mine:
        assert np.allclose(mine[k], fortran[k], rtol=1e-4, atol=1e-6 * np.abs(fortran[k]).max()), k
