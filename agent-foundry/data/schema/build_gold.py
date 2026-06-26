#!/usr/bin/env python3
"""Gold-set builder for the RESPONSE-schema validation task
(api-tester / validate-json-schema-responses).

NOT one of the four agents — the deterministic *reference*. For every documented
endpoint it sends ONE valid request, records the REAL HTTP status + response body,
looks up the response schema documented for that (path, method, status) in the
spec, and (if a schema exists) runs the SAME ajv v8 validator the agents' harness
uses. Per the task owner's Phase-2 decision the spec documents NO response schemas,
so the honest ground truth is: 0 schemas to validate; the finding is the coverage
gap. The ajv engine is wired and proven; it simply has nothing to run yet.

Reads the shared, untouched spec at ../openapi.json. Writes only under data/schema/:
  - gold/<slug>.json   per-endpoint gold record
  - gold.json          consolidated table + empirical summary

Usage:  BASE_URL=http://localhost:8899 python3 data/schema/build_gold.py
Stdlib only (plus a subprocess to the local ajv8 validator). Air-gapped.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent              # data/schema
DATA = HERE.parent                                  # data
WORKSPACE = DATA.parent                             # agent-foundry
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
GOLD_DIR = HERE / "gold"
SPEC_PATH = DATA / "openapi.json"                   # shared spec, left untouched
AJV = WORKSPACE / "tools" / "ajv" / "ajv_validate.mjs"
EXISTING_ID = 1

# Reuse the single endpoint catalogue (DRY) from the request-body gold builder.
sys.path.insert(0, str(DATA))
import build_gold as rb  # noqa: E402

ENDPOINTS = rb.ENDPOINTS


def classify(code: int) -> str:
    if 200 <= code < 300:
        return "2xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return f"other_{code}"


def send(method: str, path: str, body: dict):
    url = BASE_URL + path.replace("{id}", str(EXISTING_ID))
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), _parse(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read().decode("utf-8", "replace") if e.fp else "")
    except Exception as e:  # noqa: BLE001
        return -1, {"_transport_error": str(e)}


def _parse(raw: str):
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return raw[:500] if raw else None


def lookup_response_schema(spec: dict, path: str, method: str, status_code: int):
    """Find the documented JSON response schema for (path, method, status).
    Resolution: exact code -> range key (2xx/400/5xx) -> 'default'."""
    op = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
    responses = op.get("responses", {})
    range_key = {"2xx": "2xx", "4xx": "400", "5xx": "5xx"}.get(classify(status_code))
    for key in (str(status_code), range_key, "default"):
        if key and key in responses:
            schema = (responses[key].get("content", {})
                      .get("application/json", {}).get("schema"))
            return schema, key
    return None, None


def ajv_validate(schema, data):
    """Run the real ajv v8 validator (draft-07, strict, additionalProperties:false).
    Returns (valid, error_count, errors, fields_validated)."""
    payload = json.dumps({"schema": schema, "data": data, "draft": "draft-07"}).encode()
    proc = subprocess.run(["node", str(AJV)], input=payload, capture_output=True, timeout=30)
    out = json.loads(proc.stdout.decode() or "{}")
    return out.get("valid"), out.get("error_count", 0), out.get("errors", []), out.get("fields_validated", 0)


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    spec = json.loads(SPEC_PATH.read_text())
    consolidated = []
    responses_received = validated = conformant = without_schema = 0

    for ep in ENDPOINTS:
        code, body = send(ep["method"], ep["path"], ep["valid"])
        responses_received += 1 if code != -1 else 0
        schema, matched_key = lookup_response_schema(spec, ep["path"], ep["method"], code)

        if schema is None:
            without_schema += 1
            conformance, errors, err_count, fields = "n/a", [], 0, 0
            note = ("response status documented as description-only; no JSON Schema "
                    "present -> nothing to validate (spec TODO).")
        else:
            valid, err_count, errors, fields = ajv_validate(schema, body)
            validated += 1
            conformance = "pass" if err_count == 0 else "fail"
            conformant += 1 if err_count == 0 else 0
            note = "documented response schema present; validated by ajv v8."

        rec = {
            "slug": ep["slug"], "method": ep["method"], "path": ep["path"],
            "request_body": ep["valid"], "actual_code": code,
            "actual_class": classify(code), "matched_response_key": matched_key,
            "documented_schema": schema is not None,
            "fields_validated": fields, "validation_error_count": err_count,
            "validation_errors": errors, "conformance": conformance,
            "response_body": body, "note": note,
        }
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * conformant / validated, 2) if validated else None
    summary = {
        "target": BASE_URL, "task": "validate-json-schema-responses",
        "ajv": {"version": 8, "draft": "draft-07", "strict": True,
                "additionalProperties_false": True},
        "endpoints": len(ENDPOINTS), "responses_received": responses_received,
        "endpoints_without_documented_response_schema": without_schema,
        "responses_validated": validated, "responses_conformant": conformant,
        "schema_conformance_rate_pct": rate,
        "finding": (
            f"{without_schema}/{len(ENDPOINTS)} endpoints document a response status "
            "as description-only with NO JSON Schema. 0 responses could be validated "
            "-> Schema Conformance Rate is N/A (0 validated). ACTION: author response "
            "schemas in openapi.json (spec TODO), then re-run."),
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
