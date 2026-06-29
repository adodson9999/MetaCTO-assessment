# Used by: shared — converts core_requirements results into the 8-field TestCases for the three
# core agents (test-authentication-flows, verify-crud-operation-integrity,
# validate-search-and-filter-queries). Consumed by run_pipeline; asserted by guardrails G14–G16.
"""Render executed Core-Requirements scenarios into the canonical 8-field test-case schema,
grouped by the agent that owns each area. One scenario -> one test case.

8 fields (exact): test_case_id, title_summary, preconditions, test_steps, test_data,
expected_result, actual_result, status (Pass | Fail | Blocked).
"""
from __future__ import annotations

import json

PREFIX = {"Authentication": "AUTH", "CRUD": "CRUD", "Search & Filtering": "SEARCH",
          "Error Handling": "ERR"}
AGENT_OF_AREA = {"Authentication": "test-authentication-flows",
                 "CRUD": "verify-crud-operation-integrity",
                 "Search & Filtering": "validate-search-and-filter-queries"}
AUTH_DESC = {"bearer": "with a valid Bearer token", "bad": "with a malformed Bearer token",
             "expired": "with an expired Bearer token", "revoked": "with a revoked (post-logout) token",
             "refresh": "with the captured refreshToken"}


def _steps(sc: dict) -> list[str]:
    auth = sc.get("auth")
    where = AUTH_DESC.get(auth, "with no Authorization header" if sc["area"] == "Authentication"
                          and sc["path"] == "/auth/me" else "")
    line = f"1. Send {sc['method']} {sc['resolved_path']}"
    if where:
        line += f" {where}"
    steps = [line + "."]
    n = 2
    if sc.get("sent_body"):
        steps.append(f"{n}. Request body: {json.dumps(sc['sent_body'])}."); n += 1
    for c in sc["checks"]:
        steps.append(f"{n}. Assert {c['desc']}."); n += 1
    return steps


def _expected(sc: dict) -> str:
    return "; ".join(c["desc"] for c in sc["checks"]) + "." if sc["checks"] else f"HTTP {sc['expected_status']}."


def _actual(sc: dict) -> str:
    if sc["blocked"]:
        return f"Target unreachable — {sc['error']}."
    fails = [c["desc"] for c in sc["checks"] if not c["ok"]]
    body = sc["actual_body"]
    snippet = ""
    if isinstance(body, dict):
        msg = body.get("message")
        snippet = f" message='{msg}'" if msg else ""
    head = f"HTTP {sc['actual_status']}.{snippet}"
    return head if not fails else head + " FAILED: " + "; ".join(fails) + "."


def _status(sc: dict) -> str:
    return "Blocked" if sc["blocked"] else ("Pass" if sc["passed"] else "Fail")


def to_testcases(results: list[dict]) -> dict:
    """{agent: [8-field case, ...]} for the three core agents (areas Auth/CRUD/Search)."""
    by_agent: dict[str, list] = {}
    counters: dict[str, int] = {}
    for sc in results:
        agent = AGENT_OF_AREA.get(sc["area"])
        if not agent:
            continue
        counters[agent] = counters.get(agent, 0) + 1
        tc_id = f"TC-{PREFIX[sc['area']]}-{counters[agent]:03d}"
        by_agent.setdefault(agent, []).append({
            "test_case_id": tc_id,
            "title_summary": sc["title"],
            "preconditions": sc.get("precondition", "Target reachable; no special prior state required."),
            "test_steps": _steps(sc),
            "test_data": {"scenario_id": sc["id"], "method": sc["method"], "path": sc["path"],
                          "query": sc.get("query") or {}, "body": sc.get("sent_body"),
                          "auth": sc.get("auth"), **({"note": sc["note"]} if sc.get("note") else {})},
            "expected_result": _expected(sc),
            "actual_result": _actual(sc),
            "status": _status(sc),
        })
    return by_agent


def to_markdown(agent: str, cases: list[dict]) -> str:
    p = sum(c["status"] == "Pass" for c in cases)
    f = sum(c["status"] == "Fail" for c in cases)
    b = sum(c["status"] == "Blocked" for c in cases)
    out = [f"# Test Cases — {agent}", "", f"Total: {len(cases)} | Pass: {p} | Fail: {f} | Blocked: {b}", ""]
    for c in cases:
        out += [f"## {c['test_case_id']}",
                f"- **Title/Summary:** {c['title_summary']}",
                f"- **Preconditions:** {c['preconditions']}",
                "- **Test Steps:**", *[f"  {s}" for s in c["test_steps"]],
                f"- **Test Data:** `{json.dumps(c['test_data'])}`",
                f"- **Expected Result:** {c['expected_result']}",
                f"- **Actual Result:** {c['actual_result']}",
                f"- **Status:** {c['status']}", ""]
    return "\n".join(out)
