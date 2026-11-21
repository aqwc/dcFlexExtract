# dcFlexExtract - resumable ERA5 download and post-processing for FLEXPART input
# Copyright (C) 2026 the dcFlexExtract contributors
# SPDX-License-Identifier: CC-BY-4.0
#
# Builds on flex_extract, (C) 2014-2020 Anne Philipp, Leopold Haimberger and Petra Seibert
# (CC BY 4.0; https://www.flexpart.eu/wiki/FpInputMetEcmwf). See NOTICE.md.

"""CDS access behind a tiny interface: submit -> poll -> download, so that a request can be
submitted by one process and fetched by another (CDS keeps the queued request server-side).

Two implementations:
  * DatastoresClient - ecmwf-datastores-client (what `cdsapi` >= 0.7 uses internally for the new
    CDS); supports detached submit / reattach by request id. Credentials are read from ~/.cdsapirc.
  * FakeClient (in tests) for unit tests.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

# poll results
QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
# failure kinds
TOO_LARGE, TRANSIENT, FATAL, BUSY = "too_large", "transient", "fatal", "busy"


def classify_error(message: str) -> str:
    m = message.lower()
    # per-user limit on queued/running requests, or rate limiting: not a failure, just wait
    if any(k in m for k in ("too many", "429", "queued requests", "limit of", "maximum number of", "rate limit")) \
            and "cost limits" not in m:
        return BUSY
    if "cost limits exceeded" in m or "too large" in m or "reduce your selection" in m:
        return TOO_LARGE
    if any(k in m for k in ("401", "403", "licence", "license", "invalid", "bad request", "400",
                            "authentication", "not found", "404")):
        return FATAL
    return TRANSIENT


class Client(Protocol):
    def submit(self, dataset: str, body: dict) -> str: ...
    def poll(self, job_id: str) -> tuple[str, str]: ...      # (state, message)
    def download(self, job_id: str, target: str) -> None: ...
    def cleanup(self, job_id: str) -> None: ...              # delete the finished job + its result at CDS


class SubmitError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.kind = classify_error(message)


def read_cdsapirc(path: str | None = None) -> tuple[str, str]:
    """url and key from ~/.cdsapirc. Only lines of the form `url: ...` / `key: ...` are used, so
    stray text in the file does not matter. The key is never printed or logged."""
    path = path or os.environ.get("CDSAPI_RC") or str(Path.home() / ".cdsapirc")
    url = key = None
    for line in Path(path).read_text().splitlines():
        m = re.match(r"\s*(url|key)\s*:\s*(\S+)\s*$", line)
        if m:
            if m.group(1) == "url":
                url = m.group(2)
            else:
                key = m.group(2)
    if not url or not key:
        raise RuntimeError(f"no url/key found in {path}")
    return url, key


class DatastoresClient:
    def __init__(self, rcfile: str | None = None):
        from ecmwf.datastores import Client as _C
        url, key = read_cdsapirc(rcfile)
        self._c = _C(url=url, key=key, progress=False, maximum_tries=5)

    def submit(self, dataset: str, body: dict) -> str:
        try:
            return self._c.submit(dataset, body).request_id
        except Exception as e:                       # noqa: BLE001 - classified by message
            raise SubmitError(str(e)) from e

    def poll(self, job_id: str) -> tuple[str, str]:
        r = self._c.get_remote(job_id)
        st = r.status
        if st == "successful":
            return DONE, ""
        if st == "failed":
            try:
                msg = str(r.json.get("metadata", {}).get("results", {}).get("message", "")
                          or r.json.get("message", "") or "job failed")
            except Exception:                        # noqa: BLE001
                msg = "job failed"
            return FAILED, msg
        if st in ("rejected", "dismissed"):
            return FAILED, f"job {st}"
        return (RUNNING if st == "running" else QUEUED), ""

    def download(self, job_id: str, target: str) -> None:
        self._c.get_remote(job_id).download(target)

    def cleanup(self, job_id: str) -> None:
        """Delete a finished job (and its stored result) from the CDS account."""
        self._c.delete(job_id)

    def list_successful(self) -> list[str]:
        """Ids of all successful jobs still stored for this account (for the manual cleanup command)."""
        jobs = self._c.get_jobs(status="successful", limit=100)
        ids = list(jobs.request_ids)
        while getattr(jobs, "next", None) is not None:
            jobs = jobs.next
            ids += list(jobs.request_ids)
        return ids
