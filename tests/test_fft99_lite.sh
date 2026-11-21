#!/bin/bash
# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

# Compares fft99_lite.f90 with libemos FFT99 (needs libemosR64 installed; skip otherwise).
set -e
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
gfortran -O1 -fdefault-real-8 "$here/fft99_driver.f90" -o "$tmp/emos" -lemosR64 2>/dev/null || { echo "SKIP: libemosR64 not available"; exit 0; }
gfortran -O1 -fdefault-real-8 "$here/fft99_driver.f90" "$here/../fortran/fft99_lite.f90" -o "$tmp/lite"
"$tmp/emos" > "$tmp/emos.txt"; "$tmp/lite" > "$tmp/lite.txt"
python3 - "$tmp/emos.txt" "$tmp/lite.txt" <<'P'
import sys
a, b = (open(f).read().split("\n") for f in sys.argv[1:])
worst = 0.0
for x, y in zip(a, b):
    if x.startswith("n="):
        assert x == y, (x, y)
    elif x.strip():
        worst = max(worst, abs(float(x) - float(y)))
assert len(a) == len(b)
print(f"max abs difference vs EMOS: {worst:.3e}")
sys.exit(0 if worst < 1e-9 else 1)
P
