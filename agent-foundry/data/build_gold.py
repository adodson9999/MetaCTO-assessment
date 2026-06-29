#!/usr/bin/env python3
"""Gold-set builder for the API request-body contract-testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the OpenAPI 3 spec the agents must parse, generates the canonical
1-valid + 5-invalid payload matrix per endpoint, sends every payload to a
locally-running DummyJSON, and records the REAL observed status code.

The recorded behavior is the ground truth. Agents are later ranked on how
faithfully their own runs reproduce this table (coverage + correct codes +
correct pass/fail classification).

Outputs (all under data/):
  - openapi.json        the spec the agents parse (the task INPUT)
  - gold/<slug>.json    per-endpoint gold cases
  - gold.json           consolidated gold table + empirical summary

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

# The 5 invalid variant ids, in fixed order (per the task spec).
VARIANTS = [
    "valid",                 # 1 valid payload  -> expect 2xx
    "inv_missing_required",  # (a) drop one required field
    "inv_wrong_type",        # (b) wrong data type on one field
    "inv_extra_field",       # (c) extra undocumented field
    "inv_all_null",          # (d) all documented fields null
    "inv_maxlength",         # (e) string field at maxLength+1
]

# ---------------------------------------------------------------------------
# Endpoint catalogue. Each entry declares the request-body schema explicitly
# (required / type / maxLength) so every invalid variant is well-defined.
# `valid` holds a known-good body. `maxlen_field` names the string field used
# for the maxLength+1 variant (None => that variant is not applicable).
# `path` may contain {id}; we substitute an existing id (1).
# ---------------------------------------------------------------------------
def s(maxlen=None):  # string field
    return {"type": "string", **({"maxLength": maxlen} if maxlen else {})}

ENDPOINTS = [
    {
        "slug": "auth_login", "method": "POST", "path": "/auth/login",
        "fields": {"username": s(40), "password": s(60), "expiresInMins": {"type": "integer"}},
        "required": ["username", "password"], "maxlen_field": "username",
        "valid": {"username": "emilys", "password": "emilyspass"},
    },
    # products
    {
        "slug": "products_add", "method": "POST", "path": "/products/add",
        "fields": {"title": s(100), "description": s(500), "price": {"type": "number"}, "stock": {"type": "integer"}, "category": s(60)},
        "required": ["title", "price"], "maxlen_field": "title",
        "valid": {"title": "Forge Test Widget", "price": 9.99, "stock": 5, "category": "tools"},
    },
    {
        "slug": "products_put", "method": "PUT", "path": "/products/{id}",
        "fields": {"title": s(100), "price": {"type": "number"}, "stock": {"type": "integer"}},
        "required": ["title"], "maxlen_field": "title",
        "valid": {"title": "Updated Widget", "price": 12.5},
    },
    {
        "slug": "products_patch", "method": "PATCH", "path": "/products/{id}",
        "fields": {"title": s(100), "price": {"type": "number"}},
        "required": ["title"], "maxlen_field": "title",
        "valid": {"title": "Patched Widget"},
    },
    # posts
    {
        "slug": "posts_add", "method": "POST", "path": "/posts/add",
        "fields": {"title": s(150), "body": s(1000), "userId": {"type": "integer"}, "tags": {"type": "array"}},
        "required": ["title", "userId"], "maxlen_field": "title",
        "valid": {"title": "A Forge Post", "body": "hello world", "userId": 1, "tags": ["a"]},
    },
    {
        "slug": "posts_put", "method": "PUT", "path": "/posts/{id}",
        "fields": {"title": s(150), "body": s(1000), "userId": {"type": "integer"}},
        "required": ["title"], "maxlen_field": "title",
        "valid": {"title": "Updated Post", "body": "edited"},
    },
    {
        "slug": "posts_patch", "method": "PATCH", "path": "/posts/{id}",
        "fields": {"title": s(150), "body": s(1000)},
        "required": ["title"], "maxlen_field": "title",
        "valid": {"title": "Patched Post"},
    },
    # todos
    {
        "slug": "todos_add", "method": "POST", "path": "/todos/add",
        "fields": {"todo": s(200), "completed": {"type": "boolean"}, "userId": {"type": "integer"}},
        "required": ["todo", "completed", "userId"], "maxlen_field": "todo",
        "valid": {"todo": "Ship the foundry", "completed": False, "userId": 1},
    },
    {
        "slug": "todos_put", "method": "PUT", "path": "/todos/{id}",
        "fields": {"todo": s(200), "completed": {"type": "boolean"}, "userId": {"type": "integer"}},
        "required": ["todo"], "maxlen_field": "todo",
        "valid": {"todo": "Updated todo", "completed": True},
    },
    {
        "slug": "todos_patch", "method": "PATCH", "path": "/todos/{id}",
        "fields": {"todo": s(200), "completed": {"type": "boolean"}},
        "required": ["completed"], "maxlen_field": "todo",
        "valid": {"completed": True},
    },
    # users
    {
        "slug": "users_add", "method": "POST", "path": "/users/add",
        "fields": {"firstName": s(50), "lastName": s(50), "age": {"type": "integer"}, "email": s(120)},
        "required": ["firstName"], "maxlen_field": "firstName",
        "valid": {"firstName": "Forge", "lastName": "Tester", "age": 30, "email": "f@example.com"},
    },
    {
        "slug": "users_put", "method": "PUT", "path": "/users/{id}",
        "fields": {"firstName": s(50), "lastName": s(50), "age": {"type": "integer"}},
        "required": ["firstName"], "maxlen_field": "firstName",
        "valid": {"firstName": "Updated", "lastName": "Name"},
    },
    {
        "slug": "users_patch", "method": "PATCH", "path": "/users/{id}",
        "fields": {"firstName": s(50), "age": {"type": "integer"}},
        "required": ["firstName"], "maxlen_field": "firstName",
        "valid": {"firstName": "Patched"},
    },
    # recipes
    {
        "slug": "recipes_add", "method": "POST", "path": "/recipes/add",
        "fields": {"name": s(100), "ingredients": {"type": "array"}, "instructions": {"type": "array"}, "prepTimeMinutes": {"type": "integer"}},
        "required": ["name", "ingredients"], "maxlen_field": "name",
        "valid": {"name": "Forge Stew", "ingredients": ["water"], "instructions": ["boil"], "prepTimeMinutes": 10},
    },
    {
        "slug": "recipes_put", "method": "PUT", "path": "/recipes/{id}",
        "fields": {"name": s(100), "ingredients": {"type": "array"}},
        "required": ["name"], "maxlen_field": "name",
        "valid": {"name": "Updated Stew", "ingredients": ["salt"]},
    },
    {
        "slug": "recipes_patch", "method": "PATCH", "path": "/recipes/{id}",
        "fields": {"name": s(100), "prepTimeMinutes": {"type": "integer"}},
        "required": ["name"], "maxlen_field": "name",
        "valid": {"name": "Patched Stew"},
    },
    # carts  (NB: no string field -> inv_maxlength not applicable)
    {
        "slug": "carts_add", "method": "POST", "path": "/carts/add",
        "fields": {"userId": {"type": "integer"}, "products": {"type": "array"}},
        "required": ["userId", "products"], "maxlen_field": None,
        "valid": {"userId": 1, "products": [{"id": 1, "quantity": 2}]},
    },
    {
        "slug": "carts_put", "method": "PUT", "path": "/carts/{id}",
        "fields": {"merge": {"type": "boolean"}, "products": {"type": "array"}},
        "required": ["products"], "maxlen_field": None,
        "valid": {"merge": True, "products": [{"id": 1, "quantity": 3}]},
    },
    {
        "slug": "carts_patch", "method": "PATCH", "path": "/carts/{id}",
        "fields": {"merge": {"type": "boolean"}, "products": {"type": "array"}},
        "required": ["products"], "maxlen_field": None,
        "valid": {"merge": False, "products": [{"id": 1, "quantity": 1}]},
    },
    # comments
    {
        "slug": "comments_add", "method": "POST", "path": "/comments/add",
        "fields": {"body": s(300), "postId": {"type": "integer"}, "userId": {"type": "integer"}},
        "required": ["body", "postId", "userId"], "maxlen_field": "body",
        "valid": {"body": "Nice post", "postId": 1, "userId": 1},
    },
    {
        "slug": "comments_put", "method": "PUT", "path": "/comments/{id}",
        "fields": {"body": s(300)},
        "required": ["body"], "maxlen_field": "body",
        "valid": {"body": "Updated comment"},
    },
    {
        "slug": "comments_patch", "method": "PATCH", "path": "/comments/{id}",
        "fields": {"body": s(300)},
        "required": ["body"], "maxlen_field": "body",
        "valid": {"body": "Patched comment"},
    },
]

EXISTING_ID = 1

# The labeled-array payload structure is defined once in agents/common/payload_spec.py
# and shared with the agent harness, so gold and agent output use the same case scheme.
sys.path.insert(0, str(HERE.parent / "agents" / "common"))
import payload_spec  # noqa: E402


def gen_payloads(ep):
    """Deterministically derive the canonical labeled payload object from the
    schema (the new array-based structure)."""
    return payload_spec.generate_payloads(ep["fields"], ep["required"], ep["valid"])


def send(method, path, body):
    url = BASE_URL + path.replace("{id}", str(EXISTING_ID))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa
        return -1


def build_openapi():
    paths = {}
    for ep in ENDPOINTS:
        props = ep["fields"]
        schema = {"type": "object", "properties": props, "required": ep["required"],
                  "additionalProperties": False}
        op = {
            "operationId": ep["slug"],
            "requestBody": {"required": True,
                            "content": {"application/json": {
                                "schema": schema,
                                "example": ep["valid"],  # known-good body (e.g. real login creds)
                            }}},
            "responses": {"2xx": {"description": "accepted"}, "400": {"description": "rejected"}},
        }
        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {"title": "DummyJSON (authored for contract-testing task)", "version": "1.0.0",
                 "description": "Request-body schemas authored from DummyJSON routes/controllers. "
                                "The agents parse THIS spec; ground truth is the live API's observed behavior."},
        "servers": [{"url": BASE_URL}],
        "paths": paths,
    }


def classify(code):
    if 200 <= code < 300:
        return "2xx"
    if code == 400:
        return "400"
    return f"other_{code}"


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "openapi.json").write_text(json.dumps(build_openapi(), indent=2))

    consolidated = []
    sent = correct_reject = total_invalid = 0
    for ep in ENDPOINTS:
        out = gen_payloads(ep)
        cases = []
        for category, label, field, expected_class, body in payload_spec.iter_cases(out):
            code = send(ep["method"], ep["path"], body)
            actual_class = classify(code)
            cases.append({"category": category, "label": label, "field": field,
                          "expected_class": expected_class, "actual_code": code,
                          "actual_class": actual_class, "payload": body})
            sent += 1
            if category != "valid":
                total_invalid += 1
                if actual_class == "400":
                    correct_reject += 1
        rec = {"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
               "schema": {"fields": ep["fields"], "required": ep["required"]},
               "cases": cases}
        (GOLD_DIR / f"{ep['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rejection_rate = round(100.0 * correct_reject / total_invalid, 2) if total_invalid else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "labeled_cases": sent,
        "invalid_cases": total_invalid,
        "invalid_rejected_400": correct_reject,
        "empirical_payload_rejection_rate_pct": rejection_rate,
        "note": "Ground truth = live DummyJSON observed codes per labeled case. Most "
                "add/update endpoints do NOT validate, so the empirical rejection rate is "
                "well below 100% by design.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
