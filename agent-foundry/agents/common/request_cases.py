# Used by: shared — folds each agent's RECORDED API calls (request_recorder output) into that
# agent's TestCases as request-derived 8-field cases, so every unique call the agent made becomes a
# test case (and therefore a Postman request via build_full). Per-agent: dedup never crosses agents.
"""Augment non-core agents' cases.json with their recorded API calls.

For each non-core agent, every UNIQUE request it sent (method+path+query+body — deduped per agent by
request_recorder) that isn't already an exact existing test case is appended as a request-derived
8-field case. Existing semantic cases are kept untouched; numbering continues from the agent's max.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import format_test_cases as F
import core_postman as CP
import request_recorder as RR


def _signature(method, path, query: dict, body) -> tuple:
    qs = tuple(sorted((str(k), str(v)) for k, v in (query or {}).items()))
    return (method, path, qs, json.dumps(body, sort_keys=True) if body is not None else "")


def _existing_signatures(cases: list) -> set:
    sigs = set()
    for c in cases:
        pr = CP._parse_request(c)
        if pr:
            method, path, query, body = pr
            sigs.add(_signature(method, path, query, body))
    return sigs


def _next_num(cases: list) -> int:
    nums = [int(m.group(1)) for c in cases
            if (m := re.search(r"-(\d+)$", c.get("test_case_id", "")))]
    return max(nums, default=0)


def _req_case(prefix: str, n: int, r: dict) -> dict:
    method, path = r["method"], r["path"]
    query, body, status = r.get("query") or {}, r.get("body"), r.get("status")
    qs = ("?" + "&".join(f"{k}={v}" for k, v in query.items())) if query else ""
    bodytxt = f" with body {json.dumps(body)}" if body is not None else ""
    exp = f"The API returns {status}." if status is not None else "A response is received."
    act = f"The API returned {status}." if status is not None else "No response (target unreachable)."
    return {
        "test_case_id": f"TC-{prefix}-{n:03d}",
        "title_summary": f"Recorded API call: {method} {path}",
        "preconditions": "API target reachable.",
        "test_steps": [f"1. Send {method} {path}{qs}{bodytxt} to the API target.",
                       "2. Read the HTTP response status code and body.",
                       "3. Compare the observed result to the expected result."],
        "test_data": {"method": method, "path": path, "query": query, "body": body,
                      "source": "recorded-request"},
        "expected_result": exp,
        "actual_result": act,
        "status": "Pass" if status is not None else "Blocked",
    }


def _markdown(agent: str, cases: list) -> str:
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


def augment(out_root, requests_dir, core_agents: set) -> dict:
    """For every non-core agent, append request-derived cases for its recorded calls not already
    present. Rewrites cases.json + cases.md. Returns {agent: appended_count}."""
    out_root, requests_dir = Path(out_root), Path(requests_dir)
    tc_root = out_root / "TestCases"
    summary: dict = {}
    if not tc_root.is_dir():
        return summary
    for agent_dir in sorted(p for p in tc_root.iterdir() if p.is_dir()):
        agent = agent_dir.name
        if agent in core_agents:
            continue
        rf = requests_dir / f"{agent}.json"
        if not rf.exists():
            continue
        try:
            cases = json.loads((agent_dir / "cases.json").read_text())
            reqs = json.loads(rf.read_text()).get("requests", [])
        except (OSError, json.JSONDecodeError):
            continue
        seen = _existing_signatures(cases)
        n, prefix, appended = _next_num(cases), F.code(agent), []
        for r in reqs:
            if RR.path_excluded(r.get("path", "")):    # skip LLM-backend / telemetry calls
                continue
            sig = _signature(r["method"], r["path"], r.get("query") or {}, r.get("body"))
            if sig in seen:
                continue
            seen.add(sig)
            n += 1
            appended.append(_req_case(prefix, n, r))
        if appended:
            cases.extend(appended)
            (agent_dir / "cases.json").write_text(json.dumps(cases, indent=2))
            (agent_dir / "cases.md").write_text(_markdown(agent, cases))
            summary[agent] = len(appended)
    return summary
