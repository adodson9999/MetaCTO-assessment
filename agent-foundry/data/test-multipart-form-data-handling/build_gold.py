#!/usr/bin/env python3
"""Gold-set builder for the API multipart/form-data handling testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
multipart contract (multipart_openapi.json) + the agents' input catalogue
(multipart_spec.json), derives the canonical correct plan per endpoint, executes that
plan against a locally-running DummyJSON using the SAME harness code the agents use, and
records the REAL observed token per scenario.

DummyJSON's repo and data are NEVER modified. We only:
  - author a SEPARATE multipart_openapi.json describing the multipart upload contract a
    proper API would publish (so the agents have a documented contract to test against), and
  - probe the live API with the SAME non-persistent POST /add routes the request-payload
    and content-type builds already exercise (DummyJSON simulates writes; it persists
    nothing and deletes any parsed multipart file).

Endpoint catalogue (the two DummyJSON create routes whose controllers echo two real text
fields and return 201, so multipart text-field preservation is genuinely observable):
  - POST /products/add  echoes  title + category      (readback GET /products/{id})
  - POST /users/add     echoes  firstName + lastName   (readback GET /users/{id})

The recorded per-(endpoint, scenario) observed token is the ground truth. Agents are
later ranked on how faithfully their own runs reproduce this table. The idealized
contract lives in multipart_spec.IDEAL; where the real token differs from the ideal is a
genuine QA finding about DummyJSON (it parses multipart and preserves text fields, but
does not store the file, expose a document_url, persist the resource, validate required
fields, return 413 for a single over-limit file, or return 415 for a wrong Content-Type).

Outputs (all under data/test-multipart-form-data-handling/):
  - multipart_openapi.json   the multipart contract the agents are briefed from (INPUT)
  - multipart_spec.json      the endpoint catalogue (INPUT)
  - gold/<slug>.json         per-endpoint gold scenarios
  - gold.json                consolidated gold table + empirical Multipart Handling Accuracy

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
"""
import json
import os
import sys
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure + harness (one source of truth with the agents).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import multipart_spec  # noqa: E402

# Point the harness's execution helpers at this BASE_URL and run-id.
os.environ.setdefault("FORGE_TARGET_BASE_URL", BASE_URL)
os.environ.setdefault("FORGE_RUN_ID", "gold-build")
import multipart as mp  # noqa: E402  (uses FORGE_TARGET_BASE_URL set above)

# The 50 KB PNG, the 5 MiB documented per-file maximum, and the two endpoints.
FILE_SIZE_BYTES = 50 * 1024          # 51200 — the "50KB PNG" the task specifies
MAX_ALLOWED_FILE_BYTES = 5 * 1024 * 1024   # 5 MiB — DummyJSON's documented per-file cap
ENDPOINTS = [
    {
        "slug": "products_add",
        "endpoint": "/products/add",
        "method": "POST",
        "expected_create_status": 201,
        "text_field_a": {"name": "title", "value": "Test Entity"},
        "text_field_b": {"name": "category", "value": "A"},
        "file_field": "document",
        "file_media_type": "image/png",
        "file_size_bytes": FILE_SIZE_BYTES,
        "max_allowed_file_bytes": MAX_ALLOWED_FILE_BYTES,
        "readback_path": "/products/{id}",
    },
    {
        "slug": "users_add",
        "endpoint": "/users/add",
        "method": "POST",
        "expected_create_status": 201,
        "text_field_a": {"name": "firstName", "value": "Test Entity"},
        "text_field_b": {"name": "lastName", "value": "A"},
        "file_field": "document",
        "file_media_type": "image/png",
        "file_size_bytes": FILE_SIZE_BYTES,
        "max_allowed_file_bytes": MAX_ALLOWED_FILE_BYTES,
        "readback_path": "/users/{id}",
    },
]


def build_openapi() -> dict:
    paths = {}
    for ep in ENDPOINTS:
        a, b = ep["text_field_a"], ep["text_field_b"]
        paths[ep["endpoint"]] = {
            ep["method"].lower(): {
                "summary": f"{ep['method']} {ep['endpoint']} (multipart upload)",
                "consumes": ["multipart/form-data"],
                "requestBody": {
                    "required": True,
                    "content": {"multipart/form-data": {"schema": {
                        "type": "object",
                        "required": [a["name"], b["name"], ep["file_field"]],
                        "properties": {
                            a["name"]: {"type": "string"},
                            b["name"]: {"type": "string"},
                            ep["file_field"]: {"type": "string", "format": "binary",
                                               "x-max-bytes": ep["max_allowed_file_bytes"]},
                        },
                    }}},
                },
                "responses": {
                    "201": {"description": "created; body echoes the text fields and a document_url"},
                    "400": {"description": "a required text part is missing"},
                    "413": {"description": "the file exceeds x-max-bytes"},
                    "415": {"description": "the request Content-Type is not multipart/form-data"},
                },
            }
        }
        paths[ep["readback_path"]] = {"get": {
            "summary": f"read back {ep['readback_path']}",
            "responses": {"200": {"description": "the persisted resource incl. the text fields and document_url"}},
        }}
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "DummyJSON multipart/form-data upload contract (authored for the "
                     "multipart-form-data-handling task; DummyJSON itself is unmodified)",
            "version": "1.0.0",
            "description": "Describes the multipart upload contract a properly implemented "
                           "API would publish for these create routes. The live DummyJSON "
                           "parses multipart and preserves recognized text fields, but does "
                           "not store the file, expose a document_url, persist the resource, "
                           "validate required fields, return 413 for a single over-limit "
                           "file, or return 415 for a wrong Content-Type; the gold records "
                           "that real behavior and each gap is a QA finding.",
        },
        "x-file-size-bytes": FILE_SIZE_BYTES,
        "paths": paths,
    }


def build_catalogue() -> dict:
    return {
        "title": "Multipart/form-data upload endpoint catalogue (authored for the task)",
        "description": "Agents are briefed one upload endpoint at a time. DummyJSON is "
                       "never modified — the POST /add routes are non-persistent simulated "
                       "writes and any parsed file is deleted by the server.",
        "target": BASE_URL,
        "file_size_bytes": FILE_SIZE_BYTES,
        "max_allowed_file_bytes": MAX_ALLOWED_FILE_BYTES,
        "endpoints": ENDPOINTS,
    }


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (HERE / "multipart_openapi.json").write_text(json.dumps(build_openapi(), indent=2))
    (HERE / "multipart_spec.json").write_text(json.dumps(build_catalogue(), indent=2))

    all_cases = []
    total = correct = 0
    for cfg in ENDPOINTS:
        # Execute the CANONICAL correct plan through the shared harness against the live API.
        plan = multipart_spec.build_reference_plan(cfg)
        raw, reqlog = mp._exec_plan(cfg, plan)
        observed = multipart_spec.evaluate(raw)

        scenarios = []
        for label in multipart_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = multipart_spec.correct(label, tok, cfg)
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": multipart_spec.ideal_for(label, cfg),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        case = {"slug": cfg["slug"], "endpoint": cfg["endpoint"], "method": cfg["method"],
                "request_log": reqlog, "scenarios": scenarios}
        all_cases.append(case)
        (GOLD_DIR / f"{cfg['slug']}.json").write_text(json.dumps(case, indent=2))

    rate = round(100.0 * correct / total, 2) if total else 0.0
    gold = {
        "task": "api-tester / test-multipart-form-data-handling",
        "target": BASE_URL,
        "multipart_handling_accuracy_pct": rate,
        "scenarios_total": total,
        "scenarios_api_correct": correct,
        "endpoints": all_cases,
    }
    (HERE / "gold.json").write_text(json.dumps(gold, indent=2))

    print(f"endpoints: {len(ENDPOINTS)}  scenarios: {total}  api_correct: {correct}")
    print(f"Multipart Handling Accuracy = {rate}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
