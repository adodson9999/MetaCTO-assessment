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


def test_g20_deliverable_separation_pass():
    """G20: a complete tree (TestCases/ + Postman/collection.json) with BugReport agents that all
    have TestCases entries PASSES the separation gate."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        _complete(out)   # writes TestCases/<agent>/ for every required agent + Postman/
        # a BugReport whose agent also has a TestCases entry is allowed
        br = out / "BugReport" / "test-authentication-flows"
        br.mkdir(parents=True, exist_ok=True)
        (br / "cases.json").write_text(json.dumps([{"test_case_id": "TC-AUTH-007"}]))
        (br / "cases.md").write_text("# bug")
        g = G.g20_deliverable_separation(out)
        assert g["status"] == "PASS", f"G20 should pass on a separated tree: {g['detail']}"


def test_g20_missing_testcases_fails():
    """G20: Postman present but NO TestCases/ (test cases only under runs/ or the bug folder) FAILS."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        _write_postman(out)   # Postman only, no TestCases/
        g = G.g20_deliverable_separation(out)
        assert g["status"] == "FAIL" and "TestCases" in g["detail"], g


def test_g20_missing_postman_fails():
    """G20: TestCases present but NO Postman/collection.json FAILS."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        for agent, ids in GOLD["required_scenarios"].items():
            _write_cases(out, agent, list(ids))   # TestCases only, no Postman/
        g = G.g20_deliverable_separation(out)
        assert g["status"] == "FAIL" and "Postman" in g["detail"], g


def test_g20_bug_agent_without_testcase_fails():
    """G20: an agent that appears under BugReport/ but NOT under TestCases/ FAILS — test cases can
    never live only in the bug folder (the exact 'mixed into bug report' regression the user hit)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        _complete(out)
        br = out / "BugReport" / "verify-caching-headers"   # no TestCases/verify-caching-headers
        br.mkdir(parents=True, exist_ok=True)
        (br / "cases.json").write_text(json.dumps([{"test_case_id": "TC-CACHE-001"}]))
        (br / "cases.md").write_text("# bug")
        g = G.g20_deliverable_separation(out)
        assert g["status"] == "FAIL" and "verify-caching-headers" in g["detail"], g


def test_auth_me_malformed_regression_locked():
    """Regression lock for the missed bug: AUTH-ME-MALFORMED (GET /auth/me with a bad token, expect
    401/403) MUST remain a deterministic Core-Requirements scenario, and G14 MUST fail if it is
    dropped from the auth agent's TestCases. This is the coverage the full-orchestration path lost
    when it skipped the Core-Requirements contract and the auth agent's LLM producer timed out."""
    ids = {sc["id"] for sc in CR.SCENARIOS if sc["area"] == "Authentication"}
    assert "AUTH-ME-MALFORMED" in ids, "AUTH-ME-MALFORMED must stay in the deterministic contract"
    assert "AUTH-ME-MALFORMED" in G._AUTH_REQUIRED, "G14 must require AUTH-ME-MALFORMED"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        _complete(out)
        assert G.g14_auth_lifecycle(out)["status"] == "PASS"
        partial = [s for s in GOLD["required_scenarios"]["test-authentication-flows"]
                   if s != "AUTH-ME-MALFORMED"]
        _write_cases(out, "test-authentication-flows", partial)
        g = G.g14_auth_lifecycle(out)
        assert g["status"] == "FAIL" and "AUTH-ME-MALFORMED" in g["detail"], g


def test_g13_accepts_self_contained_bugreport():
    """G13/G20: a BugReport with per-agent System-A reports (verified_bugs/BUG-*.json) PLUS embedded
    artifacts (screenshots/recordings/logs) and index files passes — that is the deliverable's
    self-contained bug structure. A bug agent missing from TestCases still fails G20."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        _complete(out)   # TestCases for all required agents + Postman
        agent = "test-authentication-flows"   # has a TestCases entry from _complete
        vb = out / "BugReport" / agent / "verified_bugs"
        vb.mkdir(parents=True, exist_ok=True)
        (vb / "BUG-0001.json").write_text(json.dumps({"bug_id": "BUG-0001", "agent_name": agent}))
        for sub in ("screenshots", "recordings", "logs"):
            d = out / "BugReport" / agent / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / "BUG-0001.x").write_text("artifact")
        # G13 scans all of results/ (WS), so validate its section helper directly on this tree.
        assert G._check_section(out / "BugReport") == [], G._check_section(out / "BugReport")
        assert G.g20_deliverable_separation(out)["status"] == "PASS", \
            G.g20_deliverable_separation(out)["detail"]
        # a bug agent with no TestCases entry -> G20 FAIL
        orphan = out / "BugReport" / "verify-caching-headers" / "verified_bugs"
        orphan.mkdir(parents=True, exist_ok=True)
        (orphan / "BUG-0002.json").write_text(json.dumps({"bug_id": "BUG-0002"}))
        g = G.g20_deliverable_separation(out)
        assert g["status"] == "FAIL" and "verify-caching-headers" in g["detail"], g


def test_g21_hard_fails_on_silent_empty():
    """G21: an agent classified EMPTY (produced no usable output on a SUPPORTED capability) is a HARD
    fail — the silent-miss that let the auth agent skip AUTH-ME-MALFORMED and still be marked PASS."""
    clean = [{"agent": "a", "outcome": "PASS"}, {"agent": "b", "outcome": "ENV-LIMITED"}]
    assert G.g21_no_silent_empty(clean)["status"] == "PASS"
    dirty = clean + [{"agent": "check-authorization-rules", "outcome": "EMPTY"}]
    g = G.g21_no_silent_empty(dirty)
    assert g["status"] == "FAIL" and g["hard"] and "check-authorization-rules" in g["detail"], g


def test_classify_downgrades_empty_on_unsupported_capability():
    """classify(): an agent that produces no cases is ENV-LIMITED (not EMPTY) IFF its mapped capability
    is declared unsupported — so absent-feature 0%s never trip G21, but a real model failure still does."""
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / "api-tester-widget-agent.json").write_text(json.dumps(
            {"agent": "api-tester-widget-agent", "produced_cases": 0}))
        caps_unsup = {"pass_threshold_pct": 70.0, "partial_threshold_pct": 30.0,
                      "capabilities": {"widgets": {"supported": False}},
                      "agent_capability_map": {"widget-agent": ["widgets"]}}
        assert G.classify(rd, "widget-agent", caps_unsup)["outcome"] == "ENV-LIMITED"
        caps_sup = {"pass_threshold_pct": 70.0, "partial_threshold_pct": 30.0,
                    "capabilities": {"widgets": {"supported": True}},
                    "agent_capability_map": {"widget-agent": ["widgets"]}}
        assert G.classify(rd, "widget-agent", caps_sup)["outcome"] == "EMPTY"


def test_tidy_results_deletes_working_data():
    """tidy_results deletes the run's transient working data (results/runs/<id>, legacy bug-reports,
    registry strays) as soon as the deliverable is built, leaving ONLY dated deliverables + _global."""
    import build_deliverables as BD
    with tempfile.TemporaryDirectory() as td:
        results = Path(td) / "results"
        (results / "runs" / "RUN-X" / "agents").mkdir(parents=True)
        (results / "runs" / "RUN-X" / "state.json").write_text("{}")
        (results / "bug-reports").mkdir()
        (results / "test-case-registry.json").write_text("{}")
        (results / "test-case-registry-summary.json").write_text("{}")
        (results / "2026-07-02" / "00-01-38" / "TestCases").mkdir(parents=True)
        (results / "_global").mkdir()
        orig = BD.WS
        try:
            BD.WS = Path(td)
            res = BD.tidy_results("RUN-X")
        finally:
            BD.WS = orig
        assert "runs/RUN-X" in res["removed"] and "bug-reports" in res["removed"]
        assert res["remaining_strays"] == []
        assert sorted(p.name for p in results.iterdir()) == ["2026-07-02", "_global"]


def test_g23_results_clean():
    """G23 (HARD): results/ with only <date>/ + _global PASSES; a leftover runs/ or bug-reports/ FAILS."""
    import guardrails as GG
    with tempfile.TemporaryDirectory() as td:
        results = Path(td) / "results"
        (results / "2026-07-02" / "00-01-38").mkdir(parents=True)
        (results / "_global").mkdir()
        orig = GG.WS
        try:
            GG.WS = Path(td)
            assert GG.g23_results_clean()["status"] == "PASS"
            (results / "runs").mkdir()
            g = GG.g23_results_clean()
            assert g["status"] == "FAIL" and g["hard"] and "runs" in g["detail"], g
        finally:
            GG.WS = orig


def test_ci_regression_suite_build_excludes_ambiguous_cases():
    """The CI regression suite carries ONLY passing, unambiguously-replayable cases grouped by agent:
    a concrete API-call Pass case is included; a Fail case, an unresolved template path (/carts/{id}),
    and a no-path (unexecutable) case are all excluded. Expected statuses come through as a set."""
    import ci_regression_suite as CRS
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        d = out / "TestCases" / "test-pagination-behavior"
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps([
            {"test_case_id": "TC-1", "status": "Pass", "expected_result": "The API returns 200.",
             "test_steps": ["1. Send GET /products to the API."],
             "test_data": {"method": "GET", "path": "/products", "query": {}, "body": None}},
            {"test_case_id": "TC-2", "status": "Fail", "expected_result": "200",
             "test_data": {"method": "GET", "path": "/products"}},
            {"test_case_id": "TC-3", "status": "Pass", "expected_result": "400",
             "test_data": {"method": "PUT", "path": "/carts/{id}"}},          # template -> excluded
            {"test_case_id": "TC-4", "status": "Pass", "expected_result": "200",
             "test_steps": ["1. Send GET  to the API."], "test_data": {"note": "no path"}},
            {"test_case_id": "TC-5", "status": "Pass", "expected_result": "status in [401, 403]",
             "test_data": {"method": "GET", "path": "/auth/me", "auth": "bad"}},
        ]))
        orig_dir, orig_ws = CRS.SUITE_DIR, CRS.WS
        try:
            CRS.SUITE_DIR = Path(td) / "suite"
            m = CRS.build(out)
            suite = json.loads((CRS.SUITE_DIR / "test-pagination-behavior" / "cases.json").read_text())
        finally:
            CRS.SUITE_DIR, CRS.WS = orig_dir, orig_ws
        ids = {c["test_case_id"] for c in suite}
        assert ids == {"TC-1", "TC-5"}, ids            # Fail, template, no-path excluded
        tc5 = next(c for c in suite if c["test_case_id"] == "TC-5")
        assert tc5["expected_statuses"] == [401, 403] and tc5["auth"] == "bad"
        assert m["total_cases"] == 2


def test_g22_forbids_bug_index_files():
    """G22 (HARD): no *-index.json / index.json may exist under BugReport/. Clean tree PASSES;
    planting verified-index.json, unverified-index.json, or index.json FAILS."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        vb = out / "BugReport" / "test-pagination-behavior" / "verified_bugs"
        vb.mkdir(parents=True, exist_ok=True)
        (vb / "BUG-0001.json").write_text(json.dumps({"bug_id": "BUG-0001"}))
        assert G.g22_no_bug_index_files(out)["status"] == "PASS"
        for name in ("verified-index.json", "unverified-index.json", "index.json"):
            f = out / "BugReport" / name
            f.write_text("{}")
            g = G.g22_no_bug_index_files(out)
            assert g["status"] == "FAIL" and g["hard"] and name in g["detail"], (name, g)
            f.unlink()
        # also caught nested under an agent folder
        (out / "BugReport" / "test-pagination-behavior" / "verified-index.json").write_text("{}")
        assert G.g22_no_bug_index_files(out)["status"] == "FAIL"


def test_unverified_bugs_survive_finalizer_rebuild():
    """Regression lock: the finalizer rebuilds BugReport/ from scratch, but the categorized
    unverified bugs (missing-docs → VULN/BIZ/SW written by adjudicate) MUST survive that rebuild and
    land at the top-level BugReport/unverified/{category}/ tree. No index file is written (G22).
    This is the exact drop the rmtree(BugReport) once caused."""
    import build_deliverables as BD
    with tempfile.TemporaryDirectory() as td:
        # a source tree as adjudicate leaves it: BugReport/unverified/{category}/
        src = Path(td) / "src"
        vb = src / "unverified" / "vulnerability"
        vb.mkdir(parents=True, exist_ok=True)
        (vb / "VULN-RUN-0001.json").write_text(json.dumps(
            {"bug_id": "VULN-RUN-0001", "category": "vulnerability",
             "finding_agent": "test-pagination-behavior", "documentation_cited": False}))
        # snapshot (survives rmtree) then restore into a freshly-rebuilt tree
        snap = BD._snapshot_unverified(src)
        tree = Path(td) / "BugReport"
        tree.mkdir()
        res = BD._restore_unverified(tree, snap)
        assert (tree / "unverified" / "vulnerability" / "VULN-RUN-0001.json").is_file()
        # no index file is written (G22)
        assert not list(tree.glob("*index.json"))
        assert res["reports"] == 1 and res["by_category"].get("vulnerability") == 1


def test_standard_bug_report_format():
    """Every materialized bug carries the eight standard defect fields (id, title/summary,
    description in When-I/I-expect/but-I-get form, steps to reproduce, actual-vs-expected,
    severity+priority with their distinct meanings, environment, attachments) and its .md renders
    them — sourced from the agent's linked failed test case."""
    import build_deliverables as BD
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "2026-07-02" / "00-01-38"
        d = out / "TestCases" / "test-authentication-flows"
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps([{
            "test_case_id": "TC-AUTH-007", "title_summary": "GET /auth/me bad token rejected",
            "test_steps": ["1. Send GET /auth/me with a malformed token.", "2. Assert 401/403."],
            "test_data": {"method": "GET", "path": "/auth/me"},
            "expected_result": "status in [401, 403]", "actual_result": "HTTP 500", "status": "Fail"}]))
        raw = {"bug_id": "BUG-0001", "agent_name": "api-tester-test-authentication-flows",
               "severity": "CRITICAL", "priority": "P1", "title": "[agent] metric=0%"}
        r = BD._standard_report(raw, "test-authentication-flows", out, "RUN-x",
                                "http://localhost:8899", "2026-07-02", "00-01-38",
                                {"screenshot": "BugReport/x/screenshots/BUG-0001.txt"})
        for f in ("id", "title_summary", "description", "steps_to_reproduce", "expected_result",
                  "actual_result", "severity", "priority", "environment", "attachments"):
            assert f in r and r[f], f"missing standard field: {f}"
        assert "When I" in r["description"] and "I expect" in r["description"] and "but I get" in r["description"]
        assert r["severity"] == "CRITICAL" and r["priority"] == "P1"
        assert r["environment"]["endpoint"] == "GET /auth/me"
        assert r["severity_impact"] and r["priority_urgency"]   # distinct meanings surfaced
        md = BD._bug_markdown(r)
        for heading in ("## Description", "## Steps to Reproduce", "## Actual vs. Expected",
                        "## Severity & Priority", "## Environment", "## Attachments"):
            assert heading in md, f"markdown missing section: {heading}"


def main() -> int:
    tests = [test_complete_run_passes_all_gates, test_missing_auth_scenario_fails_g14,
             test_missing_crud_and_search_scenarios_fail, test_postman_gate,
             test_g18_postman_testcase_alignment, test_g19_postman_coverage,
             test_g20_deliverable_separation_pass, test_g20_missing_testcases_fails,
             test_g20_missing_postman_fails, test_g20_bug_agent_without_testcase_fails,
             test_auth_me_malformed_regression_locked, test_g21_hard_fails_on_silent_empty,
             test_classify_downgrades_empty_on_unsupported_capability,
             test_g13_accepts_self_contained_bugreport, test_standard_bug_report_format,
             test_unverified_bugs_survive_finalizer_rebuild, test_g22_forbids_bug_index_files,
             test_tidy_results_deletes_working_data, test_g23_results_clean,
             test_ci_regression_suite_build_excludes_ambiguous_cases]
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
