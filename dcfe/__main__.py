# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""dcFlexExtract command line:  plan | download | process | cleanup   (see README.md).

download, process and cleanup write a complete log of the run into <outdir>/logs/ (see runlog.py)."""
import argparse
import json
import sys
from pathlib import Path

from . import era5, runlog
from .config import Config
from .requests import plan
from .runlog import LOG


def _domain_args(p):
    p.add_argument("--start", required=True, help="YYYYMMDD")
    p.add_argument("--end", required=True, help="YYYYMMDD, inclusive")
    p.add_argument("--area", required=True, nargs=4, type=float, metavar=("N", "W", "S", "E"))
    p.add_argument("--grid", type=float, default=0.25)
    p.add_argument("--levels", nargs=2, type=int, default=[60, 137], metavar=("FIRST", "LAST"))


def _outdir_arg(p, what):
    p.add_argument("--outdir", default="out",
                   help=f"output directory: {what}; logs go to <outdir>/logs (default: out)")


def _spans(text):
    return {k.strip().upper(): int(v) for k, v in (kv.split("=") for kv in text.split(",") if kv)}


def build_parser():
    ap = argparse.ArgumentParser(prog="dcfe")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="list download units for a configuration (no network, no files)")
    _domain_args(p)
    _outdir_arg(p, "only used to show where the raw data would go; plan writes nothing")
    p.add_argument("--rawdir", default=None, help="raw data directory (default: <outdir>/raw)")
    p.add_argument("--show-request", action="store_true", help="also print the CDS request body")
    p.add_argument("--spans", default="", metavar="ML=7,LNSP=31", help="days per request, by group")

    d = sub.add_parser("download", help="download (resumable); re-run to continue")
    _domain_args(d)
    _outdir_arg(d, "raw data goes to <outdir>/raw unless --rawdir is given")
    d.add_argument("--rawdir", default=None, help="where raw GRIB files are stored (default: <outdir>/raw)")
    d.add_argument("--once", action="store_true", help="advance state once and exit (cron / short jobs)")
    d.add_argument("--poll", type=float, default=60, help="seconds between polls in loop mode")
    d.add_argument("--inflight-mars", type=int, default=2, help="open jobs in the MARS queue (model levels, LNSP)")
    d.add_argument("--inflight-sfc", type=int, default=3, help="open jobs for single-level data (not MARS)")
    d.add_argument("--spans", default="", metavar="ML=7,LNSP=31",
                   help="days per request to try first, by group (ML LNSP SL FLUX); refused sizes are learned and halved")

    pr = sub.add_parser("process", help="raw GRIB -> hourly FLEXPART files (uses calc_etadot)")
    _domain_args(pr)
    _outdir_arg(pr, "the hourly FLEXPART files are written here")
    pr.add_argument("--rawdir", default=None,
                    help="directory searched recursively for *.grb, any source (default: <outdir>/raw)")
    pr.add_argument("--exe", default=str(Path(__file__).resolve().parent.parent / "fortran" / "calc_etadot"))
    pr.add_argument("--scratch", default=None, help="scratch dir (default: <outdir>/.scratch)")
    pr.add_argument("--keep-scratch", action="store_true")
    pr.add_argument("--check", action="store_true", help="only report what is missing for each hour")

    c = sub.add_parser("cleanup", help="delete finished (successful) jobs stored in your CDS account")
    _outdir_arg(c, "only the log is written there")
    c.add_argument("--yes", action="store_true", help="really delete (default: only list how many)")
    return ap


def _cfg(a):
    rawdir = a.rawdir or str(Path(a.outdir) / "raw")
    return Config.make(a.start, a.end, a.area, a.grid, a.levels, rawdir=rawdir, outdir=a.outdir)


def cmd_process(a):
    from .gribcount import count_messages
    from .process import build_hour, hours, missing, out_name
    from .rawindex import RawIndex
    cfg = _cfg(a)
    LOG.info("raw data: %s   output: %s", cfg.rawdir, cfg.outdir)
    ix = RawIndex.from_dir(cfg.rawdir)
    LOG.info("indexed %d raw files", ix.files)
    for p in sorted(Path(cfg.rawdir).rglob("*.grb")):
        LOG.debug("raw file: %s (%d bytes)", p, p.stat().st_size)
    LOG.debug("index: %d flux, %d surface, %d static, %d LNSP, %d model-level messages",
              len(ix.flux), len(ix.sfc), len(ix.static), len(ix.lnsp), len(ix.ml))
    out = Path(cfg.outdir)
    out.mkdir(parents=True, exist_ok=True)
    scratch = Path(a.scratch) if a.scratch else out / ".scratch"
    bad = 0
    for T in hours(cfg):
        miss = missing(ix, cfg, T)
        if a.check or miss:
            LOG.info("%s: %s", out_name(cfg, T), "ok" if not miss else "MISSING " + ", ".join(miss))
            bad += bool(miss)
            continue
        existed = (out / out_name(cfg, T)).exists()
        f = build_hour(ix, cfg, T, a.exe, out, scratch, a.keep_scratch)
        if existed:
            LOG.info("exists, skipped: %s", f.name)
        else:
            LOG.info("wrote %s", f.name)
            LOG.debug("output %s: %d bytes, %d messages", f, f.stat().st_size, count_messages(str(f)))
    LOG.info("%s", "missing data for %d hour(s)" % bad if bad else "all hours complete")
    return 1 if bad else 0


def cmd_cleanup(a):
    from .client import DatastoresClient
    cl = DatastoresClient()
    ids = cl.list_successful()
    LOG.info("%d successful jobs stored at CDS", len(ids))
    if a.yes:
        for i in ids:
            cl.cleanup(i)
            LOG.debug("deleted CDS job %s", i)
        LOG.info("deleted")
    elif ids:
        LOG.info("re-run with --yes to delete them (they cannot be downloaded afterwards)")
    return 0


def cmd_download(a):
    from .client import DatastoresClient
    from .download import Downloader
    cfg = _cfg(a)
    LOG.info("raw data: %s", cfg.rawdir)
    dl = Downloader(cfg, DatastoresClient(),
                    max_inflight={era5.DATASET_MARS: a.inflight_mars, era5.DATASET_SFC: a.inflight_sfc},
                    poll_seconds=a.poll, spans=_spans(a.spans), log=LOG.info)
    ok = (dl.step() and dl.summary().get("failed", 0) == 0) if a.once else dl.run()
    LOG.info("%s", dl.summary())
    return 0 if ok or a.once else 1


def cmd_plan(a):
    units = plan(Config.make(a.start, a.end, a.area, a.grid, a.levels), _spans(a.spans))
    for u in units:
        print(f"{u.queue.split('-era5-')[1]:14s} {u.expected_messages:6d}  {u.relpath}")
        if a.show_request:
            print("   ", json.dumps(u.cds_request()))
    print(f"{len(units)} units; raw data would go to {a.rawdir or Path(a.outdir) / 'raw'}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    a = build_parser().parse_args(argv)
    if a.cmd == "plan":
        raise SystemExit(cmd_plan(a))
    runlog.setup(a.outdir, a.cmd, argv, vars(a))
    run = {"download": cmd_download, "process": cmd_process, "cleanup": cmd_cleanup}[a.cmd]
    try:
        rc = run(a)
    except KeyboardInterrupt:
        LOG.warning("interrupted by user")
        rc = 130
    except Exception:                                    # noqa: BLE001 - leave the traceback in the log
        LOG.exception("%s failed", a.cmd)
        raise
    LOG.debug("exit status %s", rc)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
