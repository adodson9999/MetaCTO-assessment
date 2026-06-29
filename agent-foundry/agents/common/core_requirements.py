# Used by: shared — deterministic Core-Requirements contract for the assessment (Authentication,
# CRUD-products, Search & Filtering, Error handling). Consumed by run_pipeline (TestCases + BugReport),
# core_postman (the Postman deliverable), and the api-tester agents' executors. Guaranteed coverage
# every run — no LLM dependency — so guardrails G14–G17 + unit tests can assert it.
"""Deterministic Core-Requirements scenario contract + executor.

Each scenario is a concrete, real request against the DummyJSON contract with explicit
assertions (status + response-shape). `run(target)` executes them in order against the live
target, carrying auth/CRUD context (captured accessToken / refreshToken / created id), records
the ACTUAL response, evaluates every assertion, and returns one executed-result per scenario.

The SAME scenario list drives:
  - the 8-field TestCases (core_testcases.py),
  - the folder-organised Postman collection (core_postman.py),
so coverage of the four Core Requirements is identical across the deliverable and guaranteed.

Faithful to DummyJSON (https://dummyjson.com/docs/auth + /docs):
  - POST /auth/login {username,password} -> 200 {accessToken, refreshToken, ...}; bad creds -> 400.
  - GET /auth/me  Authorization: Bearer <accessToken> -> 200; missing/invalid -> 401/403.
  - POST /auth/refresh {refreshToken} -> 200 {accessToken, refreshToken}.
  - /products is SIMULATED & NON-PERSISTENT: add/update/delete echo a success body but do NOT
    persist (a read of the freshly-created id 404s — documented, NOT a bug).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[2]))).resolve()
TARGET_DEFAULT = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
PUBLIC_BASE_URL = "https://dummyjson.com"           # what {{base_url}} points to for graders
VALID_CREDS = {"username": "emilys", "password": "emilyspass"}
INVALID_BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"   # clearly-bad JWT -> 401/403

AREAS = ("Authentication", "CRUD", "Search & Filtering", "Error Handling")
AGENT_OF_AREA = {
    "Authentication": "test-authentication-flows",
    "CRUD": "verify-crud-operation-integrity",
    "Search & Filtering": "validate-search-and-filter-queries",
    "Error Handling": "verify-error-message-clarity",
}


# --------------------------------------------------------------------------- #
# Scenario contract — ordered; auth scenarios run first to capture the token.
# A scenario:
#   id, area, title, method, path, query{}, body(None|dict), auth(None|'bearer'|'bad'|'refresh'),
#   expected_status, assertions[], capture{env_var: body_key}, precondition, note
# Assertion kinds: status / has / eq / type / each / len_lte / sorted / contains / subset_keys
# --------------------------------------------------------------------------- #
def _scenarios() -> list[dict]:
    S: list[dict] = []

    # ───────────── Authentication (JWT lifecycle) ─────────────
    S += [
        {"id": "AUTH-LOGIN-VALID", "area": "Authentication",
         "title": "Login with valid credentials returns 200 + accessToken + refreshToken",
         "method": "POST", "path": "/auth/login", "body": dict(VALID_CREDS),
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "has", "path": "accessToken"},
                        {"t": "has", "path": "refreshToken"}, {"t": "eq", "path": "username", "val": "emilys"}],
         "capture": {"token": "accessToken", "refreshToken": "refreshToken"},
         "precondition": "Seed user emilys/emilyspass exists.",
         "note": "Tokens returned in body and as cookies."},
        {"id": "AUTH-LOGIN-WRONGPASS", "area": "Authentication",
         "title": "Login with wrong password is rejected (400)",
         "method": "POST", "path": "/auth/login",
         "body": {"username": "emilys", "password": "wrong-password"},
         "expected_status": 400,
         "assertions": [{"t": "status", "in": [400, 401]}, {"t": "has", "path": "message"}],
         "precondition": "Valid username, invalid password."},
        {"id": "AUTH-LOGIN-UNKNOWN", "area": "Authentication",
         "title": "Login with unknown username is rejected (400)",
         "method": "POST", "path": "/auth/login",
         "body": {"username": "no-such-user-zzz", "password": "whatever"},
         "expected_status": 400,
         "assertions": [{"t": "status", "in": [400, 401]}, {"t": "has", "path": "message"}]},
        {"id": "AUTH-LOGIN-MISSING-FIELDS", "area": "Authentication",
         "title": "Login with missing credentials is rejected (400)",
         "method": "POST", "path": "/auth/login", "body": {},
         "expected_status": 400,
         "assertions": [{"t": "status", "in": [400, 401]}, {"t": "has", "path": "message"}],
         "note": "Ambiguity: docs don't specify the missing-field error — assert 4xx + message."},
        {"id": "AUTH-ME-VALID", "area": "Authentication",
         "title": "GET /auth/me with a valid Bearer token returns the current user (200)",
         "method": "GET", "path": "/auth/me", "auth": "bearer",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "eq", "path": "username", "val": "emilys"},
                        {"t": "has", "path": "email"}],
         "precondition": "A valid accessToken captured from AUTH-LOGIN-VALID."},
        {"id": "AUTH-ME-MISSING", "area": "Authentication",
         "title": "GET /auth/me without a token is rejected (401/403)",
         "method": "GET", "path": "/auth/me",
         "expected_status": 401,
         "assertions": [{"t": "status", "in": [401, 403]}, {"t": "has", "path": "message"}]},
        {"id": "AUTH-ME-MALFORMED", "area": "Authentication",
         "title": "GET /auth/me with a malformed/invalid token is rejected (401/403)",
         "method": "GET", "path": "/auth/me", "auth": "bad",
         "expected_status": 401,
         "assertions": [{"t": "status", "in": [401, 403]}, {"t": "has", "path": "message"}]},
        {"id": "AUTH-ME-EXPIRED", "area": "Authentication",
         "title": "GET /auth/me with an expired token is rejected (401/403)",
         "method": "GET", "path": "/auth/me", "auth": "expired",
         "expected_status": 401,
         "assertions": [{"t": "status", "in": [401, 403]}, {"t": "has", "path": "message"}],
         "note": "Token minted with a past exp via the shared auth_spec recipe."},
        {"id": "AUTH-ME-REVOKED", "area": "Authentication",
         "title": "GET /auth/me after logout (revoked) — JWT is stateless, so behaviour is a coverage gap",
         "method": "GET", "path": "/auth/me", "auth": "revoked",
         "expected_status": 401,
         "assertions": [{"t": "status", "in": [200, 401, 403]}],
         "note": "Ambiguity: DummyJSON JWTs are stateless; logout may NOT invalidate an issued token. "
                 "Recorded, not asserted strictly."},
        {"id": "AUTH-REFRESH-VALID", "area": "Authentication",
         "title": "POST /auth/refresh with a valid refreshToken mints a new accessToken (200)",
         "method": "POST", "path": "/auth/refresh", "auth": "refresh",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "has", "path": "accessToken"},
                        {"t": "has", "path": "refreshToken"}],
         "precondition": "A valid refreshToken captured from AUTH-LOGIN-VALID."},
        {"id": "AUTH-REFRESH-MISSING", "area": "Authentication",
         "title": "POST /auth/refresh without a refreshToken is rejected (401/403)",
         "method": "POST", "path": "/auth/refresh", "body": {},
         "expected_status": 401,
         "assertions": [{"t": "status", "in": [400, 401, 403]}, {"t": "has", "path": "message"}]},
    ]

    # ───────────── CRUD — products (simulated, non-persistent) ─────────────
    new_body = {"title": "Forge Test Widget", "price": 42, "category": "groceries", "stock": 7}
    S += [
        {"id": "CRUD-READ-LIST", "area": "CRUD",
         "title": "GET /products returns a paginated product list (200)",
         "method": "GET", "path": "/products", "query": {"limit": 5},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "type", "path": "products", "is": "array"},
                        {"t": "has", "path": "total"}, {"t": "len_lte", "path": "products", "n": 5}]},
        {"id": "CRUD-READ-ONE", "area": "CRUD",
         "title": "GET /products/1 returns a single product with the expected shape (200)",
         "method": "GET", "path": "/products/1",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "eq", "path": "id", "val": 1},
                        {"t": "has", "path": "title"}, {"t": "has", "path": "price"}]},
        {"id": "CRUD-CREATE", "area": "CRUD",
         "title": "POST /products/add echoes the new product with an id (201, simulated)",
         "method": "POST", "path": "/products/add", "body": dict(new_body),
         "expected_status": 201,
         "assertions": [{"t": "status", "in": [200, 201]}, {"t": "eq", "path": "title", "val": "Forge Test Widget"},
                        {"t": "type", "path": "id", "is": "number"}],
         "capture": {"newProductId": "id"},
         "note": "DummyJSON SIMULATES creation: it returns a success body + a fresh id but does NOT persist."},
        {"id": "CRUD-CREATE-NONPERSIST", "area": "CRUD",
         "title": "GET the freshly-created product id returns 404 — documented non-persistence (not a bug)",
         "method": "GET", "path": "/products/{newProductId}",
         "expected_status": 404,
         "assertions": [{"t": "status", "eq": 404}, {"t": "contains", "path": "message", "sub": "not found"}],
         "precondition": "newProductId captured from CRUD-CREATE.",
         "note": "Proves the simulated contract: the add succeeded but nothing was stored."},
        {"id": "CRUD-UPDATE", "area": "CRUD",
         "title": "PUT /products/1 echoes the changed field (200, simulated)",
         "method": "PUT", "path": "/products/1", "body": {"title": "Forge Updated Title"},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "eq", "path": "id", "val": 1},
                        {"t": "eq", "path": "title", "val": "Forge Updated Title"}],
         "note": "Update is simulated: the changed field is echoed back, not persisted."},
        {"id": "CRUD-DELETE", "area": "CRUD",
         "title": "DELETE /products/1 returns the product flagged isDeleted + deletedOn (200, simulated)",
         "method": "DELETE", "path": "/products/1",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "eq", "path": "isDeleted", "val": True},
                        {"t": "has", "path": "deletedOn"}],
         "note": "Delete is simulated: it flags isDeleted/deletedOn but does not remove the record."},
        {"id": "CRUD-READ-MISSING", "area": "CRUD",
         "title": "GET /products/99999 returns 404 with a clear message",
         "method": "GET", "path": "/products/99999",
         "expected_status": 404,
         "assertions": [{"t": "status", "eq": 404}, {"t": "contains", "path": "message", "sub": "not found"}]},
        {"id": "CRUD-UPDATE-MISSING", "area": "CRUD",
         "title": "PUT /products/99999 (nonexistent) returns 404",
         "method": "PUT", "path": "/products/99999", "body": {"title": "x"},
         "expected_status": 404,
         "assertions": [{"t": "status", "in": [404, 400]}, {"t": "has", "path": "message"}]},
        {"id": "CRUD-DELETE-MISSING", "area": "CRUD",
         "title": "DELETE /products/99999 (nonexistent) returns 404",
         "method": "DELETE", "path": "/products/99999",
         "expected_status": 404,
         "assertions": [{"t": "status", "in": [404, 400]}, {"t": "has", "path": "message"}]},
    ]

    # ───────────── Search & Filtering ─────────────
    S += [
        {"id": "SEARCH-KEYWORD", "area": "Search & Filtering",
         "title": "GET /products/search?q=phone returns matching products (200)",
         "method": "GET", "path": "/products/search", "query": {"q": "phone"},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "type", "path": "products", "is": "array"},
                        {"t": "has", "path": "total"}]},
        {"id": "SEARCH-KEYWORD-EMPTY", "area": "Search & Filtering",
         "title": "GET /products/search?q=<nonsense> returns an empty product set (200, total 0)",
         "method": "GET", "path": "/products/search", "query": {"q": "zzzqx-no-match"},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "type", "path": "products", "is": "array"},
                        {"t": "eq", "path": "total", "val": 0}]},
        {"id": "FILTER-CATEGORY", "area": "Search & Filtering",
         "title": "GET /products/category/smartphones returns only that category (200)",
         "method": "GET", "path": "/products/category/smartphones",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "type", "path": "products", "is": "array"},
                        {"t": "each", "path": "products", "key": "category", "op": "eq", "val": "smartphones"}]},
        {"id": "FILTER-CATEGORY-LIST", "area": "Search & Filtering",
         "title": "GET /products/categories returns the category list (200)",
         "method": "GET", "path": "/products/categories",
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "type", "path": "$root", "is": "array"}]},
        {"id": "PAGE-LIMIT-SKIP", "area": "Search & Filtering",
         "title": "GET /products?limit=5&skip=10 honours pagination (200)",
         "method": "GET", "path": "/products", "query": {"limit": 5, "skip": 10},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200}, {"t": "len_lte", "path": "products", "n": 5},
                        {"t": "eq", "path": "skip", "val": 10}, {"t": "eq", "path": "limit", "val": 5}]},
        {"id": "SELECT-FIELDS", "area": "Search & Filtering",
         "title": "GET /products?select=title,price returns only the selected fields (+id) (200)",
         "method": "GET", "path": "/products", "query": {"limit": 3, "select": "title,price"},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200},
                        {"t": "subset_keys", "path": "products", "allowed": ["id", "title", "price"]}]},
        {"id": "SORT-ASC", "area": "Search & Filtering",
         "title": "GET /products?sortBy=title&order=asc returns title-sorted products (200)",
         "method": "GET", "path": "/products", "query": {"limit": 10, "sortBy": "title", "order": "asc"},
         "expected_status": 200,
         "assertions": [{"t": "status", "eq": 200},
                        {"t": "sorted", "path": "products", "key": "title", "order": "asc"}]},
    ]
    return S


SCENARIOS = _scenarios()


# --------------------------------------------------------------------------- #
# HTTP + assertion evaluation
# --------------------------------------------------------------------------- #
def _request(base: str, method: str, path: str, body=None, headers=None) -> tuple[int | None, object, str]:
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:  # noqa: BLE001 — target down / network
        return None, None, f"{type(e).__name__}: {e}"
    try:
        return code, json.loads(raw), ""
    except json.JSONDecodeError:
        return code, raw, ""


def _get(obj, path: str):
    """Dot-path getter. '$root' => obj itself. Returns (found, value)."""
    if path == "$root":
        return True, obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def _check(a: dict, status: int | None, body) -> tuple[bool, str]:
    t = a["t"]
    if t == "status":
        if "eq" in a:
            return status == a["eq"], f"status == {a['eq']}"
        return status in a["in"], f"status in {a['in']}"
    found, val = _get(body, a.get("path", "$root"))
    if t == "has":
        return found, f"body has '{a['path']}'"
    if t == "eq":
        return found and val == a["val"], f"{a['path']} == {a['val']!r}"
    if t == "type":
        want = a["is"]
        ok = found and ((want == "array" and isinstance(val, list)) or
                        (want == "number" and isinstance(val, (int, float)) and not isinstance(val, bool)) or
                        (want == "string" and isinstance(val, str)))
        return ok, f"{a['path']} is {want}"
    if t == "len_lte":
        return found and isinstance(val, list) and len(val) <= a["n"], f"len({a['path']}) <= {a['n']}"
    if t == "contains":
        return found and isinstance(val, str) and a["sub"].lower() in val.lower(), f"{a['path']} contains '{a['sub']}'"
    if t == "each":
        if not (found and isinstance(val, list) and val):
            return False, f"each({a['path']}) non-empty array"
        ok = all(isinstance(it, dict) and it.get(a["key"]) == a["val"] for it in val)
        return ok, f"every {a['path']}[].{a['key']} == {a['val']!r}"
    if t == "subset_keys":
        if not (found and isinstance(val, list) and val):
            return False, f"{a['path']} non-empty array"
        allowed = set(a["allowed"])
        ok = all(isinstance(it, dict) and set(it).issubset(allowed) for it in val)
        return ok, f"every {a['path']}[] keys ⊆ {sorted(allowed)}"
    if t == "sorted":
        if not (found and isinstance(val, list)):
            return False, f"{a['path']} array"
        keys = [it.get(a["key"]) for it in val if isinstance(it, dict)]
        srt = sorted(keys, reverse=(a.get("order") == "desc"))
        return keys == srt, f"{a['path']} sorted by {a['key']} {a.get('order','asc')}"
    return False, f"unknown assertion {t}"


def _auth_headers(kind: str | None, ctx: dict, base: str) -> dict:
    if not kind:
        return {}
    if kind == "bearer":
        return {"Authorization": f"Bearer {ctx.get('token','')}"}
    if kind == "bad":
        return {"Authorization": INVALID_BEARER}
    if kind in ("expired", "revoked"):
        try:                                   # faithful construction via the shared auth substrate
            import auth_spec
            recipe = {"expired": {"kind": "expired_token", "exp_delta_sec": -3600},
                      "revoked": {"kind": "revoked_token", "revoke_via": "POST /auth/logout"}}[kind]
            headers, _ = auth_spec.build_credential(recipe, base, os.environ.get("JWT_SECRET", "forge_test_secret"))
            return headers
        except Exception:  # noqa: BLE001
            return {"Authorization": INVALID_BEARER}
    return {}


def run(target: str | None = None) -> list[dict]:
    """Execute every scenario against `target`, carrying token/created-id context. Returns one
    result dict per scenario: {**scenario, actual_status, actual_body, passed, checks[], blocked}."""
    base = (target or TARGET_DEFAULT).rstrip("/")
    ctx: dict = {}
    results: list[dict] = []
    for sc in SCENARIOS:
        path = sc["path"].replace("{newProductId}", str(ctx.get("newProductId", "0")))
        query = sc.get("query") or {}
        if query:
            from urllib.parse import urlencode
            path = path + "?" + urlencode(query)
        headers = {}
        if sc.get("auth") == "refresh":
            body = {"refreshToken": ctx.get("refreshToken", "")}
        else:
            body = sc.get("body")
            headers = _auth_headers(sc.get("auth"), ctx, base)
        status, rbody, err = _request(base, sc["method"], path, body=body, headers=headers)
        blocked = status is None
        checks = []
        for a in sc["assertions"]:
            ok, desc = (False, f"blocked: {err}") if blocked else _check(a, status, rbody)
            checks.append({"ok": ok, "desc": desc})
        passed = (not blocked) and all(c["ok"] for c in checks)
        for env_var, key in (sc.get("capture") or {}).items():
            if isinstance(rbody, dict) and key in rbody:
                ctx[env_var] = rbody[key]
        results.append({**sc, "resolved_path": path, "sent_body": body, "sent_headers": headers,
                        "actual_status": status, "actual_body": rbody, "error": err,
                        "blocked": blocked, "passed": passed, "checks": checks})
    return results


if __name__ == "__main__":
    res = run(sys.argv[1] if len(sys.argv) > 1 else None)
    p = sum(1 for r in res if r["passed"]); b = sum(1 for r in res if r["blocked"])
    print(f"core-requirements: {len(res)} scenarios | pass={p} fail={len(res)-p-b} blocked={b}")
    for r in res:
        mark = "PASS" if r["passed"] else ("BLOCK" if r["blocked"] else "FAIL")
        print(f"  [{mark}] {r['id']:24} {r['method']:6} {r['resolved_path']}  -> {r['actual_status']}")
