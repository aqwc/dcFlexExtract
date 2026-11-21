# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""Can gridded LNSP (model level 1 only) be requested together with other model-level data in ONE MARS request?
One hour, temperature + LNSP, levelist 1/60/61/.../137 written out (the form 1/60/to/137 makes CDS answer HTTP 500), test box. Re-attaches to the saved job when run again.
usage (repository root):  PYTHONPATH=. python -u livetest/mars_structure_test.py"""
import json
import os
import time

from dcfe.client import DatastoresClient

JOB = "livetest/structtest/job.json"
BODY = {"class": "ea", "expver": "1", "stream": "oper", "type": "an", "levtype": "ml", "date": "20230830",
        "time": "14", "levelist": "/".join(["1"] + [str(i) for i in range(60, 138)]), "param": "130.128/152.128", "grid": "0.25/0.25",
        "area": "61/21/59/25", "accuracy": "24"}

c = DatastoresClient()
if os.path.exists(JOB):
    job = json.load(open(JOB))["job"]
    print("re-attached to", job, flush=True)
else:
    job = c.submit("reanalysis-era5-complete", BODY)
    json.dump({"job": job, "body": BODY}, open(JOB, "w"))
    print("submitted", job, flush=True)
while True:
    st, msg = c.poll(job)
    if st in ("done", "failed"):
        break
    time.sleep(60)
print(st, msg, flush=True)
if st == "done":
    c.download(job, "livetest/structtest/test.grb")
    c.cleanup(job)
    print("downloaded", flush=True)

if st == "done":
    from collections import Counter
    import eccodes as ec
    from dcfe import gribio
    msgs = gribio.read_all("livetest/structtest/test.grb")
    print("messages:", len(msgs), dict(Counter(gribio.get_int(m, "paramId") for m in msgs)), flush=True)
    for m in msgs:
        if gribio.get_int(m, "paramId") == 152:
            g = ec.codes_new_from_message(m)
            print("LNSP:", {k: ec.codes_get(g, k) for k in ("gridType", "level", "typeOfLevel", "numberOfValues")}, flush=True)
