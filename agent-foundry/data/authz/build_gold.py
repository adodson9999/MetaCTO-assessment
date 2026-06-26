#!/usr/bin/env python3
"""Deterministic gold reference for the authorization-rules task.

This is NOT one of the four agents. It is the canonical reference that:
  1. derives the three role-bearing users + the owner's resource from the target's
     own seed data (no roles invented; DummyJSON users already carry a `role`),
  2. writes data/authz/authz_spec.json — the access-surface description the four
     agents parse (it is the analog of the prior task's openapi.json),
  3. builds the canonical 8-case matrix (authz_spec.reference_matrix),
  4. executes every case against the LIVE target through the same executor the
     agents use (authz_contract.send/evaluate), recording the REAL observed code,
     data_exposed, and leak_safe, and
  5. writes data/authz/gold.json + data/authz/gold/<sub_test>.json and prints the
     empirical Access Control Accuracy Rate.

Run with the target already up:
    FORGE_TARGET_BASE_URL=http://localhost:8899 python3 data/authz/build_gold.py

Stdlib only. Self-locating: the workspace is two parents up from this file; the
target repo (DummyJSON seed data) is the workspace's parent.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
WORKSPACE = HERE.parents[2]          # data/authz/build_gold.py -> agent-foundry/
TARGET_REPO = WORKSPACE.parent
os.environ.setdefault("FORGE_WORKSPACE", str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import authz_spec      # noqa: E402
import authz_contract  # noqa: E402

BASE = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
authz_contract.TARGET_BASE_URL = BASE


def _load_seed(name: str):
    raw = json.loads((TARGET_REPO / "database" / f"{name}.json").read_text())
    return raw if isinstance(raw, list) else raw.get(name, raw)


def derive_entities() -> dict:
    """Pick admin / owner(B) / viewer(A) from the seed and the owned resource.

    admin  = first user with role 'admin'
    owner  = first user with role 'user' who owns at least one post
    viewer = first user with role 'user' that is neither owner nor a resource owner
    resource = a post owned by `owner`  (the owner-scoped resource under test)
    """
    users = _load_seed("users")
    posts = _load_seed("posts")
    by_role = lambda r: [u for u in users if u.get("role") == r]

    admin = by_role("admin")[0]
    owner = next(u for u in by_role("user")
                 if any(p.get("userId") == u["id"] for p in posts))
    res_post = next(p for p in posts if p.get("userId") == owner["id"])
    viewer = next(u for u in by_role("user")
                  if u["id"] != owner["id"] and u["id"] != res_post.get("userId"))

    cred = lambda u: {"username": u["username"], "password": u["password"]}
    return {"admin": admin, "owner": owner, "viewer": viewer, "res_post": res_post,
            "users": {"viewer": cred(viewer), "owner": cred(owner), "admin": cred(admin)}}


def build_spec(ent: dict, owner_snapshot: dict) -> dict:
    res_post = ent["res_post"]
    return {
        "target": BASE,
        "login_path": "/auth/login",
        "resource_path": "/auth/posts/{id}",
        "collection_path": "/auth/posts",
        "admin_listing_path": "/auth/users",
        "resource_id": res_post["id"],
        "resource_field_names": list(owner_snapshot.keys()),
        "owner_resource_snapshot": owner_snapshot,
        "users": ent["users"],
        "roles_note": ("DummyJSON users carry a role field (admin/moderator/user) "
                       "but the API enforces no role/ownership checks; the security "
                       "contract here is what a correct API SHOULD return."),
    }


def main() -> int:
    ent = derive_entities()
    spec_users = {"viewer": ent["users"]["viewer"], "owner": ent["users"]["owner"],
                  "admin": ent["users"]["admin"]}

    # provision tokens + fetch the owner's real resource snapshot via owner token
    tmp_spec = {"login_path": "/auth/login", "users": spec_users}
    tokens = authz_contract.provision_tokens(tmp_spec)
    res_id = ent["res_post"]["id"]
    code, text, owner_body = authz_contract.send("GET", f"/auth/posts/{res_id}", tokens["owner"])
    owner_snapshot = owner_body if isinstance(owner_body, dict) else dict(ent["res_post"])

    spec = build_spec(ent, owner_snapshot)
    spec_path = WORKSPACE / "data" / "authz" / "authz_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))

    matrix = authz_spec.reference_matrix(
        resource_field_names=spec["resource_field_names"],
        resource_path=spec["resource_path"], collection_path=spec["collection_path"],
        admin_listing_path=spec["admin_listing_path"], resource_id=str(res_id))

    gold_cases = []
    core_total = core_pass = 0
    for case in matrix:
        endpoint = case["endpoint"].replace("{id}", str(res_id))
        auth = authz_contract._auth_for(case, tokens)
        c, t, bj = authz_contract.send(case["method"], endpoint, auth)
        ev = authz_contract.evaluate(case, c, t, bj, owner_snapshot)
        row = {"sub_test": case["sub_test"], "requesting_role": case["requesting_role"],
               "method": case["method"], "endpoint": endpoint,
               "resource_owner": case["resource_owner"],
               "expected_code": case["expected_code"],
               "leakage": case["leakage"],
               "expect_resource_data": case["expect_resource_data"],
               "list_must_exclude": case["list_must_exclude"],
               "body_snippet": t[:200], **ev}
        gold_cases.append(row)
        (WORKSPACE / "data" / "authz" / "gold" / f"{case['sub_test']}.json").write_text(
            json.dumps(row, indent=2))
        if case["sub_test"] in authz_contract.CORE:
            core_total += 1
            core_pass += 1 if ev["pass"] else 0

    accuracy = round(100.0 * core_pass / core_total, 2) if core_total else 0.0
    gold = {"target": BASE, "resource_id": res_id,
            "entities": {"viewer": ent["viewer"]["username"],
                         "owner": ent["owner"]["username"],
                         "admin": ent["admin"]["username"],
                         "owner_role": ent["owner"]["role"], "admin_role": ent["admin"]["role"]},
            "access_control_accuracy_rate_pct": accuracy,
            "core_sub_tests": core_total, "core_passed": core_pass,
            "sub_tests": gold_cases}
    (WORKSPACE / "data" / "authz" / "gold.json").write_text(json.dumps(gold, indent=2))

    print(f"viewer={ent['viewer']['username']}  owner={ent['owner']['username']} "
          f"(post {res_id})  admin={ent['admin']['username']}")
    for c in gold_cases:
        flag = "PASS" if c["pass"] else "FAIL"
        print(f"  {c['sub_test']:22} {c['method']:6} exp={c['expected_code']} "
              f"act={c['actual_code']} exposed={c['data_exposed']} safe={c['leak_safe']}  {flag}")
    print(f"\nAccess Control Accuracy Rate (6 core) = {accuracy}%  "
          f"({core_pass}/{core_total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
