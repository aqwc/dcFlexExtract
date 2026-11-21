# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

# Site file for a laptop/workstation: needs python3, and for the Fortran step gfortran, make and ecCodes with its
# Fortran interface (pkg-config eccodes_f90 or ECCODES_DIR). Nothing to load. Set DCFE_PY to use a specific Python.
site_modules_base() { :; }
site_modules_fortran() { :; }
