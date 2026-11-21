# dcFlexExtract

ERA5 → hourly FLEXPART input files, with the download **decoupled** from the post-processing.

* **download** asks CDS for the data, survives interruptions and days-long queues, and never throws away
  what it already has.
* **process** turns any directory of compliant ERA5 GRIB files (downloaded by `download` *or by hand*) into
  hourly FLEXPART files, running the Fortran `calc_etadot`.

Only ERA5 is supported. You choose four things:

| option | meaning |
|---|---|
| `--start` / `--end` | the dates you want (`YYYYMMDD`); how they are chunked for CDS is not your concern |
| `--area N W S E` | latitude/longitude rectangle, degrees |
| `--grid` | `0.25` (default) or `0.5` |
| `--levels FIRST LAST` | model levels, default `60 137` (137 is the surface level) |
| `--outdir DIR` | where everything of the run goes (default `out`): hourly files, raw data in `DIR/raw`, logs in `DIR/logs` |

## Origin and licence

dcFlexExtract builds on **flex_extract** by **Anne Philipp, Leopold Haimberger and Petra Seibert**
(https://www.flexpart.eu/wiki/FpInputMetEcmwf): the processing chain, the Fortran program `calc_etadot` and the
flux disaggregation come from their work, and we are grateful for it. Please cite Tipka, Haimberger and Seibert,
Geosci. Model Dev. 13, 5277-5310, 2020 (https://doi.org/10.5194/gmd-13-5277-2020) when you use this software,
and Hittmeir, Philipp and Seibert, GMD 11, 2503-2523, 2018 for the flux disaggregation. `NOTICE.md` lists
exactly what was taken, what was changed, and the third-party material.

Licence: **CC BY 4.0**, as for flex_extract (`LICENSE`); `fortran/Makefile` is GPL-2.0-only
(`LICENSES/GPL-2.0-only.txt`) because it is adapted from a flex_extract makefile under that licence.

## Install

```
./dcfe.sh setup        # python venv (+eccodes, ecmwf-datastores-client), builds fortran/calc_etadot, self-test
./dcfe.sh selftest     # re-run just the calc_etadot check (compares fort.15 byte for byte)
```

Needs gfortran, make and ecCodes with its Fortran interface (pkg-config `eccodes_f90`, or `ECCODES_DIR`).
EMOS is **not** needed (`fortran/fft99_lite.f90` replaces it).
A working `~/.cdsapirc` (`url:` and `key:` lines) is read for CDS access.

**CSC (Roihu):** `dcfe.sh` loads `sites/csc.sh` automatically (python-geo, gcc, openmpi, netcdf-c,
netcdf-fortran, fftw, eccodes — the modules from the old `general_callscript.sh`). Force a site with
`DCFE_SITE=csc|local`. Not yet exercised on Roihu with dcFlexExtract.

## Use

```
A="--start 20230830 --end 20230902 --area 61 21 59 25 --grid 0.25 --levels 60 137 --outdir /scratch/me/era5_run1"

./dcfe.sh plan     $A            # what would be requested (units, expected message counts)
./dcfe.sh download $A            # loop until everything is downloaded; safe to stop (Ctrl-C) and restart
./dcfe.sh process  $A --check    # what is still missing for each hour
./dcfe.sh process  $A            # writes <outdir>/EA025YYMMDDHH
```

Run `download` in `tmux`/`screen` on a login node or laptop: CDS queues can take days and a Slurm job
cannot cover them. The loop only sleeps and polls. `--once` advances one step and exits (cron or a short
job). Use the same `--outdir` for `download` and `process`: raw data is kept in `<outdir>/raw` (override with
`--rawdir`), the hourly files go to `<outdir>`. On HPC point `--outdir` to scratch.

### Running the download from cron (`--once`)

Instead of a long-running loop, `download --once` does one pass and exits: it fetches the jobs that have
finished, deletes them at CDS, submits new pending units (up to the per-queue limits) and prints a summary
such as `{'done': 5, 'submitted': 2}`. Repeat it until everything is `done`. Use identical options every time.
A lock on the manifest stops a second copy from starting while one is still working.

```
# crontab -e   (every 30 minutes; use absolute paths, cron has no login environment)
*/30 * * * * cd /home/me/dcFlexExtract && ./dcfe.sh download --once --start 20230830 --end 20230902 --area 61 21 59 25 --grid 0.25 --levels 60 137 --outdir /scratch/me/era5_run1 >> /scratch/me/era5_run1_cron.out 2>&1
```

* The exit status is 0 even if some units failed; look for `FAILED` in `<outdir>/logs/` or run
  `./dcfe.sh download --once ...` by hand and read the summary line.
* A run can take a while when large files are fetched; cron will not start a second copy meanwhile
  (the manifest lock refuses it, and that attempt exits).
* Remove the cron line when the summary shows only `done`, then run `process`.
* Whether cron is allowed depends on the machine; on CSC login nodes use `tmux` and the normal loop mode
  instead. The `--once` mode is also suitable for a short Slurm job, but not for waiting out a CDS queue.

### Logs

Every `download`, `process` and `cleanup` run writes a log in `<outdir>/logs/`:

* `YYYYmmdd-HHMMSS_<command>.log` – one file per run, with timestamps. It starts with the exact command line
  used (as typed to `dcfe.sh`), working directory, host, Python/ecCodes/CDS-client versions and all arguments.
  Then: every request sent to CDS (full body) and its job id, job state changes, retries/splits/errors, every
  file saved (path, bytes, message count) and CDS job deleted; for `process` the raw files indexed, which raw
  files each hour was built from, the `calc_etadot` namelist, command and result, and every output file
  (path, bytes, message count). The console shows only the short INFO lines.
* `commands.log` – one line per invocation (time, command, command line), appended across runs.

`plan` writes nothing. The CDS key is never logged.

### What the downloader does

* One unit = a few days × one group (model levels, LNSP, surface, fluxes, static). Files are named after
  their content, so a restart re-uses finished files and re-attaches to jobs still queued at CDS (job ids
  are kept in `raw/<domain>/manifest.json`). A file is only accepted if its GRIB message count is right.
* Too large for CDS? The unit is split: fewer days → variables → hours → geographic tiles. **Levels are
  never split.** The largest accepted size per group is learned and reused.
* Queues: MARS (`reanalysis-era5-complete`: model levels, LNSP) allows one running request per user, so
  `--inflight-mars` defaults to 2; single-level data is not MARS and runs `--inflight-sfc` (3) jobs in
  parallel. Each finished CDS job is deleted after a verified download. `./dcfe.sh cleanup` lists
  successful jobs still stored in your account, `cleanup --yes` deletes them.

### Your own data

Put GRIB files anywhere under `--rawdir`; `process` indexes them by content (not by file name) and
reports missing fields. Required per hour: T U V Q ETADOT CLWC CIWC on all chosen levels, spectral LNSP,
the 9 surface fields (SD MSL TCC 10U 10V 2T 2D Z LSM), 6 fluxes (LSP CP SSHF EWSS NSSS SSR, accumulated, from
the 06/18 forecasts incl. the day before/after) and the 4 static fields (SDOR CVL CVH FSR).

### Adding upper levels later

Re-run `download` with e.g. `--levels 1 137`: only the missing block (levels 1–59) is requested.
Then run `process` with `--levels 1 137` into a **new** `--outdir`; existing output files are skipped, not
overwritten, so reusing the old outdir would leave the old 60–137 files in place.

## Output

`EA025YYMMDDHH` (prefix `EA` + grid×100) holds, per hour: U V ETADOT T SP Q on all levels, CLWC, CIWC,
6 fluxes (disaggregated to instantaneous rates), 9 surface fields, 4 static fields; mixed GRIB1/GRIB2
as delivered by CDS (FLEXPART v11 reads GRIB1, GRIB2 and mixed). SP is computed by `calc_etadot` from the
spectral LNSP. Checked against an old flex_extract hourly file (566 messages) with `--etadot-boundary top`:
identical layout and surface fields; model-level fields differ by at most 2.5e-4 of a field's maximum (ETADOT
near the surface), others far less.

### Vertical velocity (ETADOT) and the integration boundary

ERA5 gives `eta_dot` on full levels; FLEXPART needs `eta_dot * dp/deta` on half levels, which `calc_etadot`
obtains with a running sum over the levels. That sum needs a starting value. flex_extract starts at the top of
the **retrieved** levels with 0, which is only right when level 1 is included. For e.g. levels 60-137 the true
value there is not zero (about 0.04 Pa/s in a test over southern Finland), and the error appears with
alternating sign in every level and leaves a non-zero vertical velocity at the ground. dcFlexExtract therefore
integrates upward from the ground, where the value is exactly zero, which is correct for any level range ending
at the lowest level (checked against mass continuity: `livetest/etadot_continuity_test.py`).

* `--etadot-boundary ground` (default): the corrected ETADOT. The Fortran step still runs; before its ETADOT is
  replaced, our own implementation of its calculation must reproduce it (otherwise the run stops).
* `--etadot-boundary top`: flex_extract's behaviour, for reproducing earlier output.

Output files that already exist are skipped, so use a new `--outdir` when you switch the boundary. If the levels
do not end at the lowest model level the ground boundary cannot be used and a warning is logged.

## Tests

`./.venv/bin/python -m pytest tests` (no network needed; CDS is replaced by a fake client).
`tests/test_fft99_lite.sh` compares the EMOS-free FFT with EMOS if EMOS is installed.

## Layout

```
dcfe/         config, request builder, downloader (+manifest), GRIB index, flux disaggregation, process
fortran/      calc_etadot sources, Makefile, selftest/ (installation test data)
sites/        csc.sh, local.sh (module loads)
NOTICE.md     origin, authors, modifications, third-party material; LICENSE, LICENSES/ the licence texts
docs/         baseline.md (what the old flex_extract requests and produces)
dcfe.sh       launcher
```
