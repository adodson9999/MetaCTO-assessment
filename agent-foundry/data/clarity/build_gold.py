#!/usr/bin/env python3
"""Gold-set builder for the Verify-Error-Message-Clarity task.

NOT one of the four agents. The deterministic *reference*: it authors the
OpenAPI 3 spec the agents must parse (documenting, per operation, which error
codes it returns and the named trigger for each), applies the canonical recipe
(agents/common/clarity_spec.py) to derive the request that triggers every
documented (operation, error-code) case, sends each to a locally-running
DummyJSON, records the REAL response body, and runs the deterministic clarity
assertions on it.

The recorded behavior is the ground truth. Agents are later ranked on how
faithfully their own runs reproduce this table (coverage + correct trigger
construction + same triggered status + same clarity verdict).

Outputs (all under data/clarity/):
  - openapi.json        the spec the agents parse (the task INPUT)
  - gold/<slug>.json    per-operation gold cases (request + real body + verdict)
  - gold.json           consolidated gold table + empirical clarity summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL and one login. Air-gapped.
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
LOGIN_USER = os.environ.get("FORGE_LOGIN_USER", "emilys")
LOGIN_PASS = os.environ.get("FORGE_LOGIN_PASS", "emilyspass")

# Shared, pure recipe + descriptor scheme + clarity assertions — identical to
# what the harness iterates.
sys.path.insert(0, str(HERE.parent.parent / "agents" / "common"))
import clarity_spec  # noqa: E402


def s(maxlen=None):
    return {"type": "string", **({"maxLength": maxlen} if maxlen else {})}


# Each operation declares its documented ERROR-code contract (`triggers`: code ->
# trigger name) plus the metadata the recipe needs (auth, required body fields, a
# valid example body, an optional bad-query suffix). Mapped onto DummyJSON's real
# error surface (verified live):
#   - real resource errors (400/401/404/500) where DummyJSON genuinely raises them
#   - the native /http/<n> error hooks for the server-class codes DummyJSON does
#     not raise on resources (403/409/422/429/500)
ENDPOINTS = [
    # --- real resource error bodies (what callers actually hit) ---
    {"slug": "auth_login", "method": "POST", "path": "/auth/login",
     "auth_required": False,
     "fields": {"username": s(40), "password": s(60)},
     "required": ["username", "password"],
     "example": {"username": LOGIN_USER, "password": LOGIN_PASS},
     "triggers": {400: "missing_field"}},

    {"slug": "auth_me", "method": "GET", "path": "/auth/me",
     "auth_required": True, "fields": {}, "required": [], "example": None,
     "triggers": {401: "no_auth", 500: "malformed_auth"}},

    {"slug": "products_get", "method": "GET", "path": "/products/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {404: "bad_path_id"}},

    {"slug": "users_get", "method": "GET", "path": "/users/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {400: "bad_path_id"}},

    {"slug": "posts_get", "method": "GET", "path": "/posts/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {400: "bad_path_id"}},

    {"slug": "comments_get", "method": "GET", "path": "/comments/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {404: "bad_path_id"}},

    {"slug": "todos_get", "method": "GET", "path": "/todos/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {404: "bad_path_id"}},

    {"slug": "carts_get", "method": "GET", "path": "/carts/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {404: "bad_path_id"}},

    {"slug": "products_list", "method": "GET", "path": "/products",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "bad_query": "?skip=abc",
     "triggers": {400: "bad_query"}},

    # --- native /http/<n> error hooks (the API's contract for server-class codes
    #     it does not raise on resources: 403 wrong-role, 409 duplicate-key,
    #     422 invalid-field, 429 rate-limit, 500 server-error) ---
    {"slug": "http_403", "method": "GET", "path": "/http/403", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {403: "passthrough"}},
    {"slug": "http_409", "method": "GET", "path": "/http/409", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {409: "passthrough"}},
    {"slug": "http_422", "method": "GET", "path": "/http/422", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {422: "passthrough"}},
    {"slug": "http_429", "method": "GET", "path": "/http/429", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {429: "passthrough"}},
    {"slug": "http_500", "method": "GET", "path": "/http/500", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "triggers": {500: "passthrough"}},
]


def login_token() -> str | None:
    body = json.dumps({"username": LOGIN_USER, "password": LOGIN_PASS}).encode()
    req = urllib.request.Request(BASE_URL + "/auth/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("accessToken") or data.get("token")
    except Exception:  # noqa
        return None


def headers_for(auth: str, token: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if auth == "valid" and token:
        h["Authorization"] = f"Bearer {token}"
    elif auth == "malformed":
        # 3-segment JWT-shaped but undecodable token -> DummyJSON parse-level 500
        # with a plain-English "invalid token" body (verified live).
        h["Authorization"] = "Bearer xx.yy.zz"
    return h


def send(desc: dict, token: str | None):
    """Return (status_code, raw_body_text)."""
    url = BASE_URL + desc["path"]
    data = json.dumps(desc["body"]).encode() if desc.get("body") is not None else None
    req = urllib.request.Request(url, data=data, method=desc["method"],
                                 headers=headers_for(desc.get("auth", "none"), token))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:  # noqa
            body = ""
        return e.code, body
    except Exception:  # noqa
        return -1, ""


def build_openapi() -> dict:
    paths: dict = {}
    for ep in ENDPOINTS:
        codes = sorted(int(c) for c in ep["triggers"])
        op = {"operationId": ep["slug"],
              "responses": {str(c): {"description": f"documented error {c}"} for c in codes},
              # surface the per-code trigger contract the agents must honor
              "x-error-triggers": {str(c): ep["triggers"][c] for c in codes}}
        if ep.get("auth_required"):
            op["security"] = [{"bearerAuth": []}]
        if ep.get("bad_query"):
            op["x-bad-query"] = ep["bad_query"]
        if ep["method"] in clarity_spec.BODY_METHODS and ep.get("fields"):
            op["requestBody"] = {"required": True, "content": {"application/json": {
                "schema": {"type": "object", "properties": ep["fields"],
                           "required": ep["required"], "additionalProperties": False},
                "example": ep["example"]}}}
        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {"title": "DummyJSON (authored for the error-message-clarity task)",
                 "version": "1.0.0",
                 "description": "Per-endpoint documented error contract authored from "
                                "DummyJSON routes/controllers. Each operation lists the "
                                "error codes it returns and the named trigger that provokes "
                                "each. Agents parse THIS spec; ground truth is the live API's "
                                "observed body + clarity verdict per documented (endpoint, "
                                "error-code) case."},
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "servers": [{"url": BASE_URL}],
        "paths": paths,
    }


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    (HERE / "openapi.json").write_text(json.dumps(build_openapi(), indent=2))
    token = login_token()

    consolidated = []
    total = passed = msg_yes = code_yes = leaks_found = 0
    p1_leaks = 0
    for ep in ENDPOINTS:
        cases = []
        for code in sorted(int(c) for c in ep["triggers"]):
            desc = clarity_spec.reference_request(ep, code)
            actual, body = send(desc, token)
            verdict = clarity_spec.clarity_verdict(body)
            cases.append({"documented_code": code,
                          "trigger": ep["triggers"][code],
                          "request": desc,
                          "actual_code": actual,
                          "body": body,
                          "verdict": verdict})
            total += 1
            passed += int(verdict["passed"])
            msg_yes += int(verdict["message_present"])
            code_yes += int(verdict["code_present"])
            if verdict["sensitive_found"]:
                leaks_found += 1
                p1_leaks += 1
        rec = {"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
               "auth_required": bool(ep.get("auth_required")), "is_hook": bool(ep.get("is_hook")),
               "documented_codes": sorted(int(c) for c in ep["triggers"]), "cases": cases}
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    pass_rate = round(100.0 * passed / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "operations": len(ENDPOINTS),
        "documented_error_cases": total,
        "passed_cases": passed,
        "error_clarity_pass_rate_pct": pass_rate,
        "message_field_present": msg_yes,
        "code_field_present": code_yes,
        "responses_with_internal_leaks": leaks_found,
        "p1_security_defects": p1_leaks,
        "note": "Ground truth = live DummyJSON error body + clarity verdict per documented "
                "(endpoint, error-code) case. A case PASSES only with a usable 'message' AND a "
                "usable 'code'/'error_code' AND zero internal-detail leaks. DummyJSON error "
                "bodies carry a clear 'message' and leak nothing, but expose NO machine-readable "
                "'code'/'error_code' field, so the strict pass rate is driven down by the "
                "missing-code-field contract gap — a real QA finding. P1 security defects "
                "(stack traces / file paths / exception classes in a body) = "
                + str(p1_leaks) + ".",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
