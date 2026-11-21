# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

import json
import os
from pathlib import Path

import pytest

from dcfe.__main__ import main
from dcfe import runlog

AREA = ["61", "21", "59", "25"]


def test_process_check_writes_log_and_command_history_in_outdir(tmp_path, monkeypatch):
    monkeypatch.delenv("DCFE_CMDLINE", raising=False)
    out = tmp_path / "out"
    argv = ["process", "--start", "20230830", "--end", "20230830", "--area", *AREA, "--levels", "60", "137",
            "--rawdir", str(tmp_path / "raw"), "--outdir", str(out), "--check"]
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 1                              # nothing downloaded: everything missing
    logs = sorted((out / "logs").glob("*_process.log"))
    assert len(logs) == 1
    text = logs[0].read_text()
    assert "python -m dcfe process --start 20230830" in text and "--check" in text   # the command line
    assert "arguments    :" in text and "working dir" in text and "versions" in text
    assert "EA02523083000: MISSING" in text
    cmds = (out / "logs" / "commands.log").read_text().splitlines()
    assert len(cmds) == 1 and "[process]" in cmds[0] and "--outdir" in cmds[0]
    runlog.LOG.handlers.clear()


def test_launcher_command_line_is_logged_verbatim(tmp_path, monkeypatch):
    monkeypatch.setenv("DCFE_CMDLINE", "./dcfe.sh process --start 20230830 --outdir 'my out'")
    runlog.setup(tmp_path, "process", ["process"])
    assert "command line : ./dcfe.sh process --start 20230830 --outdir 'my out'" in \
        next((tmp_path / "logs").glob("2*.log")).read_text()
    runlog.LOG.handlers.clear()


def test_second_run_gets_its_own_log_and_appends_history(tmp_path, monkeypatch):
    monkeypatch.delenv("DCFE_CMDLINE", raising=False)
    for _ in range(2):
        runlog.setup(tmp_path, "download", ["download", "--x"])
    assert len(list((tmp_path / "logs").glob("*_download*.log"))) == 2
    assert len((tmp_path / "logs" / "commands.log").read_text().splitlines()) == 2
    runlog.LOG.handlers.clear()


def test_downloader_details_go_to_the_log_file(tmp_path):
    from dcfe.config import Config
    from dcfe.download import Downloader
    from test_download import FakeClient, mkcfg, quiet, run
    cfg = mkcfg(tmp_path)
    logfile = runlog.setup(tmp_path / "out", "download", ["download"])
    run(Downloader(cfg, FakeClient(), **quiet()))
    text = logfile.read_text()
    runlog.LOG.handlers.clear()
    assert "REQUEST " in text and "reanalysis-era5" in text            # request bodies
    assert "SAVED   " in text and "bytes" in text                      # saved files
    assert "CLEANUP deleted CDS job" in text


def test_plan_accepts_the_same_options_as_the_other_commands_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as e:
        main(["plan", "--start", "20230830", "--end", "20230830", "--area", *AREA, "--levels", "60", "137",
              "--outdir", str(out)])
    assert e.value.code == 0
    assert f"raw data would go to {out / 'raw'}" in capsys.readouterr().out
    assert not out.exists()
