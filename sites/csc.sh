# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# Module list taken from flex_extract's Run/general_callscript.sh.

# Site file for CSC (Roihu): the modules the old general_callscript.sh used, which are all that is needed.
# (Module names are taken from that script; not yet exercised on Roihu with dcFlexExtract.)
type module >/dev/null 2>&1 || source /etc/profile.d/modules.sh 2>/dev/null || true
module load python-geo
module load gcc
module load openmpi
module load netcdf-c
module load netcdf-fortran
module load fftw
module load eccodes
