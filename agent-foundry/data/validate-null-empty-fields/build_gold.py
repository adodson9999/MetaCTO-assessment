#!/usr/bin/env python3
"""Gold-set builder for the API null-and-empty-fields testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it reuses the SAME endpoint catalogue + OpenAPI spec the request-payloads build
authored (data/build_gold.py ENDPOINTS -> data/openapi.json, the agents' INPUT),
generates the canonical null/empty test matrix per endpoint (null_spec), sends
every payload to a locally-running DummyJSON, and records the REAL observed status
code alongside the idealized contract token.

The recorded behavior is the ground truth. Agents are later ranked on how
faithfully their own runs reproduce this table (Null-Empty-Test Fidelity).

Outputs (under data/validate-null-empty-fields/):
  - gold/<slug>.json   per-endpoint gold cases
  - gold.json          consolidated gold table + empirical summary (headline accuracy +
                       Required Invalid-State Rejection Rate + Optional Nullable Compliance)

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
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
DATA_DIR = HERE.parent                       # agent-foundry/data
COMMON = HERE.parent.parent / "agents" / "common"

# Reuse the single source of truth for the endpoint catalogue (DRY): the same
# ENDPOINTS the request-payloads gold builder authored data/openapi.json from.
sys.path.insert(0, str(DATA_DIR))
sys.path.insert(0, str(COMMON))
import build_gold as payload_gold  # noqa: E402  (ENDPOINTS + send + classify shape)
import null_spec  # noqa: E402

ENDPOINTS = payload_gold.ENDPOINTS
EXISTING_ID = 1


def send(method: str, path: str, body) -> int:
    url = BASE_URL + path.replace("{id}", str(EXISTING_ID))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa
        return -1


def classify(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "2xx"
    if code == 400:
        return "400"
    return f"other_{code}"


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    consolidated = []
    total = correct = 0
    req_invalid = req_invalid_400 = 0
    opt_null = opt_null_match = 0

    for ep in ENDPOINTS:
        props, required, example = ep["fields"], ep["required"], ep["valid"]
        out = null_spec.generate_cases(props, required, example)
        cases = []
        for category, label, field, state, body in null_spec.iter_cases(out):
            code = send(ep["method"], ep["path"], body)
            actual = classify(code)
            ideal = null_spec.ideal_token(category, field, state, props)
            ok = actual == ideal
            cases.append({"category": category, "label": label, "field": field, "state": state,
                          "ideal_token": ideal, "actual_code": code, "actual_class": actual,
                          "api_correct": ok, "payload": body})
            total += 1
            correct += 1 if ok else 0
            if category in null_spec.REQUIRED_INVALID_CATEGORIES:
                req_invalid += 1
                if actual == "400":
                    req_invalid_400 += 1
            if category == "optional_state" and state == "json_null":
                opt_null += 1
                if ok:
                    opt_null_match += 1
        rec = {"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
               "schema": {"fields": props, "required": required,
                          "optional": null_spec.optional_fields(props, required)},
               "cases": cases}
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    def pct(n, d):
        return round(100.0 * n / d, 2) if d else None

    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "total_cases": total,
        "headline_null_empty_validation_accuracy_pct": pct(correct, total),
        "required_invalid_cases": req_invalid,
        "required_invalid_state_rejection_rate_pct": pct(req_invalid_400, req_invalid),
        "optional_null_cases": opt_null,
        "optional_field_nullable_compliance_rate_pct": pct(opt_null_match, opt_null),
        "note": "Ground truth = live DummyJSON observed codes per labeled case. DummyJSON "
                "performs no null/empty request-body validation, so the headline accuracy and "
                "the required-field rejection rate are expected to be well below 100% by design "
                "— that gap is the genuine QA finding, not an agent fault.",
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
