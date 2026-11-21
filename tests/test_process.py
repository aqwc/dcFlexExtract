# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

from datetime import datetime

from dcfe.config import Config
from dcfe.process import hours, namelist, out_name, prefix_for


def test_prefix_and_names():
    assert prefix_for(0.25) == "EA025" and prefix_for(0.5) == "EA050"
    cfg = Config.make("20230830", "20230830", (61, 21, 59, 25), 0.25)
    assert out_name(cfg, datetime(2023, 8, 30, 14)) == "EA02523083014"


def test_hours_cover_start_00_to_end_23():
    cfg = Config.make("20230830", "20230831", (61, 21, 59, 25), 0.25)
    hs = hours(cfg)
    assert len(hs) == 48 and hs[0] == datetime(2023, 8, 30, 0) and hs[-1] == datetime(2023, 8, 31, 23)


def test_namelist_matches_reference_style():
    cfg = Config.make("20230830", "20230830", (61, 21, 59, 25), 0.25, levels=(60, 137))
    nl = namelist(cfg, 639)
    assert "maxl = 17," in nl and "maxb = 9," in nl and "mlevel = 137," in nl
    assert 'mlevelist = "60/to/137"' in nl and "mnauf = 639," in nl
    assert "rlo0 = 21.0" in nl and "rlo1 = 25.0" in nl and "rla0 = 59.0" in nl and "rla1 = 61.0" in nl
    assert "meta = 1," in nl and "mdpdeta = 1" in nl and "mgauss = 0" in nl


def test_namelist_dateline_wrap():
    cfg = Config.make("20230830", "20230830", (10, 170, 0, -170), 0.5)
    assert "maxl = 41," in namelist(cfg, 639)


def test_missing_reports_the_pressure_source_that_was_chosen():
    from types import SimpleNamespace
    from dcfe import era5
    from dcfe.process import missing
    T = datetime(2023, 8, 30, 14)
    ix = SimpleNamespace(missing_for=lambda t: [], lnsp={}, glnsp={}, sp={}, ml={})
    for src, word in (("spectral", "spectral"), ("lnsp", "gridded"), ("sp", "surface pressure")):
        cfg = Config.make("20230830", "20230830", (61, 21, 59, 25), 0.25, pressure=src)
        assert any(word in m for m in missing(ix, cfg, T)), src
    ix.sp[T] = object()        # only the chosen source counts
    cfg = Config.make("20230830", "20230830", (61, 21, 59, 25), 0.25, pressure="lnsp")
    assert any("gridded" in m for m in missing(ix, cfg, T))
