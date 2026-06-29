#!/usr/bin/env python3
"""Gold-set builder for the API response status-code task.

NOT one of the four agents. The deterministic *reference*: it authors the
OpenAPI 3 spec the agents must parse (documenting a realistic per-endpoint
status-code contract), applies the canonical recipe (agents/common/status_spec.py)
to derive the request for every documented (endpoint, code) case, sends each to a
locally-running DummyJSON, and records the REAL observed status code.

The recorded behavior is the ground truth. Agents are later ranked on how
faithfully their own runs reproduce this table (coverage + correct request
construction + correct actual code).

Outputs (all under data/status/):
  - openapi.json        the spec the agents parse (the task INPUT)
  - gold/<slug>.json    per-operation gold cases
  - gold.json           consolidated gold table + empirical summary

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

# Shared, pure recipe + descriptor scheme — identical to what the harness iterates.
sys.path.insert(0, str(HERE.parent.parent / "agents" / "common"))
import status_spec  # noqa: E402


def s(maxlen=None):
    return {"type": "string", **({"maxLength": maxlen} if maxlen else {})}


# Each operation declares its documented status-code contract (`codes`) plus the
# metadata the recipe needs (auth, required body fields, a valid example body).
ENDPOINTS = [
    {"slug": "auth_login", "method": "POST", "path": "/auth/login",
     "auth_required": False,
     "fields": {"username": s(40), "password": s(60), "expiresInMins": {"type": "integer"}},
     "required": ["username", "password"],
     "example": {"username": LOGIN_USER, "password": LOGIN_PASS},
     "codes": [200, 400]},

    {"slug": "auth_me", "method": "GET", "path": "/auth/me",
     "auth_required": True, "fields": {}, "required": [], "example": None,
     "codes": [200, 401, 500]},

    {"slug": "products_get", "method": "GET", "path": "/products/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "codes": [200, 404]},

    {"slug": "products_add", "method": "POST", "path": "/products/add",
     "auth_required": False,
     "fields": {"title": s(100), "price": {"type": "number"}, "stock": {"type": "integer"}},
     "required": ["title"],
     "example": {"title": "Forge Widget", "price": 9.99, "stock": 5},
     "codes": [201, 400]},

    {"slug": "posts_get", "method": "GET", "path": "/posts/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "codes": [200, 404]},

    {"slug": "posts_add", "method": "POST", "path": "/posts/add",
     "auth_required": False,
     "fields": {"title": s(150), "userId": {"type": "integer"}, "body": s(1000)},
     "required": ["title", "userId"],
     "example": {"title": "A Forge Post", "userId": 1, "body": "hello"},
     "codes": [201, 400]},

    {"slug": "todos_add", "method": "POST", "path": "/todos/add",
     "auth_required": False,
     "fields": {"todo": s(200), "completed": {"type": "boolean"}, "userId": {"type": "integer"}},
     "required": ["todo", "completed", "userId"],
     "example": {"todo": "Ship the foundry", "completed": False, "userId": 1},
     "codes": [201, 400]},

    {"slug": "users_get", "method": "GET", "path": "/users/{id}",
     "auth_required": False, "fields": {}, "required": [], "example": None,
     "codes": [200, 404]},

    {"slug": "comments_add", "method": "POST", "path": "/comments/add",
     "auth_required": False,
     "fields": {"body": s(300), "postId": {"type": "integer"}, "userId": {"type": "integer"}},
     "required": ["body", "postId", "userId"],
     "example": {"body": "Nice post", "postId": 1, "userId": 1},
     "codes": [201, 400]},

    {"slug": "carts_add", "method": "POST", "path": "/carts/add",
     "auth_required": False,
     "fields": {"userId": {"type": "integer"}, "products": {"type": "array"}},
     "required": ["userId", "products"],
     "example": {"userId": 1, "products": [{"id": 1, "quantity": 2}]},
     "codes": [201, 400]},

    # Documented status hooks for codes the resource layer does not natively enforce.
    {"slug": "http_403", "method": "GET", "path": "/http/403", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None, "codes": [403]},
    {"slug": "http_409", "method": "GET", "path": "/http/409", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None, "codes": [409]},
    {"slug": "http_422", "method": "GET", "path": "/http/422", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None, "codes": [422]},
    {"slug": "http_429", "method": "GET", "path": "/http/429", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None, "codes": [429]},
    {"slug": "http_500", "method": "GET", "path": "/http/500", "is_hook": True,
     "auth_required": False, "fields": {}, "required": [], "example": None, "codes": [500]},
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
        # 3-segment JWT-shaped but undecodable token → DummyJSON's parse-level 500.
        # (A 2- or 4-segment token yields 401 instead; this is the meaningful
        # "malformed token -> server error" trigger.)
        h["Authorization"] = "Bearer xx.yy.zz"
    return h


def send(desc: dict, token: str | None) -> int:
    url = BASE_URL + desc["path"]
    data = json.dumps(desc["body"]).encode() if desc.get("body") is not None else None
    req = urllib.request.Request(url, data=data, method=desc["method"],
                                 headers=headers_for(desc.get("auth", "none"), token))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa
        return -1


def build_openapi() -> dict:
    paths: dict = {}
    for ep in ENDPOINTS:
        op = {"operationId": ep["slug"],
              "responses": {str(c): {"description": f"documented {c}"} for c in ep["codes"]}}
        if ep.get("auth_required"):
            op["security"] = [{"bearerAuth": []}]
        if ep["method"] in status_spec.BODY_METHODS and ep.get("fields"):
            op["requestBody"] = {"required": True, "content": {"application/json": {
                "schema": {"type": "object", "properties": ep["fields"],
                           "required": ep["required"], "additionalProperties": False},
                "example": ep["example"]}}}
        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {"title": "DummyJSON (authored for the status-code task)", "version": "1.0.0",
                 "description": "Per-endpoint status-code contract authored from DummyJSON "
                                "routes/controllers. Agents parse THIS spec; ground truth is the "
                                "live API's observed code per documented (endpoint, code) case."},
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
    testable = correct = 0
    for ep in ENDPOINTS:
        cases = []
        for code in ep["codes"]:
            desc = status_spec.reference_request(ep, code)
            actual = send(desc, token)
            passed = (actual == code)
            cases.append({"documented_code": code, "request": desc,
                          "actual_code": actual, "passed": passed})
            testable += 1
            correct += int(passed)
        rec = {"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
               "auth_required": bool(ep.get("auth_required")), "is_hook": bool(ep.get("is_hook")),
               "documented_codes": ep["codes"], "cases": cases}
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    accuracy = round(100.0 * correct / testable, 2) if testable else None
    summary = {
        "target": BASE_URL,
        "operations": len(ENDPOINTS),
        "testable_cases": testable,
        "correct_exact_match": correct,
        "empirical_status_code_accuracy_rate_pct": accuracy,
        "note": "Ground truth = live DummyJSON observed code per documented (endpoint, code) "
                "case. Several /add endpoints document 400 but return 201 (no body validation), "
                "so the empirical accuracy rate is below 100% by design — a real QA finding.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
