# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.
#
# Module list taken from flex_extract's Run/general_callscript.sh.

# Site file for CSC (Roihu). Modules first: nothing is installed by dcfe.sh unless a module cannot provide it.
# Always loaded: python-geo (Python with numpy etc.) and eccodes (kept up to date by CSC).
# Loaded only when the Fortran step is needed (setup, build, selftest, --pressure spectral): gcc.
# (Not yet exercised on Roihu with dcFlexExtract. If linking ecCodes' Fortran interface turns out to need more,
# e.g. openmpi or netcdf-fortran as in flex_extract's general_callscript.sh, add them to site_modules_fortran.)
type module >/dev/null 2>&1 || source /etc/profile.d/modules.sh 2>/dev/null || true

site_modules_base() {
  module load python-geo
  module load eccodes
}

site_modules_fortran() {
  module load gcc
}
