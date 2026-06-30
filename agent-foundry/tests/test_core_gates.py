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
import core_requirements as CR
import core_testcases as CT
import core_postman as CP

GOLD = json.loads((Path(__file__).resolve().parent / "core_requirements.gold.json").read_text())


def _fake_results():
    """Executed scenarios (no network) so the real builders produce an aligned TestCases+Postman pair."""
    return [{**sc, "resolved_path": sc["path"], "sent_body": sc.get("body"), "sent_headers": {},
             "actual_status": sc["expected_status"], "actual_body": {}, "error": "", "blocked": False,
             "passed": True, "checks": [{"ok": True, "desc": a["t"]} for a in sc["assertions"]]}
            for sc in CR.SCENARIOS]


def _write_aligned(out_root: Path) -> None:
    """Write TestCases/<agent>/cases.json + Postman/collection.json from the SAME results (aligned)."""
    res = _fake_results()
    for agent, cases in CT.to_testcases(res).items():
        d = out_root / "TestCases" / agent
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps(cases))
        (d / "cases.md").write_text("# x")
    col, env = CP.build(res)
    pm = out_root / "Postman"
    pm.mkdir(parents=True, exist_ok=True)
    (pm / "collection.json").write_text(json.dumps(col))
    (pm / "environment.json").write_text(json.dumps(env))


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
        # missing a required agent folder
        _write_postman(out, folders=["test-authentication-flows", "verify-crud-operation-integrity"])
        g = G.g17_postman(out)
        assert g["status"] == "FAIL" and "validate-search-and-filter-queries" in g["detail"], g


def _write_full(out_root: Path):
    """Aligned TestCases (core + one non-core API agent) + a build_full collection. Returns the
    non-core agent's API-call test_case_ids that must be covered."""
    res = _fake_results()
    for agent, cases in CT.to_testcases(res).items():
        d = out_root / "TestCases" / agent
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps(cases))
    api = out_root / "TestCases" / "test-pagination-behavior"
    api.mkdir(parents=True, exist_ok=True)
    api_cases = [
        {"test_case_id": "TC-PAGE-001", "title_summary": "Page1 returns 200", "preconditions": "x",
         "test_steps": ["1. Send GET /products to http://localhost:8899."], "test_data": {},
         "expected_result": "The API returns 200.", "actual_result": "x", "status": "Pass"},
        {"test_case_id": "TC-PAGE-002", "title_summary": "generic probe", "preconditions": "x",
         "test_steps": ["1. Send GET  to http://localhost:8899."], "test_data": {},  # not an API call
         "expected_result": "The API returns 200.", "actual_result": "x", "status": "Pass"}]
    (api / "cases.json").write_text(json.dumps(api_cases))
    col, env = CP.build_full(out_root, res)
    pm = out_root / "Postman"; pm.mkdir(parents=True, exist_ok=True)
    (pm / "collection.json").write_text(json.dumps(col))
    (pm / "environment.json").write_text(json.dumps(env))
    return {"TC-PAGE-001"}   # the only API-call case in the non-core agent (TC-PAGE-002 has no path)


def test_g19_postman_coverage():
    """G19: every API-call test case is in the collection; the no-path case is NOT required; and
    dropping a required request makes G19 FAIL."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _write_full(out)
        assert G.g19_postman_coverage(out)["status"] == "PASS", G.g19_postman_coverage(out)["detail"]
        # drop the required pagination request from the collection
        col = json.loads((out / "Postman" / "collection.json").read_text())
        for f in col["item"]:
            if f["name"] == "test-pagination-behavior":
                f["item"] = [it for it in f["item"] if not it["name"].startswith("TC-PAGE-001")]
        (out / "Postman" / "collection.json").write_text(json.dumps(col))
        g = G.g19_postman_coverage(out)
        assert g["status"] == "FAIL" and "TC-PAGE-001" in g["detail"], g


def test_g18_postman_testcase_alignment():
    """G18: an aligned collection passes; a wrong request name OR an id with no matching test case fails."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-06-29" / "12-00-00"
        _write_aligned(out)
        assert G.g18_postman_testcase_alignment(out)["status"] == "PASS", \
            G.g18_postman_testcase_alignment(out)["detail"]
        # 1) break the naming convention
        col = json.loads((out / "Postman" / "collection.json").read_text())
        good_name = col["item"][0]["item"][0]["name"]
        col["item"][0]["item"][0]["name"] = "BOGUS REQUEST NAME"
        (out / "Postman" / "collection.json").write_text(json.dumps(col))
        g = G.g18_postman_testcase_alignment(out)
        assert g["status"] == "FAIL" and "BOGUS" in g["detail"], g
        # 2) valid naming but an id that has no matching test case
        col["item"][0]["item"][0]["name"] = "TC-AUTH-999 — " + good_name.split(" — ", 1)[1]
        (out / "Postman" / "collection.json").write_text(json.dumps(col))
        g = G.g18_postman_testcase_alignment(out)
        assert g["status"] == "FAIL" and "TC-AUTH-999" in g["detail"], g


def main() -> int:
    tests = [test_complete_run_passes_all_gates, test_missing_auth_scenario_fails_g14,
             test_missing_crud_and_search_scenarios_fail, test_postman_gate,
             test_g18_postman_testcase_alignment, test_g19_postman_coverage]
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
