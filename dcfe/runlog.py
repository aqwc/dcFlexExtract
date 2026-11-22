# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""Run logging. Every invocation of download/process/cleanup writes its own log file in <outdir>/logs/:

    <outdir>/logs/YYYYmmdd-HHMMSS_<command>.log   everything of that run (DEBUG detail, timestamps)
    <outdir>/logs/commands.log                    one comment line per invocation: when (date, weekday, time), command, exact command line

The log starts with two comment lines (# date weekday time, # the full command), then the command line that was used, the working directory, host, tool versions and the
parsed arguments. Afterwards it records requests sent to CDS (with their bodies), job state changes, files
saved (size, message count), and for post-processing the raw files indexed, the calc_etadot namelist and
command line, its result and every output file. The console shows the INFO lines only.
Secrets are never logged: the CDS key is read only inside the client and is not part of any argument.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shlex
import socket
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path

LOG = logging.getLogger("dcfe")


def _version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "not installed"


def command_line(argv: list[str]) -> str:
    """The line the user typed: the launcher exports it, otherwise reconstruct `python -m dcfe ...`."""
    return os.environ.get("DCFE_CMDLINE", "").strip() or "python -m dcfe " + shlex.join(argv)


def setup(outdir, cmd: str, argv: list[str], args: dict | None = None) -> Path:
    """Start logging for this run; returns the path of the log file."""
    logdir = Path(outdir) / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = logdir / f"{stamp}_{cmd}.log"
    n = 1
    while path.exists():                                   # two runs in the same second
        n += 1
        path = logdir / f"{stamp}_{cmd}_{n}.log"

    LOG.setLevel(logging.DEBUG)
    LOG.propagate = False
    for h in list(LOG.handlers):
        LOG.removeHandler(h)
        h.close()
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(fh)
    LOG.addHandler(ch)

    line = command_line(argv)
    started = datetime.now()
    when = f"{started:%Y-%m-%d %a %H:%M:%S}"          # date, weekday, time
    # the first lines of every log are comments: when it was started and the full command, ready to copy
    fh.stream.write(f"# {when}\n# {line}\n")
    fh.stream.flush()
    with open(logdir / "commands.log", "a", encoding="utf-8") as f:
        f.write(f"# {when} [{cmd}] {line}\n")

    LOG.debug("command line : %s", line)
    LOG.debug("python -m form: python -m dcfe %s", shlex.join(argv))
    LOG.debug("working dir  : %s", os.getcwd())
    LOG.debug("host         : %s (%s)", socket.gethostname(), platform.platform())
    LOG.debug("python       : %s %s", sys.version.split()[0], sys.executable)
    LOG.debug("versions     : eccodes %s, ecmwf-datastores-client %s, numpy %s",
              _version("eccodes"), _version("ecmwf-datastores-client"), _version("numpy"))
    if args is not None:
        LOG.debug("arguments    : %s", json.dumps(args, sort_keys=True, default=str))
    LOG.info("log file: %s", path)
    return path
