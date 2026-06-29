#!/usr/bin/env python3
"""Gold-set builder for the "Test Authentication Flows" task.

This is NOT one of the four agents. It is the deterministic *reference*: it
authors the OpenAPI 3 security section the agents must parse, constructs each
auth credential deterministically, sends it to the live DummyJSON protected
endpoint, and records the REAL observed status code + response message.

Per the Phase 2 decisions:
  - FAITHFUL to DummyJSON: the only documented scheme is Bearer JWT. The other
    schemes / the api-key-location sub-test / a dedicated revoke endpoint are
    enumerated as not_applicable ("needs_to_be_built_and_tested"), never faked.
  - Gold `actual_class` is the live API's ACTUAL behavior (the ground truth that
    agents are ranked against). The separate task-rule expected (200 valid / 401
    invalid) is what the Auth Flow Pass Rate / False Acceptance findings use.

Outputs (under data/):
  - auth_openapi.json    the security-section spec the agents parse (task INPUT)
  - auth_gold.json       the executed gold matrix + empirical summary

Usage:
  BASE_URL=http://localhost:8899 JWT_SECRET=forge_test_secret python3 build_gold_auth.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
SECRET = os.environ.get("JWT_SECRET", "forge_test_secret")
HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE.parent / "agents" / "common"))
import auth_spec  # noqa: E402


def build_openapi() -> dict:
    """The faithful security section: exactly what DummyJSON implements."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "DummyJSON (authored for the auth-flow testing task)",
            "version": "1.0.0",
            "description": "Authored from DummyJSON's real auth middleware/routes. "
                           "The agents parse THIS security section; ground truth is "
                           "the live API's observed behavior. Only bearerJWT is "
                           "implemented; other schemes are flagged not_applicable.",
        },
        "servers": [{"url": BASE_URL}],
        "components": {
            "securitySchemes": {
                "bearerJWT": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            },
        },
        "security": [{"bearerJWT": []}],
        "paths": {
            "/auth/login": {"post": {"operationId": "auth_login", "security": [],
                                     "summary": "obtain accessToken (username+password)"}},
            "/auth/me": {"get": {"operationId": "auth_me",
                                 "security": [{"bearerJWT": []}],
                                 "summary": "protected: current user"}},
            "/auth/logout": {"post": {"operationId": "auth_logout",
                                      "security": [{"bearerJWT": []}],
                                      "summary": "clear cookies (does NOT revoke a stateless JWT)"}},
        },
        "x-not-implemented": [x["item"] for x in auth_spec.NOT_APPLICABLE],
    }


def _message_of(text: str) -> str:
    try:
        return json.loads(text).get("message", "")
    except Exception:  # noqa
        return ""


def main() -> int:
    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    (HERE / "auth_openapi.json").write_text(json.dumps(build_openapi(), indent=2))

    ep = auth_spec.PROTECTED_ENDPOINT
    cases = []
    total = correct_code = 0
    false_accept = false_reject = 0

    for sname, label, recipe, task_expected in auth_spec.SUBTESTS_ITER():
        headers, note = auth_spec.build_credential(recipe, BASE_URL, SECRET)
        code, text = auth_spec_request(ep, headers)
        actual_class = auth_spec.classify(code)
        msg = _message_of(text)
        passed = (actual_class == task_expected)
        cases.append({
            "scheme": sname, "label": label, "recipe": recipe,
            "construction_note": note,
            "task_expected_class": task_expected,
            "actual_code": code, "actual_class": actual_class,
            "message": msg, "task_rule_pass": passed,
        })
        total += 1
        if passed:
            correct_code += 1
        else:
            if label == "valid" and actual_class != "2xx":
                false_reject += 1
            if label != "valid" and actual_class == "2xx":
                false_accept += 1

    pass_rate = round(100.0 * correct_code / total, 2) if total else 0.0
    summary = {
        "target": BASE_URL,
        "documented_schemes": [auth_spec.SCHEME["name"]],
        "protected_endpoint": ep,
        "executed_cases": total,
        "task_rule_correct_code": correct_code,
        "auth_flow_pass_rate_pct": pass_rate,
        "false_acceptance_count": false_accept,
        "false_rejection_count": false_reject,
        "not_applicable": auth_spec.NOT_APPLICABLE,
        "note": "Gold actual_class = live DummyJSON behavior. Bearer JWT is stateless "
                "with no server-side revocation and the error map omits 'invalid "
                "signature', so the empirical pass rate is below 100% BY DESIGN: "
                "revoked reuses a still-valid token (200 => critical False Acceptance) "
                "and a truncated token trips an unmapped 500 instead of 401.",
    }
    (HERE / "auth_gold.json").write_text(
        json.dumps({"summary": summary, "cases": cases}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def auth_spec_request(ep: dict, headers):
    # thin wrapper so the host guard + classification live in auth_spec
    auth_spec._assert_local(BASE_URL)
    return auth_spec._request(BASE_URL, ep["method"], ep["path"], headers=headers)


if __name__ == "__main__":
    raise SystemExit(main())
