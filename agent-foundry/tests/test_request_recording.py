#!/usr/bin/env python3
"""Unit tests for the request recorder + the request-derived case augmentation (no network):

  * request_recorder dedups per agent and excludes the EverOS telemetry endpoint,
  * request_cases.augment appends a request-derived 8-field case for every recorded call that isn't
    already an exact existing case (matched by method+path+query+body), per agent, and skips matches.

Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_request_recording.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import request_recorder as RR
import request_cases as RC
import core_postman as CP


def test_recorder_dedup_and_exclusion():
    RR._SEEN.clear()
    for _ in range(3):
        RR._record("GET", "http://localhost:8899/products?limit=2", None, 200)
    RR._record("GET", "http://localhost:8899/products/1", None, 200)
    RR._record("POST", "http://localhost:8899/auth/login", b'{"u":1}', 200)
    RR._record("GET", "http://127.0.0.1:8000/api/v1/memory/add", None, 200)         # everos: excluded
    RR._record("POST", "http://localhost:8787/v1/chat/completions", b'{}', 200)     # LLM shim: excluded
    RR._record("POST", "http://localhost:11434/api/chat", b'{}', 200)               # ollama: excluded
    assert len(RR._SEEN) == 3, f"expected 3 under-test calls, got {len(RR._SEEN)}: {[r['path'] for r in RR._SEEN.values()]}"
    flood = next(r for r in RR._SEEN.values() if r["path"] == "/products" and r["query"])
    assert flood["count"] == 3, "identical calls must dedup with a count"
    assert all("/memory/" not in r["path"] and "/v1/chat" not in r["path"] and "/api/chat" not in r["path"]
               for r in RR._SEEN.values()), "LLM-backend / telemetry calls must be excluded"
    RR._SEEN.clear()


def test_augment_appends_unmatched_and_skips_matches():
    core = set(CP.CT.AGENT_OF_AREA.values())
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        req = Path(td) / "runs" / "RID" / "requests"
        agent = out / "TestCases" / "test-webhook-delivery"
        agent.mkdir(parents=True)
        # one existing parseable case (GET /products) + one no-path case
        agent.joinpath("cases.json").write_text(json.dumps([
            {"test_case_id": "TC-WEBHOOK-001", "title_summary": "list", "preconditions": "x",
             "test_steps": ["1. Send GET /products to http://localhost:8899."], "test_data": {},
             "expected_result": "The API returns 200.", "actual_result": "x", "status": "Pass"},
            {"test_case_id": "TC-WEBHOOK-002", "title_summary": "generic", "preconditions": "x",
             "test_steps": ["1. Send GET  to http://localhost:8899."], "test_data": {},
             "expected_result": "The API returns 200.", "actual_result": "x", "status": "Pass"}]))
        req.mkdir(parents=True)
        req.joinpath("test-webhook-delivery.json").write_text(json.dumps({"agent": "x", "requests": [
            {"method": "GET", "path": "/products", "query": {}, "body": None, "status": 200},      # matches TC-001
            {"method": "POST", "path": "/webhooks", "query": {}, "body": {"u": "h"}, "status": 201},  # new
            {"method": "POST", "path": "/v1/chat/completions", "query": {}, "body": {}, "status": 200},  # LLM: skipped
            {"method": "GET", "path": "/products", "query": {"limit": "5"}, "body": None, "status": 200}]}))  # new (query)
        appended = RC.augment(out, req, core)
        assert appended == {"test-webhook-delivery": 2}, appended  # the exact /products match is skipped
        cases = json.loads((agent / "cases.json").read_text())
        ids = [c["test_case_id"] for c in cases]
        assert ids == ["TC-WEBHOOK-001", "TC-WEBHOOK-002", "TC-WEBHOOK-003", "TC-WEBHOOK-004"], ids
        titles = [c["title_summary"] for c in cases[2:]]
        assert any("POST /webhooks" in t for t in titles) and any("GET /products" in t for t in titles)
        # and build_full turns them into Postman requests named by the new ids
        col, _ = CP.build_full(out, [])
        folder = next(f for f in col["item"] if f["name"] == "test-webhook-delivery")
        names = {it["name"].split(" — ", 1)[0] for it in folder["item"]}
        assert {"TC-WEBHOOK-001", "TC-WEBHOOK-003", "TC-WEBHOOK-004"}.issubset(names), names


def main() -> int:
    tests = [test_recorder_dedup_and_exclusion, test_augment_appends_unmatched_and_skips_matches]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
