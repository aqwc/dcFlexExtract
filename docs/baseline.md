# Baseline: what the current flex_extract does (reference for dcFlexExtract)

## Requests actually sent (from an old run log, ERA5, 0.25 deg, CDS API, levels 30-137)
| group | dataset | type | levtype | params | time / step | per request |
|---|---|---|---|---|---|---|
| OG__ML | reanalysis-era5-complete | AN | ML | T/Q/U/V/ETADOT/CLWC/CIWC | 00..23, step 0 | date range of `DATE_CHUNK` days |
| SH__SL | reanalysis-era5-complete | AN | ML (level 1) | LNSP, grid `OFF` (spectral) | 00..23 | same |
| OG__SL | reanalysis-era5-single-levels | AN | SFC | SD/MSL/TCC/10U/10V/2T/2D/Z/LSM | 00..23 | same |
| OG_OROLSM__SL | reanalysis-era5-single-levels | AN | SFC | SDOR/CVL/CVH/FSR | 00, first date only | one per run |
| OG_acc_SL | reanalysis-era5-single-levels | FC | SFC | LSP/CP/SSHF/EWSS/NSSS/SSR | 06/18, step 1..12 (converted to valid times 00..23) | start-1 .. end+1 |

Area is sent as N/W/S/E, grid as `0.25/0.25`. Dates are padded for the fluxes (one day before and after).

## Known failure seen in the log
`403 ... cost limits exceeded. Your request is too large` for a 7-day, 137-level model-level request.
The old code exits on any error and loses the downloads of that run.

## Environment notes
- On Roihu `cdsapi` is a thin legacy wrapper over `ecmwf-datastores-client` (the traceback goes through
  `ecmwf/datastores/legacy_client.py`), so the async API is available there.
- Fortran `calc_etadot` reads `fort.10` (U,V), `fort.11` (T), `fort.12` (D), `fort.13` (LNSP, spectral),
  `fort.16` (surface), `fort.17` (Q), `fort.21` (ETADOT), `fort.22/23` (CLWC/CIWC) and the namelist `fort.4`.

## Reference output: `FE/ERA5/20230830/EA025230830NN` (names are PREFIX + YYMMDDHH)
- 566 messages per hourly file: 7 model-level params (T,U,V,Q,ETADOT,CLWC,CIWC) x 78 levels (60..137) = 546, plus 20 surface fields
  (CVL, CVH, Z, SP, SD, LSP, CP, SSHF, MSL, SDOR, TCC, 10U, 10V, 2T, 2D, LSM, SSR, EWSS, NSSS, FSR).
- `grib_ls` reports edition 2 for these example files, regular_ll, Ni=1440, Nj=361, lat 90..0, lon -179.75..180 (0.25 deg),
  so that example was NOT produced with FORMAT GRIB1. The target format needs to be confirmed (open question).
- Surface fields appear once per file; the flux fields carry the hour's valid time with step 0.
