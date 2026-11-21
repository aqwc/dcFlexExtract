# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

from datetime import date

import pytest

from dcfe import era5
from dcfe.config import Config
from dcfe.requests import DEFAULT_SPANS, FLUX, LNSP, ML, ONE_DAY, SL, STATIC, level_blocks
from dcfe.requests import plan as _plan


def plan(c, spans=ONE_DAY):
    return _plan(c, spans)


def cfg(**kw):
    base = dict(start="20260105", end="20260107", area=(60, 20, -10, 130), levels=(60, 137), pressure="spectral")
    base.update(kw)
    return Config.make(**base)


def test_config_validation():
    with pytest.raises(ValueError):
        cfg(end="20260101")
    with pytest.raises(ValueError):
        cfg(area=(-10, 20, 60, 130))
    with pytest.raises(ValueError):
        cfg(grid=0.3)
    with pytest.raises(ValueError):
        cfg(levels=(0, 137))


def test_level_blocks_clipped_and_aligned():
    assert level_blocks(1, 137) == [(1, 59), (60, 137)]
    assert level_blocks(60, 137) == [(60, 137)]          # default: one block
    assert level_blocks(40, 100) == [(40, 59), (60, 100)]
    # extending 60-137 to 1-137 only adds a block; the existing block is unchanged
    assert set(level_blocks(60, 137)) < set(level_blocks(1, 137))


def test_plan_days_and_groups():
    units = plan(cfg())
    by = lambda g: [u for u in units if u.group == g]
    assert len(by(STATIC)) == 1 and by(STATIC)[0].day == date(2026, 1, 5)
    assert [u.day.day for u in by(SL)] == [5, 6, 7]
    assert [u.day.day for u in by(LNSP)] == [5, 6, 7]
    # fluxes padded by one day on both sides
    assert [u.day.day for u in by(FLUX)] == [4, 5, 6, 7, 8]
    assert len(by(ML)) == 3 * 1          # default levels 60-137: one block per day
    assert len([u for u in plan(cfg(levels=(1, 137))) if u.group == ML]) == 3 * 2


def test_relpaths_unique_deterministic_and_domain_scoped():
    u1, u2 = plan(cfg()), plan(cfg())
    assert [u.relpath for u in u1] == [u.relpath for u in u2]
    assert len({u.relpath for u in u1}) == len(u1)
    other = plan(cfg(area=(61, 20, -10, 130)))
    assert not ({u.relpath for u in u1} & {u.relpath for u in other})
    assert any(u.relpath.endswith("/20260105/ML_all_L060-137.grb") for u in u1)


def test_two_queues():
    queues = {u.queue for u in plan(cfg())}
    assert queues == {era5.DATASET_MARS, era5.DATASET_SFC}


def test_mars_request_matches_old_flex_extract():
    u = next(u for u in plan(cfg()) if u.group == ML)
    r = u.cds_request()
    assert r["class"] == "ea" and r["stream"] == "oper" and r["type"] == "an" and r["levtype"] == "ml"
    assert r["param"] == "130.128/131.128/132.128/133.128/77.128/246.128/247.128"
    assert r["time"].split("/") == [f"{h:02d}" for h in range(24)]
    assert r["area"] == "60/20/-10/130" and r["grid"] == "0.25/0.25"
    assert r["levelist"] == "60/to/137" and r["accuracy"] == "24"
    lnsp = next(u for u in plan(cfg()) if u.group == LNSP).cds_request()
    assert lnsp["param"] == "152.128" and lnsp["grid"] == "OFF" and lnsp["levelist"] == "1"


def test_single_level_request():
    u = next(u for u in plan(cfg()) if u.group == FLUX)
    r = u.cds_request()
    assert r["variable"][0] == "large_scale_precipitation" and len(r["variable"]) == 6
    assert (r["year"], r["month"], r["day"]) == ("2026", "01", ["04"])
    assert r["time"][0] == "00:00" and len(r["time"]) == 24
    assert r["area"] == [60.0, 20.0, -10.0, 130.0] and r["grid"] == [0.25, 0.25]


def test_expected_messages_match_reference_file():
    """Reference EA...NN file: 566 msgs = 7*78 (levels 60-137) + 20 surface, per hour."""
    c = cfg(start="20230830", end="20230830", levels=(60, 137))
    one_hour = 0
    for u in plan(c):
        if u.group == ML:
            one_hour += u.expected_messages // 24
        elif u.group in (SL, LNSP):
            one_hour += u.expected_messages // 24
    # ML 546 + SL 9 + LNSP 1 (-> SP in the output); fluxes (6) + static (4) complete the 566 together
    assert one_hour == 546 + 9 + 1
    extra = sum(u.expected_messages // 24 for u in plan(c) if u.group == FLUX and u.day.day == 30)
    assert extra == 6


@pytest.mark.parametrize("group", [ML, SL, FLUX, LNSP])
def test_variable_and_hour_splits_cover_exactly_and_keep_levels(group):
    u = next(u for u in plan(cfg()) if u.group == group)
    # follow only the variable/hour part of the ladder (tiles are tested separately)
    stack, leaves = [u], []
    while stack:
        r = stack.pop()
        parts = r.split()
        if parts and not parts[0].tiled:
            stack.extend(parts)
        else:
            leaves.append(r)
    assert len({x.relpath for x in leaves}) == len(leaves)
    assert all(x.levels == u.levels and x.area == u.area for x in leaves)
    assert sum(x.expected_messages for x in leaves) == u.expected_messages
    assert all(len(x.vars) == 1 and len(x.hours) == 1 for x in leaves)


@pytest.mark.parametrize("area,grid", [((61, 21, 59, 25), 0.25), ((60.5, -3.5, 50, 4.5), 0.5),
                                       ((10, 170, 0, 190), 0.5), ((5, 5, 5, 9), 0.25)])
def test_tiles_cover_domain_exactly_without_overlap(area, grid):
    from dcfe.requests import split_area

    def points(a):
        n, w, s_, e = a
        if e < w:
            e += 360
        return {(round(s_ + i * grid, 4), round((w + j * grid + 180) % 360 - 180, 4))
                for i in range(int(round((n - s_) / grid)) + 1)
                for j in range(int(round((e - w) / grid)) + 1)}

    def leaves(a):
        t = split_area(a, grid)
        return [a] if not t else [x for p in t for x in leaves(p)]

    ls = leaves(area)
    total = 0
    union = set()
    for x in ls:
        p = points(x)
        assert len(p) == 1                      # recursion ends at single grid points
        total += len(p)
        union |= p
    assert total == len(union) == len(points(area))
    assert union == points(area)


def test_split_order_variables_then_hours_then_tiles():
    u = next(u for u in plan(cfg()) if u.group == ML)
    a, b = u.split()
    assert a.hours == u.hours and not a.tiled and len(a.vars) + len(b.vars) == len(u.vars)
    single = a
    while len(single.vars) > 1:
        single = single.split()[0]
    h1, h2 = single.split()
    assert h1.vars == h2.vars and h1.area == single.area and not h1.tiled
    one = h1
    while len(one.hours) > 1:
        one = one.split()[0]
    t1, t2 = one.split()
    assert t1.tiled and t2.tiled and t1.relpath != t2.relpath and t1.levels == one.levels


def test_static_never_split_by_hours():
    u = plan(cfg())[0]
    assert u.group == STATIC
    leaf = u
    while leaf.split() and not leaf.split()[0].tiled:
        leaf = leaf.split()[0]
    assert len(leaf.vars) == 1 and leaf.hours == (0,)


def test_small_domain_tiles_down_to_one_point_then_stops():
    c = Config.make("20260105", "20260105", (61, 21, 59, 25), 0.25, pressure="spectral")
    r = next(u for u in plan(c) if u.group == STATIC)     # one hour: ladder goes vars -> tiles
    while len(r.vars) > 1:
        r = r.split()[0]
    n = 0
    while r.split():
        r = r.split()[0]
        n += 1
        assert n < 20
    assert r.area[0] == r.area[2] and r.area[1] == r.area[3]


def test_multi_day_units_respect_spans_and_months():
    c = Config.make("20230829", "20230904", (61, 21, 59, 25), 0.25, pressure="spectral")       # crosses a month boundary
    units = _plan(c, {ML: 3, LNSP: 31, SL: 31, FLUX: 31})
    ml = [u for u in units if u.group == ML]
    assert [(u.day.day, u.ndays) for u in ml] == [(29, 3), (1, 3), (4, 1)]
    assert [u.ndays for u in units if u.group == LNSP] == [7]             # MARS: month boundary irrelevant
    sl = [u for u in units if u.group == SL]
    assert [(u.day.month, u.day.day, u.ndays) for u in sl] == [(8, 29, 3), (9, 1, 4)]   # single-levels: split at month end
    assert all(len({d.month for d in u.days}) == 1 for u in units if u.group in (SL, FLUX))
    # every day covered exactly once per group
    for g in (ML, LNSP, SL):
        days = sorted(d for u in units if u.group == g for d in u.days)
        assert days == sorted(set(days)) and len(days) == 7


def test_multi_day_requests_and_message_counts():
    c = Config.make("20230830", "20230901", (61, 21, 59, 25), 0.25, pressure="spectral")
    u = next(u for u in _plan(c, {ML: 3}) if u.group == ML)
    r = u.cds_request()
    assert r["date"] == "20230830/to/20230901"
    assert u.expected_messages == 3 * 7 * 78 * 24
    assert u.relpath.split("/")[1] == "20230830-20230901"
    lnsp = next(u for u in _plan(c) if u.group == LNSP)
    assert lnsp.ndays == 3 and lnsp.expected_messages == 72
    sl = next(u for u in _plan(c) if u.group == SL)
    assert sl.ndays == 2 and sl.cds_request()["day"] == ["30", "31"] and sl.expected_messages == 2 * 9 * 24


def test_split_reduces_days_first_and_covers_exactly():
    c = Config.make("20230830", "20230905", (61, 21, 59, 25), 0.25, pressure="spectral")
    u = next(u for u in _plan(c, {ML: 7}) if u.group == ML)
    a, b = u.split()
    assert (a.ndays, b.ndays) == (4, 3) and b.day == a.last_day + __import__("datetime").timedelta(days=1)
    assert a.vars == b.vars == u.vars and a.hours == u.hours and not a.tiled
    assert a.expected_messages + b.expected_messages == u.expected_messages


def test_pressure_source_selects_where_sp_comes_from():
    from dcfe.requests import LNSP, SP
    got = {src: {u.group for u in plan(cfg(pressure=src))} & {LNSP, SP} for src in ("lnsp", "sp", "spectral")}
    assert got == {"lnsp": set(), "sp": {SP}, "spectral": {LNSP}}       # lnsp rides inside the model-level request
    assert era5.DEFAULT_PRESSURE == "lnsp"
    with pytest.raises(ValueError):
        cfg(pressure="bogus")


def test_gridded_lnsp_is_merged_into_the_first_model_level_request():
    ml = [u for u in plan(cfg(pressure="lnsp", levels=(60, 137))) if u.group == ML]
    assert all(u.has_lnsp and u.vars[-1] == "LNSP" for u in ml)
    body = ml[0].cds_request()
    assert body["param"].endswith("/152.128") and body["grid"] == "0.25/0.25"
    # CDS refuses '1/60/to/137'; the levels must be written out (verified live 2026-11-21)
    assert body["levelist"] == "/".join(["1"] + [str(i) for i in range(60, 138)]) and "to" not in body["levelist"]
    # level 1 comes along for every model-level variable, LNSP exists on level 1 only
    assert ml[0].expected_messages == (7 * 79 + 1) * 24 * ml[0].ndays
    assert "all-LNSP" in ml[0].relpath


def test_lnsp_with_levels_from_1_goes_to_the_first_block_only_and_without_extra_level():
    ml = [u for u in plan(cfg(pressure="lnsp", levels=(1, 137))) if u.group == ML]
    first = [u for u in ml if u.levels == (1, 59)]
    other = [u for u in ml if u.levels == (60, 137)]
    assert all(u.has_lnsp for u in first) and not any(u.has_lnsp for u in other)
    assert first[0].cds_request()["levelist"] == "1/to/59"
    assert first[0].expected_messages == (7 * 59 + 1) * 24 * first[0].ndays
    assert other[0].expected_messages == 7 * 78 * 24 * other[0].ndays


def test_split_of_a_unit_with_lnsp_covers_exactly_the_same_messages():
    u = next(u for u in plan(cfg(pressure="lnsp", start="20260105", end="20260105")) if u.group == ML)
    todo, leaves = [u], []
    while todo:                                           # follow the whole split ladder down to the leaves
        x = todo.pop()
        parts = [] if x.tiled or (len(x.vars) == 1 and len(x.hours) > 1) else x.split()   # stop before the tiles
        if parts:
            assert all(p.levels == x.levels for p in parts)            # levels are never split
            todo += parts
        else:
            leaves.append(x)
    assert [l for l in leaves if l.has_lnsp] and all(l.levels == u.levels for l in leaves)
    lnsp_only = [l for l in leaves if l.vars == ("LNSP",)]
    assert all(l.cds_request()["levelist"] == "1" for l in lnsp_only)
    assert lnsp_only and all(l.expected_messages == len(l.hours) for l in lnsp_only)


def test_sp_request_body():
    from dcfe.requests import SP
    s = next(u for u in plan(cfg(pressure="sp")) if u.group == SP)
    assert s.dataset == era5.DATASET_SFC and s.cds_request()["variable"] == ["surface_pressure"]
    assert s.expected_messages == 24 * s.ndays
