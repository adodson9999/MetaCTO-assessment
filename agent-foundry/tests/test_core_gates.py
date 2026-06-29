#!/usr/bin/env python3
"""Guarantees the Core-Requirements guardrails (G14 auth, G15 crud, G16 search, G17 postman) catch
regressions: a complete synthetic run passes every gate; removing a required scenario or the Postman
collection makes the matching gate FAIL.

Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_core_gates.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))

import guardrails as G

GOLD = json.loads((Path(__file__).resolve().parent / "core_requirements.gold.json").read_text())


def _write_cases(out_root: Path, agent: str, scenario_ids: list[str]) -> None:
    d = out_root / "TestCases" / agent
    d.mkdir(parents=True, exist_ok=True)
    cases = [{"test_case_id": f"TC-{i:03d}", "title_summary": sid, "preconditions": "x",
              "test_steps": ["1. do"], "test_data": {"scenario_id": sid}, "expected_result": "x",
              "actual_result": "x", "status": "Pass"} for i, sid in enumerate(scenario_ids, 1)]
    (d / "cases.json").write_text(json.dumps(cases))
    (d / "cases.md").write_text("# x")


def _write_postman(out_root: Path, folders=None) -> None:
    folders = folders or GOLD["postman_folders"]
    item = [{"name": f, "item": [{"name": f"{f} req",
             "request": {"method": "GET", "header": [], "url": {"raw": "{{base_url}}/x"}},
             "event": [{"listen": "test", "script": {"exec": ['pm.test("ok", function(){});']}}]}]}
            for f in folders]
    col = {"info": {"name": "x", "schema": ".../collection.json"}, "item": item,
           "variable": [{"key": k, "value": ""} for k in GOLD["postman_variables"]]}
    pm = out_root / "Postman"; pm.mkdir(parents=True, exist_ok=True)
    (pm / "collection.json").write_text(json.dumps(col))
    (pm / "environment.json").write_text(json.dumps({"values": []}))


def _complete(out_root: Path) -> None:
    for agent, ids in GOLD["required_scenarios"].items():
        _write_cases(out_root, agent, list(ids))
    _write_postman(out_root)


def test_complete_run_passes_all_gates():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _complete(out)
        for g in (G.g14_auth_lifecycle(out), G.g15_crud_products(out),
                  G.g16_search_coverage(out), G.g17_postman(out)):
            assert g["status"] == "PASS", f"{g['id']} should pass on a complete run: {g['detail']}"


def test_missing_auth_scenario_fails_g14():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _complete(out)
        partial = [s for s in GOLD["required_scenarios"]["test-authentication-flows"] if s != "AUTH-REFRESH-VALID"]
        _write_cases(out, "test-authentication-flows", partial)
        g = G.g14_auth_lifecycle(out)
        assert g["status"] == "FAIL" and "AUTH-REFRESH-VALID" in g["detail"], g


def test_missing_crud_and_search_scenarios_fail():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _complete(out)
        _write_cases(out, "verify-crud-operation-integrity",
                     [s for s in GOLD["required_scenarios"]["verify-crud-operation-integrity"] if s != "CRUD-DELETE"])
        _write_cases(out, "validate-search-and-filter-queries",
                     [s for s in GOLD["required_scenarios"]["validate-search-and-filter-queries"] if s != "SORT-ASC"])
        assert G.g15_crud_products(out)["status"] == "FAIL"
        assert G.g16_search_coverage(out)["status"] == "FAIL"


def test_postman_gate():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _complete(out)
        assert G.g17_postman(out)["status"] == "PASS"
        # remove the collection entirely
        (out / "Postman" / "collection.json").unlink()
        assert G.g17_postman(out)["status"] == "FAIL"
        # missing a required folder
        _write_postman(out, folders=["Authentication", "CRUD — Products", "Search & Filtering"])
        g = G.g17_postman(out)
        assert g["status"] == "FAIL" and "Error Handling" in g["detail"], g


def main() -> int:
    tests = [test_complete_run_passes_all_gates, test_missing_auth_scenario_fails_g14,
             test_missing_crud_and_search_scenarios_fail, test_postman_gate]
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
