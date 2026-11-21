#!/usr/bin/env bash
# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# The module list and the calc_etadot self-test come from flex_extract's Run/general_callscript.sh
# (L. Haimberger, P. Seibert).

# dcFlexExtract launcher.   ./dcfe.sh setup | selftest | plan | download | process | cleanup   (-h for options)
set -euo pipefail
# the exact call is recorded in the run log (<outdir>/logs)
DCFE_CMDLINE=$(printf '%q ' "$0" "$@"); export DCFE_CMDLINE
ROOT=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)

# --- site: DCFE_SITE=csc|local, otherwise guessed from the host name
site=${DCFE_SITE:-}
if [[ -z $site ]]; then
  case "$(hostname -f 2>/dev/null || hostname)" in
    *csc.fi*|*roihu*|*puhti*|*mahti*) site=csc ;;
    *) site=local ;;
  esac
fi
# shellcheck source=/dev/null
source "$ROOT/sites/$site.sh"

PY=${DCFE_PY:-}
[[ -z $PY && -x $ROOT/.venv/bin/python ]] && PY=$ROOT/.venv/bin/python
PY=${PY:-python3}
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
EXE=$ROOT/fortran/calc_etadot

build() { make -C "$ROOT/fortran" -j"$(nproc)" calc_etadot; }

selftest() {
  [[ -x $EXE ]] || build
  local t; t=$(mktemp -d)
  cp "$ROOT"/fortran/selftest/fort.* "$t"/
  local out; out=$(cd "$t" && "$EXE" 2>&1 | tail -1) || true
  local ok=1
  [[ $out == *CONGRATULATIONS* ]] || ok=0
  cmp -s "$t/fort.15" "$ROOT/fortran/selftest/expected.fort.15" || ok=0
  rm -f "$t"/fort.*; rmdir "$t"
  if (( ok )); then echo "calc_etadot works"; else echo "calc_etadot self-test FAILED (modules/ecCodes?). Last line: $out" >&2; return 1; fi
}

case "${1:-}" in
  setup)    # python environment (eccodes + CDS client) and the Fortran executable
    [[ -x $ROOT/.venv/bin/python ]] || python3 -m venv --system-site-packages "$ROOT/.venv"
    "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
    build; selftest ;;
  build)    build ;;
  selftest) selftest ;;
  "")       sed -n 2p "$0"; exit 1 ;;
  process)  [[ -x $EXE ]] || { build; selftest; }; exec "$PY" -m dcfe "$@" ;;
  *)        exec "$PY" -m dcfe "$@" ;;
esac
