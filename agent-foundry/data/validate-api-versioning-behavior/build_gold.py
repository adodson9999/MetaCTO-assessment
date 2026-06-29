#!/usr/bin/env python3
"""Gold-set builder for the API versioning-behavior testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the documented versioning contract + the agents' input spec (versioning_spec.json),
derives the canonical correct 5-case versioning test plan per endpoint, sends every
case to a locally-running DummyJSON with READ-ONLY GET calls, validates each 200 body
against the documented per-version schema with the real ajv v8 validator, and records
the REAL observed behavior (status class, Deprecation header presence/value/ISO/future,
schema conformance, schema-diff field presence) per scenario.

DummyJSON is tested AS-IS and never modified. All HTTP is GET only — no
POST/PUT/PATCH/DELETE against the target.

The recorded per-(endpoint, scenario) observed token is the ground truth. Agents are
later ranked on how faithfully their own runs reproduce this table (coverage + correct
plan construction + schema/header observation). The idealized contract lives in
versioning_spec.IDEAL; where the real token differs from the ideal is a genuine QA
finding about DummyJSON. The headline finding: DummyJSON implements NO API versioning
(no /vN router, no Deprecation header — see src/routes/index.js), so every versioned
URL returns 404 with an HTML body. The documented current/deprecated versions
therefore wrongly 404 and never carry a Deprecation header, while the unsupported
versions "correctly" 404 only because everything does.

Outputs (all under data/validate-api-versioning-behavior/):
  - versioning_spec.json     the contract the agents are briefed from (INPUT)
  - gold/<endpoint>.json     per-endpoint gold scenarios
  - gold.json                consolidated gold table + empirical accuracy summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib + ajv subprocess only. No network beyond BASE_URL (read-only GET). Air-gapped.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
TODAY = os.environ.get("FORGE_TODAY") or datetime.now(timezone.utc).date().isoformat()
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
AJV = HERE.parents[1] / "tools" / "ajv" / "ajv_validate.mjs"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import versioning_spec  # noqa: E402

# The four DummyJSON list collections used across the api-tester builds. Each would,
# in a versioned API, expose /v1/<ep> and /v2/<ep>. DummyJSON exposes neither.
ENDPOINTS = [
    {"endpoint": "/products", "list_field": "products"},
    {"endpoint": "/posts",    "list_field": "posts"},
    {"endpoint": "/users",    "list_field": "users"},
    {"endpoint": "/recipes",  "list_field": "recipes"},
]


def _cfg(entry: dict) -> dict:
    return {
        "endpoint": entry["endpoint"],
        "list_field": entry["list_field"],
        "schema_diff_field": versioning_spec.SCHEMA_DIFF_FIELD,
    }


def get(path: str, _retries: int = 2):
    """Read-only GET. Returns (status, json_body_or_None, deprecation_header_or_None)."""
    url = f"{BASE_URL}{path}"
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                dep = r.headers.get("Deprecation")
                try:
                    return r.getcode(), json.loads(body), dep
                except Exception:  # noqa
                    return r.getcode(), None, dep
        except urllib.error.HTTPError as e:
            dep = e.headers.get("Deprecation") if e.headers else None
            try:
                parsed = json.loads(e.read()) if e.fp else None
            except Exception:  # noqa
                parsed = None
            return e.code, parsed, dep
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return None, None, None


def ajv_errors(schema, data) -> int:
    payload = json.dumps({"schema": schema, "data": data, "draft": "draft-07"}).encode()
    try:
        proc = subprocess.run(["node", str(AJV)], input=payload, capture_output=True, timeout=30)
        return json.loads(proc.stdout.decode() or "{}").get("error_count", 1)
    except Exception:  # noqa
        return 1


def run_plan(cfg: dict, plan: dict):
    """Execute a plan's cases against the live API (read-only). Returns
    (case_obs, reqlog) where case_obs feeds versioning_spec.evaluate."""
    case_obs, reqlog = {}, {}
    lf, sdf = cfg["list_field"], cfg["schema_diff_field"]

    for case in plan["cases"]:
        path = case["path"]
        status, body, dep = get(path)
        schema_documented, errs = False, None
        version = case.get("version")
        if status == 200 and isinstance(body, dict) and version in ("v1", "v2"):
            schema = versioning_spec.schema_for(version, lf, sdf)
            schema_documented = True
            errs = ajv_errors(schema, body)
        case_obs[case["label"]] = {"status": status, "body": body, "deprecation": dep,
                                   "schema_documented": schema_documented,
                                   "ajv_error_count": errs}
        reqlog[case["label"]] = {"path": path, "version": version,
                                 "version_status": case.get("version_status"),
                                 "status": status, "deprecation": dep,
                                 "ajv_error_count": errs}
    return case_obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's
    documented versioning contract WITHOUT the answer plan."""
    return {
        "title": "DummyJSON versioning contract (authored for the versioning-behavior task)",
        "description": "Each endpoint is documented as exposing a current version (v2) and a "
                       "deprecated version (v1), with v0/v99/vbeta unsupported. The v2 response "
                       "schema declares one field (schema_diff_field) the v1 schema omits. Agents "
                       "construct the versioning test plan from this; ground truth is the live "
                       "API's observed behavior. DummyJSON is read-only and never modified, and in "
                       "fact implements no versioning — the genuine QA finding this task surfaces.",
        "target": BASE_URL,
        "schema_diff_field": versioning_spec.SCHEMA_DIFF_FIELD,
        "documented_deprecation_date": versioning_spec.DOCUMENTED_DEPRECATION_DATE,
        "supported_versions": versioning_spec.SUPPORTED_VERSIONS,
        "unsupported_versions": versioning_spec.UNSUPPORTED_VERSIONS,
        "per_version_response_schemas": {
            "note": "Authored per (version, endpoint) by versioning_spec.schema_for at run time; "
                    "v2 adds the schema_diff_field, v1 omits it.",
        },
        "endpoints": [
            {"endpoint": e["endpoint"], "list_field": e["list_field"],
             "schema_diff_field": versioning_spec.SCHEMA_DIFF_FIELD}
            for e in ENDPOINTS
        ],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "versioning_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    findings = []
    for entry in ENDPOINTS:
        cfg = _cfg(entry)
        plan = versioning_spec.build_reference_plan(cfg)
        case_obs, reqlog = run_plan(cfg, plan)
        observed = versioning_spec.evaluate(case_obs, cfg["schema_diff_field"], TODAY)

        scenarios = []
        for label in versioning_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = versioning_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": versioning_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0
            if not ok:
                findings.append({"endpoint": cfg["endpoint"], "scenario": label,
                                 "ideal": versioning_spec.IDEAL[label], "observed": tok})

        rec = {"endpoint": cfg["endpoint"], "list_field": cfg["list_field"],
               "schema_diff_field": cfg["schema_diff_field"],
               "reference_plan": plan, "request_log": reqlog, "scenarios": scenarios}
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "today": TODAY,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(versioning_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_version_routing_accuracy_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = live DummyJSON observed token per (endpoint, scenario). "
                "DummyJSON implements no API versioning: there is no /vN router and no Deprecation "
                "header, so every versioned URL returns 404 with an HTML body. The documented "
                "current (v2) and deprecated (v1) versions therefore wrongly 404 (ideal 200) and "
                "never carry a Deprecation header; schema and header scenarios score 'missing' for "
                "lack of any 200 body. Only the unsupported v0/v99/vbeta scenarios match the ideal "
                "(404), and only because every version 404s. That gap is a real QA finding, not an "
                "agent failure.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
