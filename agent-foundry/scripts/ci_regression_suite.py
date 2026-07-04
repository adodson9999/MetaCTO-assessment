#!/usr/bin/env python3
# Used by: the CI regression job (.github/workflows/agent-ci.yml) + build_deliverables finalize.
"""CI regression suite — the passing test cases, grouped by the agent that created them.

Two halves:

  build(out_root)  — refresh agent-foundry/ci/regression-suite/<agent>/cases.json from a run's
                     deliverable TestCases. A case qualifies ONLY if it PASSED and is a concrete,
                     executable API call (its steps contain 'Send <METHOD> /path'); vague no-path
                     rows are excluded so there is nothing to guess. Each emitted case is fully
                     explicit: method, path, query, body, expected_status, expected_result, title.
                     Unverified / missing-docs cases never appear (they are not in TestCases).

  run(target)      — replay every suite case against the live target, DETERMINISTICALLY (stdlib
                     HTTP, no model, no interpretation), and report each test's result:
                       [PASS|FAIL] <agent> <tc_id>  <METHOD path>  expected=<code> actual=<code>
                     Exit 0 iff every test passed. This is the "leave no room for guessing" runner —
                     the ollama backend is used elsewhere for agent steps; the assertions here are
                     exact so a test can only pass or fail, never be misread.

Refresh semantics (per decision): the suite reflects the LATEST run's passing set. Agents with no
passing executable case get no folder.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))

from core_postman import _parse_request  # noqa: E402  — single source of "is this an API call"

SUITE_DIR = WS / "ci" / "regression-suite"
_STATUS_RE = re.compile(r"\b([1-5]\d{2})\b")


def _expected_statuses(case: dict) -> list[int]:
    """ALL acceptable status codes named in the expected result (e.g. 'status in [401, 403]' -> both;
    '200 or 201' -> both). A test passes if the observed code is any of them. Empty list = the case
    names no code, so the runner only checks reachability."""
    seen: list[int] = []
    for m in _STATUS_RE.finditer(case.get("expected_result", "")):
        code = int(m.group(1))
        if code not in seen:
            seen.append(code)
    return seen


def _explicit_request(case: dict):
    """Return the FULL request (method, path, query, body, auth) with no ambiguity. Prefers the
    case's test_data (which carries body + the auth flag needed to reproduce the exact call), and
    falls back to the parsed 'Send <METHOD> /path' step. None if the case is not a concrete call."""
    td = case.get("test_data") or {}
    if td.get("method") and td.get("path"):
        return {"method": td["method"], "path": td["path"], "query": td.get("query") or {},
                "body": td.get("body"), "auth": td.get("auth")}
    parsed = _parse_request(case)
    if parsed is None:
        return None
    method, path, query, body = parsed
    return {"method": method, "path": path, "query": query, "body": body, "auth": None}


def build(out_root: Path) -> dict:
    """Refresh the regression suite from out_root/TestCases. Returns {agents, total, by_agent}."""
    import shutil
    tc_root = out_root / "TestCases"
    if SUITE_DIR.exists():
        shutil.rmtree(SUITE_DIR)
    by_agent: dict = {}
    for agent_dir in sorted(p for p in (tc_root.iterdir() if tc_root.is_dir() else []) if p.is_dir()):
        agent = agent_dir.name
        try:
            cases = json.loads((agent_dir / "cases.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        suite: list = []
        for c in cases:
            if c.get("status") != "Pass":
                continue
            req = _explicit_request(c)
            if req is None:               # not a concrete API call -> excluded (no guessing)
                continue
            if "{" in req["path"]:        # unresolved path template (e.g. /carts/{id}) -> ambiguous
                continue
            suite.append({
                "test_case_id": c.get("test_case_id"),
                "agent": agent,
                "title_summary": c.get("title_summary"),
                "method": req["method"], "path": req["path"], "query": req["query"],
                "body": req["body"], "auth": req["auth"],
                "expected_statuses": _expected_statuses(c),
                "expected_result": c.get("expected_result"),
            })
        if suite:
            d = SUITE_DIR / agent
            d.mkdir(parents=True, exist_ok=True)
            (d / "cases.json").write_text(json.dumps(suite, indent=2))
            by_agent[agent] = len(suite)
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_from": str(out_root.relative_to(WS)) if str(out_root).startswith(str(WS)) else str(out_root),
                "policy": "refresh-each-run", "agents": len(by_agent),
                "total_cases": sum(by_agent.values()), "by_agent": by_agent}
    (SUITE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _auth_context(target: str) -> dict:
    """Log in once with the documented valid credentials and capture the access + refresh tokens,
    so cases that need a Bearer token are replayed with a real one (not a guess)."""
    import core_requirements as CR
    try:
        status, body, _ = CR._request(target, "POST", "/auth/login", body=CR.VALID_CREDS)
        if status == 200 and isinstance(body, dict):
            return {"token": body.get("accessToken", ""), "refreshToken": body.get("refreshToken", "")}
    except Exception:  # noqa: BLE001
        pass
    return {"token": "", "refreshToken": ""}


def _do_request(target: str, case: dict, ctx: dict):
    """Send the case's exact request — body + resolved auth header — and return (status, error).
    Auth + refresh-token injection reuse the Core-Requirements primitives so the call is faithful."""
    import core_requirements as CR
    headers = CR._auth_headers(case.get("auth"), ctx, target)
    body = case.get("body")
    # A valid-refresh case carries a refreshToken in its body — swap in the freshly-captured one.
    # A negative refresh case (no refreshToken key, e.g. body {}) is left untouched so it still 4xx's.
    if case["path"].endswith("/auth/refresh") and isinstance(body, dict) and "refreshToken" in body:
        body = {**body, "refreshToken": ctx.get("refreshToken", "")}
    path = case["path"]
    if case.get("query"):
        path += "?" + "&".join(f"{k}={v}" for k, v in case["query"].items())
    try:
        status, _, err = CR._request(target, case["method"], path, body=body, headers=headers)
        return status, (err or None)
    except Exception as e:  # noqa: BLE001 — a transport error is a reported test error, not a crash
        return None, str(e)


def run(target: str) -> dict:
    """Replay every suite case against target and report each test. Returns a summary dict."""
    ctx = _auth_context(target)
    results: list = []
    passed = failed = errored = 0
    for agent_dir in sorted(p for p in (SUITE_DIR.iterdir() if SUITE_DIR.is_dir() else []) if p.is_dir()):
        try:
            cases = json.loads((agent_dir / "cases.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for c in cases:
            actual, err = _do_request(target, c, ctx)
            exp = c.get("expected_statuses") or []
            if err is not None:
                verdict, errored = "ERROR", errored + 1
            elif not exp:
                verdict = "PASS" if actual is not None else "FAIL"    # no explicit code → reachability
                passed += verdict == "PASS"; failed += verdict == "FAIL"
            else:
                verdict = "PASS" if actual in exp else "FAIL"
                passed += verdict == "PASS"; failed += verdict == "FAIL"
            line = (f"[{verdict}] {c['agent']} {c['test_case_id']}  "
                    f"{c['method']} {c['path']}  expected={exp or 'reachable'} actual={actual}"
                    + (f"  err={err}" if err else ""))
            print(line, flush=True)
            results.append({**{k: c.get(k) for k in
                            ("agent", "test_case_id", "method", "path", "expected_statuses")},
                            "actual_status": actual, "verdict": verdict, "error": err})
    summary = {"total": len(results), "passed": passed, "failed": failed, "errored": errored}
    print(f"\n[regression] {summary}", flush=True)
    (SUITE_DIR / "last-run-report.json").write_text(json.dumps(
        {"target": target, "summary": summary, "results": results}, indent=2))
    return summary


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("build", "run"):
        print("usage: ci_regression_suite.py build <out_root> | run [target]", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "build":
        out_root = Path(sys.argv[2]).resolve()
        m = build(out_root)
        print(f"[regression] built suite: {m['total_cases']} passing cases across {m['agents']} agents",
              flush=True)
        sys.exit(0)
    target = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    summary = run(target)
    sys.exit(1 if summary["failed"] or summary["errored"] else 0)


if __name__ == "__main__":
    main()
