#!/usr/bin/env python3
"""Gold-set builder for the API enum-value-restriction testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the OpenAPI 3 spec the agents must parse (the task INPUT), generates the
canonical enum test matrix per endpoint (enum_spec), sends every payload to a
locally-running DummyJSON, and records the REAL observed status code (and, for any
400, whether the error message names the offending field) alongside the idealized
contract token.

The recorded behavior is the ground truth. Agents are later ranked on how
faithfully their own runs reproduce this table (Enum-Test Fidelity).

Outputs (under data/verify-enum-value-restrictions/):
  - openapi.json       the spec the agents parse (the task INPUT)
  - gold/<slug>.json   per-endpoint gold cases
  - gold.json          consolidated gold table + empirical summary (headline Enum
                       Validation Rate + Invalid-Value Rejection Rate + Valid-Value
                       Acceptance Rate)

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
COMMON = HERE.parent.parent / "agents" / "common"
EXISTING_ID = 1

sys.path.insert(0, str(COMMON))
import enum_spec  # noqa: E402


# ---------------------------------------------------------------------------
# Endpoint catalogue. Each entry declares an enum-constrained request-body schema
# over the REAL DummyJSON add routes (which accept any body and simulate a 2xx
# response air-gapped, so sending them mutates nothing). The enum values are
# UPPERCASE tokens so the case-sensitivity probe is exercised; `posts_add.visibility`
# is nullable:true so the null branch is covered on both sides.
# `valid` holds a known-good body; `path` may contain {id} (we substitute id 1).
# ---------------------------------------------------------------------------
def s():  # plain string field
    return {"type": "string"}


def en(values, nullable=False):  # enum-constrained string field
    f = {"type": "string", "enum": list(values)}
    if nullable:
        f["nullable"] = True
    return f


ENUM_ENDPOINTS = [
    {
        "slug": "products_add", "method": "POST", "path": "/products/add",
        "fields": {
            "title": s(),
            "price": {"type": "number"},
            "availabilityStatus": en(["IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"]),
        },
        "required": ["title", "availabilityStatus"],
        "valid": {"title": "Forge Widget", "price": 9.99, "availabilityStatus": "IN_STOCK"},
    },
    {
        "slug": "users_add", "method": "POST", "path": "/users/add",
        "fields": {
            "firstName": s(),
            "gender": en(["MALE", "FEMALE", "OTHER"]),
            "role": en(["ADMIN", "MODERATOR", "USER"]),
        },
        "required": ["firstName", "gender"],          # role optional
        "valid": {"firstName": "Forge", "gender": "MALE", "role": "USER"},
    },
    {
        "slug": "todos_add", "method": "POST", "path": "/todos/add",
        "fields": {
            "todo": s(),
            "completed": {"type": "boolean"},
            "userId": {"type": "integer"},
            "priority": en(["LOW", "MEDIUM", "HIGH"]),
        },
        "required": ["todo", "priority"],
        "valid": {"todo": "Ship the foundry", "completed": False, "userId": 1, "priority": "MEDIUM"},
    },
    {
        "slug": "posts_add", "method": "POST", "path": "/posts/add",
        "fields": {
            "title": s(),
            "userId": {"type": "integer"},
            "status": en(["DRAFT", "PUBLISHED", "ARCHIVED"]),
            "visibility": en(["PUBLIC", "PRIVATE"], nullable=True),
        },
        "required": ["title", "status"],              # visibility optional + nullable
        "valid": {"title": "A Forge Post", "userId": 1, "status": "PUBLISHED", "visibility": "PUBLIC"},
    },
]


def send(method, path, body):
    url = BASE_URL + path.replace("{id}", str(EXISTING_ID))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:  # noqa
            return e.code, ""
    except Exception:  # noqa
        return -1, ""


def classify(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "2xx"
    if code == 400:
        return "400"
    return f"other_{code}"


def build_openapi():
    paths = {}
    for ep in ENUM_ENDPOINTS:
        schema = {"type": "object", "properties": ep["fields"], "required": ep["required"],
                  "additionalProperties": False}
        op = {
            "operationId": ep["slug"],
            "requestBody": {"required": True, "content": {"application/json": {
                "schema": schema, "example": ep["valid"]}}},
            "responses": {"200": {"description": "ok"}, "400": {"description": "validation error"}},
        }
        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op
    spec = {"openapi": "3.0.3",
            "info": {"title": "DummyJSON enum-restriction surface (forge test spec)",
                     "version": "1.0.0"},
            "servers": [{"url": BASE_URL}],
            "paths": paths}
    (HERE / "openapi.json").write_text(json.dumps(spec, indent=2))
    return spec


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    build_openapi()  # author the agents' INPUT first (independent of target reachability)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    consolidated = []
    total = correct = 0
    invalid_total = invalid_400 = 0
    valid_total = valid_2xx = 0

    for ep in ENUM_ENDPOINTS:
        props, required, example = ep["fields"], ep["required"], ep["valid"]
        out = enum_spec.generate_cases(props, required, example)
        cases = []
        for category, label, field, value, body in enum_spec.iter_cases(out):
            code, body_text = send(ep["method"], ep["path"], body)
            actual = classify(code)
            ideal = enum_spec.ideal_token(category, field, props)
            mhf = _message_has_field(body_text, field) if actual == "400" else None
            ok = (actual == ideal) and not (ideal == "400" and actual == "400" and not mhf)
            cases.append({"category": category, "label": label, "field": field,
                          "value_sent": value, "ideal_token": ideal, "actual_code": code,
                          "actual_class": actual, "message_has_field": mhf,
                          "api_correct": ok, "payload": body})
            total += 1
            correct += 1 if ok else 0
            if category in enum_spec.INVALID_VALUE_CATEGORIES:
                invalid_total += 1
                if actual == "400":
                    invalid_400 += 1
            if category == "valid_values":
                valid_total += 1
                if actual == "2xx":
                    valid_2xx += 1
        rec = {"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
               "schema": {"fields": props, "required": required,
                          "enum_fields": enum_spec.enum_fields(props)},
               "cases": cases}
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    def pct(n, d):
        return round(100.0 * n / d, 2) if d else None

    summary = {
        "target": BASE_URL,
        "endpoints": len(ENUM_ENDPOINTS),
        "total_cases": total,
        "headline_enum_validation_rate_pct": pct(correct, total),
        "invalid_value_cases": invalid_total,
        "invalid_value_rejection_rate_pct": pct(invalid_400, invalid_total),
        "valid_value_cases": valid_total,
        "valid_value_acceptance_rate_pct": pct(valid_2xx, valid_total),
        "note": "Ground truth = live DummyJSON observed codes per labeled case. DummyJSON "
                "performs NO enum validation on add/update bodies (it echoes any value and "
                "returns 2xx), so the headline Enum Validation Rate and the Invalid-Value "
                "Rejection Rate are expected to be well below 100% by design — that gap is "
                "the genuine QA finding, not an agent fault. The agents are ranked instead "
                "on Enum-Test Fidelity (faithful reproduction of this observed table).",
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def _message_has_field(body_text, field):
    if not body_text or not field:
        return False
    msg = body_text
    try:
        doc = json.loads(body_text)
        if isinstance(doc, dict) and isinstance(doc.get("message"), str):
            msg = doc["message"]
    except Exception:  # noqa
        pass
    return field.lower() in msg.lower()


if __name__ == "__main__":
    raise SystemExit(main())
