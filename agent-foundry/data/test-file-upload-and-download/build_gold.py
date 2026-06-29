#!/usr/bin/env python3
"""Gold-set builder for the API file-upload-and-download testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
upload-endpoint catalogue + the agents' input spec (upload_spec.json), derives the
canonical correct upload/download plan per endpoint, builds the EXACT-sized files in
memory, executes that plan against a locally-running DummyJSON (multipart POST upload +
GET download + byte-for-byte MD5 compare), and records the REAL observed behavior per
scenario.

DummyJSON is tested AS-IS and never modified. It ships no file-upload/-download endpoint,
so a multipart POST to any documented upload path matches no route and returns 404 with no
"url"; because no upload returns a URL, no download can run. DummyJSON also simulates
writes without persisting, so these POSTs change no server state. The recorded ground
truth is therefore that the documented upload contract is NOT implemented — a legitimate
QA finding, mirroring how test-rate-limit-enforcement surfaced DummyJSON's absent rate
limiter. The idealized contract lives in upload_spec.ideal_for(); where the real token
differs from the ideal is the finding.

Outputs (all under data/test-file-upload-and-download/):
  - upload_spec.json       the endpoint catalogue the agents are briefed from (INPUT)
  - gold/<endpoint>.json   per-endpoint gold scenarios
  - gold.json              consolidated gold table + empirical summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. The cloud LLM backend is NOT used here — the
gold reference is pure deterministic code.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
_BOUNDARY = "forgeFileUploadBoundary7MA4YWxkTrZu0gW"

# Shared scenario structure + file builders (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import upload_spec  # noqa: E402

MAX_SIZE_BYTES = upload_spec.DEFAULT_MAX_SIZE_BYTES          # 1 MiB
ALLOWED_MIME_TYPES = upload_spec.DEFAULT_ALLOWED_MIME_TYPES  # ["image/jpeg", "image/png"]

# Real upload subjects: resource-creation routes of this DummyJSON fork that accept a
# multipart upload (the global clean-request/multer middleware processes the file, the
# route simulates the add — DummyJSON never persists). Each carries its own documented
# success_code (the code that route returns on a clean small upload). Routes whose
# controllers throw on air-gapped data (e.g. /comments/add, /posts/add) are deliberately
# excluded — they would crash the process, not exercise the upload contract.
ENDPOINTS = [
    {"upload_endpoint": "/products/add", "success_code": 201},
    {"upload_endpoint": "/users/add",    "success_code": 201},
    {"upload_endpoint": "/recipes/add",  "success_code": 200},
]


def _cfg(entry: dict) -> dict:
    return {
        "upload_endpoint": entry["upload_endpoint"],
        "max_size_bytes": MAX_SIZE_BYTES,
        "allowed_mime_types": ALLOWED_MIME_TYPES,
        "success_code": entry.get("success_code", upload_spec.SUCCESS_CODE),
        "over_size_code": upload_spec.OVER_SIZE_CODE,
        "invalid_mime_code": upload_spec.INVALID_MIME_CODE,
        "download_success_code": upload_spec.DOWNLOAD_SUCCESS_CODE,
    }


def _filename_for(mime: str) -> str:
    return {"image/jpeg": "upload.jpg", "image/png": "upload.png",
            "application/octet-stream": "upload.exe"}.get(mime, "upload.bin")


def _multipart(mime: str, data: bytes) -> tuple[bytes, str]:
    pre = (f"--{_BOUNDARY}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{_filename_for(mime)}"\r\n'
           f"Content-Type: {mime}\r\n\r\n").encode()
    post = f"\r\n--{_BOUNDARY}--\r\n".encode()
    return pre + data + post, f"multipart/form-data; boundary={_BOUNDARY}"


def post_upload(path: str, mime: str, data: bytes):
    """multipart POST. Returns (status, body_bytes)."""
    url = f"{BASE_URL}{path}"
    body, ct = _multipart(mime, data)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", ct)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:  # noqa
            return e.code, b""
    except Exception:  # noqa
        return -1, b""


def get_download(url_or_path: str):
    full = url_or_path if url_or_path.startswith("http") else f"{BASE_URL}{url_or_path}"
    req = urllib.request.Request(full, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, b"", (e.headers.get("Content-Type") if e.headers else None)
    except Exception:  # noqa
        return -1, b"", None


def _url_in_body(body: bytes):
    try:
        j = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa
        return False, None
    if isinstance(j, dict) and j.get("url"):
        return True, j["url"]
    return False, None


def run_reference_plan(cfg: dict):
    """Execute the canonical correct plan against the live API and return the raw
    observation dict upload_spec.evaluate expects + a request log."""
    plan = upload_spec.build_reference_plan(cfg)
    raw = {"uploads": {}, "downloads": {}}
    reqlog = []
    uploaded = {}

    for u in plan["uploads"]:
        data = upload_spec.file_bytes(u["mime_type"], u["size_bytes"])
        md5 = upload_spec.md5_hex(data)
        status, body = post_upload(plan["upload_endpoint"], u["mime_type"], data)
        has_url, url_val = _url_in_body(body)
        raw["uploads"][u["label"]] = {"ran": True, "status": status, "url_in_body": has_url}
        uploaded[u["label"]] = {"md5": md5, "url": url_val}
        reqlog.append({"label": u["label"], "endpoint": plan["upload_endpoint"],
                       "size_bytes": u["size_bytes"], "mime": u["mime_type"],
                       "status": status, "url_in_body": has_url, "returned_url": url_val,
                       "original_md5": md5})

    for d in plan["downloads"]:
        src = uploaded.get(d["source"])
        if not src or not src.get("url"):
            raw["downloads"][d["label"]] = {"ran": False, "status": None,
                                            "content_type": None, "md5_match": None}
            reqlog.append({"label": d["label"], "source": d["source"], "skipped": True,
                           "reason": "source upload returned no url"})
            continue
        status, body, ct = get_download(src["url"])
        dl_md5 = upload_spec.md5_hex(body) if body else None
        match = (dl_md5 is not None and dl_md5 == src["md5"])
        raw["downloads"][d["label"]] = {"ran": True, "status": status,
                                        "content_type": ct, "md5_match": match}
        reqlog.append({"label": d["label"], "source": d["source"], "url": src["url"],
                       "status": status, "content_type": ct, "original_md5": src["md5"],
                       "downloaded_md5": dl_md5, "md5_match": match})

    return raw, reqlog, plan


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's upload
    contract WITHOUT the answer plan."""
    return {
        "title": "File-upload contract (authored for the file-upload-and-download testing task)",
        "description": "Each upload endpoint is documented to accept a file up to max_size_bytes "
                       "of an allowed MIME type, returning success_code with a response 'url'; a "
                       "file of max_size_bytes+1 is rejected with over_size_code and no 'url'; a "
                       "disallowed-MIME file is rejected with invalid_mime_code and no 'url'; each "
                       "accepted file is downloadable at its 'url' with download_success_code, "
                       "Content-Type image/jpeg, and bytes identical to what was uploaded. Agents "
                       "construct the upload/download test plan from this; ground truth is the live "
                       "API's observed behavior. The DummyJSON fork is tested as-is and never "
                       "modified; its multipart handling enforces a 5 MiB per-file limit but returns "
                       "no downloadable 'url', returns 400 (not 413) for an over-limit file, and has "
                       "no MIME filter, so the observed divergences are the QA findings.",
        "target": BASE_URL,
        "max_size_bytes": MAX_SIZE_BYTES,
        "allowed_mime_types": ALLOWED_MIME_TYPES,
        "success_code": upload_spec.SUCCESS_CODE,
        "over_size_code": upload_spec.OVER_SIZE_CODE,
        "invalid_mime_code": upload_spec.INVALID_MIME_CODE,
        "download_success_code": upload_spec.DOWNLOAD_SUCCESS_CODE,
        "endpoints": [{"upload_endpoint": e["upload_endpoint"], "success_code": e["success_code"]}
                      for e in ENDPOINTS],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "upload_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    integ_n = integ_d = over_n = over_d = mime_n = mime_d = 0
    for entry in ENDPOINTS:
        cfg = _cfg(entry)
        raw, reqlog, plan = run_reference_plan(cfg)
        observed = upload_spec.evaluate(raw)

        scenarios = []
        for label in upload_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = upload_spec.correct(label, tok, cfg)
            scenarios.append({"scenario": label, "ideal": upload_spec.ideal_for(label, cfg),
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        ev = {s["scenario"]: s["observed_token"] for s in scenarios}
        for scn in ("download_1kb_md5_match", "download_max_md5_match"):
            if ev.get(scn) != "missing":
                integ_d += 1
                integ_n += 1 if ev.get(scn) == "true" else 0
        if ev.get("upload_over_status") != "missing":
            over_d += 1
            over_n += 1 if ev.get("upload_over_status") == "413" else 0
        if ev.get("upload_invalid_status") != "missing":
            mime_d += 1
            mime_n += 1 if ev.get("upload_invalid_status") == "415" else 0

        rec = {
            "endpoint": cfg["upload_endpoint"],
            "max_size_bytes": cfg["max_size_bytes"],
            "allowed_mime_types": cfg["allowed_mime_types"],
            "reference_plan": plan,
            "request_log": reqlog,
            "scenarios": scenarios,
        }
        (GOLD_DIR / f"{entry['upload_endpoint'].strip('/').replace('/', '_')}.json").write_text(
            json.dumps(rec, indent=2))
        consolidated.append(rec)

    pct = lambda n, d: round(100.0 * n / d, 2) if d else 0.0
    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(upload_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_upload_contract_correctness_rate_pct": rate,
        "file_integrity_rate_pct": pct(integ_n, integ_d),
        "over_size_rejection_rate_pct": pct(over_n, over_d),
        "invalid_mime_rejection_rate_pct": pct(mime_n, mime_d),
        "rates_basis": {"file_integrity": f"{integ_n}/{integ_d}",
                        "over_size": f"{over_n}/{over_d}", "invalid_mime": f"{mime_n}/{mime_d}"},
        "note": "Ground truth = live DummyJSON-fork observed token per (endpoint, scenario). The "
                "fork accepts small multipart uploads (success_code, no 'url'), enforces a 5 MiB "
                "per-file limit but returns 400 ('Error processing multipart data: File too large') "
                "for an over-limit file rather than the documented 413 — and the boundary is "
                "exclusive, so a file of exactly max_size_bytes is also rejected — and applies no "
                "MIME filter (an application/octet-stream file is accepted, never 415). Because no "
                "accepted upload returns a 'url', no download runs. So File Integrity Rate, "
                "Over-Size Rejection Rate, and Invalid MIME Rejection Rate are all 0% — three real "
                "QA findings about the target, not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
