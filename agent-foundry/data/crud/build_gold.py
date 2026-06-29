#!/usr/bin/env python3
"""Gold-set builder for the Verify-CRUD-Operation-Integrity task.

NOT one of the four agents. The deterministic *reference*: it authors the OpenAPI 3
spec the agents parse (documenting each resource's Create/Read/Update/Delete
contract + a fixed create/update fixture), applies the canonical 8-step recipe
(agents/common/crud_spec.py) to every resource, executes it against a locally
running DummyJSON, performs a read-only direct read of the resource's backing store
(database/<table>.json) at each checkpoint, and records the REAL observed HTTP code,
response-body field echoes, and DB state.

The recorded behavior is the ground truth. Agents are later ranked on how faithfully
their own runs reproduce this table (CRUD-Test Fidelity). The headline CRUD Integrity
Rate is the real QA finding.

Key finding this surfaces: DummyJSON SIMULATES writes (CREATE returns a synthetic id
but the store is the frozen database/*.json, never mutated), so READ/UPDATE/DELETE on
the created id 404 and the DB never reflects the create -> CRUD Integrity Rate = 0%.

Outputs (under data/crud/):
  - openapi.json        the spec the agents parse (the task INPUT)
  - gold/<slug>.json    per-resource gold cases
  - gold.json           consolidated gold table + empirical summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. Read-only DB reads of the target repo's database/ dir. Air-gapped.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
# DummyJSON enforces 100 req/10s per IP (no env toggle); pace + retry-on-429 so the
# gold records the TRUE CRUD behavior, not rate-limit noise. DummyJSON is untouched.
REQ_DELAY_S = float(os.environ.get("FORGE_REQ_DELAY_S", "0.15"))
RL_RETRIES = int(os.environ.get("FORGE_RL_RETRIES", "6"))
RL_BACKOFF_S = float(os.environ.get("FORGE_RL_BACKOFF_S", "10.5"))
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
# data/crud -> data -> foundry -> target repo (DummyJSON). The DB store lives here.
TARGET_REPO = HERE.parents[2]
DB_DIR = TARGET_REPO / "database"

sys.path.insert(0, str(HERE.parent.parent / "agents" / "common"))
import crud_spec  # noqa: E402


# Each resource: db table (= database/<table>.json), REST paths, and the fixed
# create/update fixture. Where the resource has >=5 settable flat fields the literal
# "5 fields / change 3 / keep 2" shape is used (products, users, recipes, posts);
# comments/todos/carts have fewer settable fields, so they use their natural set
# (documented honestly in the summary).
RESOURCES = [
    {"slug": "products", "table": "products", "base_path": "/products",
     "add_path": "/products/add", "auth_required": False,
     "create_body": {"title": "Test-001", "price": 42, "stock": 7,
                     "brand": "Test-Brand", "category": "smartphones"},
     "update_body": {"title": "Test-001-updated", "price": 99, "stock": 13}},

    {"slug": "posts", "table": "posts", "base_path": "/posts",
     "add_path": "/posts/add", "auth_required": False,
     "create_body": {"title": "Test-001", "body": "original body", "userId": 1,
                     "tags": ["x"], "reactions": 5},
     "update_body": {"title": "Test-001-updated", "body": "updated body", "reactions": 9}},

    {"slug": "comments", "table": "comments", "base_path": "/comments",
     "add_path": "/comments/add", "auth_required": False,
     "create_body": {"body": "Test comment 001", "postId": 1, "userId": 1},
     "update_body": {"body": "Test comment 001 - updated"}},

    {"slug": "todos", "table": "todos", "base_path": "/todos",
     "add_path": "/todos/add", "auth_required": False,
     "create_body": {"todo": "Test todo 001", "completed": False, "userId": 1},
     "update_body": {"todo": "Test todo 001 - updated", "completed": True}},

    {"slug": "carts", "table": "carts", "base_path": "/carts",
     "add_path": "/carts/add", "auth_required": False,
     "create_body": {"userId": 1, "products": [{"id": 1, "quantity": 2}]},
     "update_body": {"merge": False, "products": [{"id": 1, "quantity": 5}]}},

    {"slug": "users", "table": "users", "base_path": "/users",
     "add_path": "/users/add", "auth_required": False,
     "create_body": {"firstName": "Test", "lastName": "User", "age": 30,
                     "email": "test001@example.com", "phone": "+10000000001"},
     "update_body": {"firstName": "Test-upd", "lastName": "User-upd", "age": 31}},

    {"slug": "recipes", "table": "recipes", "base_path": "/recipes",
     "add_path": "/recipes/add", "auth_required": False,
     "create_body": {"name": "Test Recipe 001", "cuisine": "Italian",
                     "difficulty": "Easy", "servings": 4, "caloriesPerServing": 200},
     "update_body": {"name": "Test Recipe 001 - updated", "cuisine": "Mexican",
                     "difficulty": "Hard"}},
]


# --------------------------------------------------------------------------- #
# HTTP (no auth needed: resource CRUD is public) + read-only DB read
# --------------------------------------------------------------------------- #
def _send_once(method: str, path: str, body) -> tuple[int, object]:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try:
                return r.getcode(), json.loads(raw)
            except Exception:  # noqa
                return r.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa
            return e.code, None
    except Exception:  # noqa
        return -1, None


def send(method: str, path: str, body) -> tuple[int, object]:
    if REQ_DELAY_S > 0:
        time.sleep(REQ_DELAY_S)
    code, resp = _send_once(method, path, body)
    attempts = 0
    while code == 429 and attempts < RL_RETRIES:
        time.sleep(RL_BACKOFF_S)
        attempts += 1
        code, resp = _send_once(method, path, body)
    return code, resp


def db_read(table: str, resource_id) -> dict:
    """Read-only direct query of the backing store database/<table>.json for one id.

    This is the deliberate, narrowly-scoped, READ-ONLY exception the task requires
    ('verify by direct database query'). It touches ONLY <repo>/database/<table>.json
    and never writes. Returns {state, record}: state in {"present","absent","no_store"}.
    """
    f = (DB_DIR / f"{table}.json").resolve()
    # hard guard: only the documented store dir, only .json, read-only
    if DB_DIR.resolve() not in f.parents or f.suffix != ".json" or not f.exists():
        return {"state": "no_store", "record": None}
    try:
        rows = json.loads(f.read_text())
    except Exception:  # noqa
        return {"state": "no_store", "record": None}
    if not isinstance(rows, list):
        return {"state": "no_store", "record": None}
    if resource_id is None:
        return {"state": "absent", "record": None}
    for row in rows:
        if isinstance(row, dict) and str(row.get("id")) == str(resource_id):
            return {"state": "present", "record": row}
    return {"state": "absent", "record": None}


# --------------------------------------------------------------------------- #
# Execute the canonical plan for one resource and record real observations
# --------------------------------------------------------------------------- #
def run_resource(resource: dict) -> dict:
    plan = crud_spec.reference_plan(resource)
    table = plan["table"]
    create_body = resource["create_body"]
    post_update_state = crud_spec.expected_post_update(resource)

    resource_id = None
    step_records = []
    db_records = []

    for step in plan["steps"]:
        path = step["path"].replace(crud_spec.ID_PLACEHOLDER, str(resource_id)
                                    if resource_id is not None else crud_spec.ID_PLACEHOLDER)
        code, resp = send(step["method"], path, step["body"])
        if step.get("capture_id") and isinstance(resp, dict):
            resource_id = resp.get("id")
        # response-body field echo check (where the step submits a body)
        body_match = None
        if step["step"] == "CREATE":
            body_match = crud_spec.subset_matches(create_body, resp)
        elif step["step"] in ("UPDATE", "READ_AFTER_UPDATE"):
            body_match = crud_spec.subset_matches(post_update_state, resp)
        step_records.append({"step": step["step"], "method": step["method"],
                             "sent_path": path, "actual_code": code,
                             "body_field_match": body_match,
                             "captured_id": resource_id if step.get("capture_id") else None})

        # DB checkpoints after CREATE, READ, UPDATE
        if step["step"] in ("CREATE", "READ", "UPDATE"):
            chk = {"CREATE": "DB_AFTER_CREATE", "READ": "DB_AFTER_READ",
                   "UPDATE": "DB_AFTER_UPDATE"}[step["step"]]
            r = db_read(table, resource_id)
            db_records.append({"checkpoint": chk, "resource_id": resource_id,
                               "db_state": r["state"]})

    # FINAL DB checkpoint (after delete)
    r = db_read(table, resource_id)
    db_records.append({"checkpoint": "DB_FINAL", "resource_id": resource_id,
                       "db_state": r["state"]})

    integrity = compute_integrity(resource, step_records, db_records)
    return {"slug": resource["slug"], "table": table,
            "auth_required": bool(resource.get("auth_required")),
            "field_count": len(create_body),
            "changed_field_count": len(resource["update_body"]),
            "kept_fields": crud_spec.kept_fields(resource),
            "create_body": create_body, "update_body": resource["update_body"],
            "steps": step_records, "db_checkpoints": db_records,
            "integrity_pass": integrity["pass"], "integrity_detail": integrity["detail"]}


def compute_integrity(resource: dict, steps: list, dbs: list) -> dict:
    """Strict pass: every HTTP step matches its expected code (+ body echo where
    applicable) AND every DB checkpoint matches its expected state. Returns
    {pass: bool, detail: {...}}."""
    by_step = {s["step"]: s for s in steps}
    by_db = {d["checkpoint"]: d for d in dbs}
    detail = {}
    ok = True

    for name, exp in crud_spec.STRICT_EXPECT.items():
        if name == "DB_FINAL":
            continue
        s = by_step.get(name)
        if s is None:
            detail[name] = {"http": "missing"}
            ok = False
            continue
        http_ok = s["actual_code"] in exp["code"]
        body_ok = (s["body_field_match"] is not False)  # None (n/a) counts ok
        passed = http_ok and body_ok
        detail[name] = {"actual_code": s["actual_code"], "http_ok": http_ok,
                        "body_ok": body_ok, "pass": passed}
        ok = ok and passed

    # DB checkpoints -> expected present states; FINAL -> absent_or_soft_deleted
    db_expect = {"DB_AFTER_CREATE": ("present",), "DB_AFTER_READ": ("present",),
                 "DB_AFTER_UPDATE": ("present",)}
    for chk, allowed in db_expect.items():
        d = by_db.get(chk)
        state = d["db_state"] if d else "missing"
        passed = state in allowed
        detail[chk] = {"db_state": state, "pass": passed}
        ok = ok and passed
    final = by_db.get("DB_FINAL")
    fstate = final["db_state"] if final else "missing"
    final_ok = fstate in ("absent",)  # hard delete; soft-delete row not modeled here
    detail["DB_FINAL"] = {"db_state": fstate, "pass": final_ok}
    ok = ok and final_ok

    return {"pass": ok, "detail": detail}


# --------------------------------------------------------------------------- #
# OpenAPI spec the agents parse
# --------------------------------------------------------------------------- #
def build_openapi() -> dict:
    paths: dict = {}
    for r in RESOURCES:
        item = f"{r['base_path']}/{{id}}"
        paths.setdefault(r["add_path"], {})["post"] = {
            "operationId": f"{r['slug']}_create",
            "x-crud-resource": r["slug"], "x-crud-table": r["table"],
            "x-crud-create-body": r["create_body"], "x-crud-update-body": r["update_body"],
            "requestBody": {"required": True, "content": {"application/json": {
                "schema": {"type": "object"}, "example": r["create_body"]}}},
            "responses": {"201": {"description": "created"}}}
        paths.setdefault(item, {})
        paths[item]["get"] = {"operationId": f"{r['slug']}_read",
                              "responses": {"200": {"description": "ok"},
                                            "404": {"description": "not found"}}}
        paths[item]["put"] = {"operationId": f"{r['slug']}_update",
                              "requestBody": {"content": {"application/json": {
                                  "example": r["update_body"]}}},
                              "responses": {"200": {"description": "ok"},
                                            "404": {"description": "not found"}}}
        paths[item]["delete"] = {"operationId": f"{r['slug']}_delete",
                                 "responses": {"200": {"description": "deleted"},
                                               "404": {"description": "not found"}}}
    return {
        "openapi": "3.0.3",
        "info": {"title": "DummyJSON (authored for the CRUD-integrity task)",
                 "version": "1.0.0",
                 "description": "Per-resource CRUD contract authored from DummyJSON "
                                "routes/controllers. Agents parse THIS spec; ground truth "
                                "is the live API's observed HTTP code + the read-only DB "
                                "state per (resource, step)."},
        "servers": [{"url": BASE_URL}],
        "x-crud-resources": [r["slug"] for r in RESOURCES],
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

    consolidated = []
    passed = 0
    for r in RESOURCES:
        rec = run_resource(r)
        (GOLD_DIR / f"{r['slug']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)
        passed += int(rec["integrity_pass"])

    total = len(RESOURCES)
    rate = round(100.0 * passed / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "resource_types": total,
        "resource_types_fully_passing": passed,
        "empirical_crud_integrity_rate_pct": rate,
        "note": "Ground truth = live DummyJSON observed HTTP code + read-only direct read "
                "of database/<table>.json per (resource, step). DummyJSON SIMULATES writes: "
                "CREATE returns a synthetic id but the store is the frozen database/*.json "
                "and is never mutated, so READ/UPDATE/DELETE on the created id 404 and the DB "
                "never reflects the create. CRUD Integrity Rate is therefore 0% by design "
                "(the real QA finding), not a harness defect.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "resources": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
