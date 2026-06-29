#!/usr/bin/env python3
"""Deterministic unit tests for the Core-Requirements contract + builders (no network):

  * the scenario contract covers the gold floor for Auth / CRUD / Search & Filtering,
  * the assertion evaluator is correct for every assertion kind,
  * core_testcases emits exactly the 8-field schema with the required scenario_ids and
    correct Pass/Fail/Blocked mapping,
  * core_postman emits a 4-folder v2.1 collection where every request carries a pm.test
    script, the Login request captures {{token}}/{{refreshToken}}, protected requests send
    `Bearer {{token}}`, and the refresh request body uses {{refreshToken}}.

Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_core_requirements.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import core_requirements as CR
import core_testcases as CT
import core_postman as CP

GOLD = json.loads((Path(__file__).resolve().parent / "core_requirements.gold.json").read_text())


def _fake_results(all_pass=True):
    """Build executed-scenario records from the contract WITHOUT hitting the network."""
    out = []
    for sc in CR.SCENARIOS:
        passed = all_pass
        checks = [{"ok": passed, "desc": a["t"]} for a in sc["assertions"]]
        out.append({**sc, "resolved_path": sc["path"], "sent_body": sc.get("body"),
                    "sent_headers": {}, "actual_status": sc["expected_status"] if passed else 500,
                    "actual_body": {"message": "x"}, "error": "", "blocked": False,
                    "passed": passed, "checks": checks})
    return out


def test_contract_covers_gold_floor():
    ids_by_agent = {}
    for sc in CR.SCENARIOS:
        agent = CT.AGENT_OF_AREA.get(sc["area"])
        if agent:
            ids_by_agent.setdefault(agent, set()).add(sc["id"])
    for agent, required in GOLD["required_scenarios"].items():
        missing = set(required) - ids_by_agent.get(agent, set())
        assert not missing, f"{agent} contract missing required scenarios: {sorted(missing)}"


def test_assertion_evaluator():
    ok = lambda a, s, b: CR._check(a, s, b)[0]  # noqa: E731
    assert ok({"t": "status", "eq": 200}, 200, {})
    assert not ok({"t": "status", "eq": 200}, 404, {})
    assert ok({"t": "status", "in": [401, 403]}, 403, {})
    assert ok({"t": "has", "path": "accessToken"}, 200, {"accessToken": "x"})
    assert not ok({"t": "has", "path": "accessToken"}, 200, {})
    assert ok({"t": "eq", "path": "id", "val": 1}, 200, {"id": 1})
    assert ok({"t": "type", "path": "products", "is": "array"}, 200, {"products": []})
    assert ok({"t": "len_lte", "path": "products", "n": 5}, 200, {"products": [1, 2, 3]})
    assert not ok({"t": "len_lte", "path": "products", "n": 2}, 200, {"products": [1, 2, 3]})
    assert ok({"t": "contains", "path": "message", "sub": "not found"}, 404, {"message": "Product not found"})
    assert ok({"t": "each", "path": "products", "key": "category", "op": "eq", "val": "x"},
              200, {"products": [{"category": "x"}, {"category": "x"}]})
    assert not ok({"t": "each", "path": "products", "key": "category", "op": "eq", "val": "x"},
                  200, {"products": [{"category": "x"}, {"category": "y"}]})
    assert ok({"t": "subset_keys", "path": "products", "allowed": ["id", "title", "price"]},
              200, {"products": [{"id": 1, "title": "a"}]})
    assert not ok({"t": "subset_keys", "path": "products", "allowed": ["id", "title"]},
                  200, {"products": [{"id": 1, "extra": 9}]})
    assert ok({"t": "sorted", "path": "products", "key": "title", "order": "asc"},
              200, {"products": [{"title": "a"}, {"title": "b"}]})
    assert not ok({"t": "sorted", "path": "products", "key": "title", "order": "asc"},
                  200, {"products": [{"title": "b"}, {"title": "a"}]})


def test_testcases_schema_and_coverage():
    res = _fake_results(all_pass=True)
    by_agent = CT.to_testcases(res)
    fields = GOLD["testcase_fields"]
    for agent, required in GOLD["required_scenarios"].items():
        cases = by_agent[agent]
        for c in cases:
            assert list(c.keys()) == fields, f"{agent} case has wrong 8-field schema: {list(c.keys())}"
            assert c["status"] in GOLD["statuses"]
        present = {c["test_data"]["scenario_id"] for c in cases}
        assert set(required).issubset(present), f"{agent} testcases missing {set(required)-present}"
    # status mapping: fail + blocked
    res2 = _fake_results(all_pass=True)
    res2[0]["passed"] = False; res2[0]["checks"][0]["ok"] = False
    res2[1]["blocked"] = True; res2[1]["passed"] = False
    cases = CT.to_testcases(res2)["test-authentication-flows"]
    by_id = {c["test_data"]["scenario_id"]: c for c in cases}
    assert by_id[res2[0]["id"]]["status"] == "Fail"
    assert by_id[res2[1]["id"]]["status"] == "Blocked"


def test_postman_collection_structure():
    col, env = CP.build(_fake_results(all_pass=True))
    assert col["info"]["schema"].endswith("collection.json")
    folders = {f["name"]: f["item"] for f in col["item"]}
    for want in GOLD["postman_folders"]:
        assert want in folders, f"Postman missing folder {want}"
    assert {v["key"] for v in col["variable"]} == set(GOLD["postman_variables"])
    assert {v["key"] for v in env["values"]} == set(GOLD["postman_variables"])
    reqs = [it for f in col["item"] for it in f["item"]]
    for it in reqs:
        exec_lines = "\n".join(it["event"][0]["script"]["exec"])
        assert "pm.test" in exec_lines, f"request {it['name']} has no pm.test"
    # login captures token + refreshToken
    login = next(it for it in reqs if it["name"].startswith("AUTH-LOGIN-VALID"))
    login_js = "\n".join(login["event"][0]["script"]["exec"])
    for var in GOLD["login_captures"]:
        assert f'pm.collectionVariables.set("{var}"' in login_js, f"login does not capture {var}"
    # protected /auth/me valid uses Bearer {{token}}
    me = next(it for it in reqs if it["name"].startswith("AUTH-ME-VALID"))
    assert any(h.get("value") == "Bearer {{token}}" for h in me["request"]["header"])
    # refresh body uses {{refreshToken}}
    refresh = next(it for it in reqs if it["name"].startswith("AUTH-REFRESH-VALID"))
    assert "{{refreshToken}}" in refresh["request"]["body"]["raw"]


def main() -> int:
    tests = [test_contract_covers_gold_floor, test_assertion_evaluator,
             test_testcases_schema_and_coverage, test_postman_collection_structure]
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
