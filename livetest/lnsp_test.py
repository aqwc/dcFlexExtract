# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""One-off test: gridded LNSP (one hour, test box) from MARS, to compare exp(LNSP) with the reference SP."""
import json, sys, time
from dcfe.client import DatastoresClient

c = DatastoresClient()
body = {"class": "ea", "expver": "1", "stream": "oper", "type": "an", "levtype": "ml",
        "date": "20230830", "time": "14", "levelist": "1", "param": "152.128",
        "grid": "0.25/0.25", "area": "61/21/59/25", "accuracy": "24"}
import os
if os.path.exists("livetest/lnspgrid/job.json"):          # re-attach after a restart / new session
    job = json.load(open("livetest/lnspgrid/job.json"))["job"]
    print("re-attached to", job, flush=True)
else:
    job = c.submit("reanalysis-era5-complete", body)
    json.dump({"job": job, "body": body}, open("livetest/lnspgrid/job.json", "w"))
    print("submitted", job, flush=True)
while True:
    st, msg = c.poll(job)
    if st in ("done", "failed"):
        break
    time.sleep(60)
print(st, msg, flush=True)
if st == "done":
    c.download(job, "livetest/lnspgrid/lnsp_grid.grb")
    c.cleanup(job)
    print("downloaded", flush=True)
