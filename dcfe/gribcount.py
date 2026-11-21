# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""Dependency-free GRIB message counter (GRIB1 and GRIB2) used to sanity-check downloads."""
from __future__ import annotations


def count_messages(path: str) -> int:
    """Number of complete GRIB messages in a file; -1 if the file is not a clean sequence of
    messages (truncated or containing junk)."""
    n = 0
    with open(path, "rb") as f:
        while True:
            head = f.read(16)
            if not head:
                return n
            if len(head) < 8 or head[:4] != b"GRIB":
                return -1
            edition = head[7]
            if edition == 2:
                length = int.from_bytes(head[8:16], "big")
            elif edition == 1:
                length = int.from_bytes(head[4:7], "big")
                if length & 0x800000:           # large-message convention (length coded in 120-byte units)
                    return -1
            else:
                return -1
            if length < 16:
                return -1
            f.seek(length - len(head), 1)
            # a seek past EOF does not fail, so verify the 7777 end marker
            f.seek(-4, 1)
            if f.read(4) != b"7777":
                return -1
            n += 1
