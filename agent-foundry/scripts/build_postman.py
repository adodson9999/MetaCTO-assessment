#!/usr/bin/env python3
# Used by: shared — one Postman collection built from ALL agents' test cases.
"""create-postman-collection (general flow, deterministic).

Activated by the test-case-creator: for every test case that contains an API call, this
appends a request to ONE Postman collection for the whole orchestrated run. Each request is
named by its test_case_id. Requests use {{base_url}} (an environment defaulting to the real
dummyjson.com). A login request captures the JWT into {{token}}, and protected requests carry
Bearer {{token}} auth. Deterministic — request method/path/params/body come straight from each
agent's recorded steps, nothing invented.

Outputs (one per run):
  results/runs/<RUN>/postman/collection.json     Postman v2.1 collection
  results/runs/<RUN>/postman/environment.json    Postman environment (base_url, token)

Usage:  python build_postman.py <RUN_ID>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
import format_test_cases as F           # records, code, base_label, find_cases_file, _find, request_index
import orchestrate_full as O            # API_TESTERS

BASE_URL = os.environ.get("FORGE_POSTMAN_BASE_URL", "https://dummyjson.com")
# create-postman-collection is the BUILDER now, not a test subject
TESTER_AGENTS = [a for a in O.API_TESTERS if a != "create-postman-collection"]
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _request_of(rec: dict, ridx: dict) -> dict | None:
    """Structured request for one record: prefer the record's own fields, else the matching
    request_log entry (path/params/method). None if there is no concrete API call."""
    label = str(F._first(rec, F.LABEL_KEYS) or "")
    log = ridx.get(label) or ridx.get(F.base_label(label)) or {}
    method = str(rec.get("method") or log.get("method") or "GET").upper()
    path = (rec.get("path") or rec.get("sent_path") or log.get("path")
            or rec.get("endpoint") or rec.get("collection") or "")
    if not path:
        return None
    params = rec.get("params") if isinstance(rec.get("params"), dict) else log.get("params") or {}
    body = rec.get("body")
    p = str(path)
    # protected = the agent flagged it, or it's /auth/me — but NEVER the login/refresh endpoints
    auth = (bool(rec.get("auth_required")) or "/auth/me" in p) and "/auth/login" not in p and "/auth/refresh" not in p
    return {"method": method, "path": p, "params": params, "body": body, "auth_required": auth,
            "expected": F._first(rec, F.EXPECTED_KEYS),
            "log_status": log.get("status") or log.get("actual_code")}


import re as _re


def status_test(expected, log_status) -> tuple[str, list[str]]:
    """A pm.test() asserting the response status, derived from the case's expected_result
    (exact code, Nxx class, or X-or-Y), falling back to the observed status, else a no-server-
    error check so every request carries a test."""
    val = "" if expected is None else str(expected).strip().lower()
    m = _re.fullmatch(r"([1-5]\d\d)", val)
    if m:
        c = int(m.group(1))
        return (f"Status code is {c}", [f"pm.test('Status code is {c}', function () {{ pm.response.to.have.status({c}); }});"])
    m = _re.fullmatch(r"([1-5])xx", val)
    if m:
        lo = int(m.group(1)) * 100
        return (f"Status is {m.group(1)}xx", [f"pm.test('Status is {m.group(1)}xx', function () {{ pm.expect(pm.response.code).to.be.within({lo}, {lo + 99}); }});"])
    codes = _re.findall(r"[1-5]\d\d", val)
    if len(codes) >= 2:
        arr = "[" + ", ".join(codes) + "]"
        return ("Status is one of expected", [f"pm.test('Status is one of {codes}', function () {{ pm.expect({arr}).to.include(pm.response.code); }});"])
    if log_status and _re.fullmatch(r"[1-5]\d\d", str(log_status)):
        c = int(log_status)
        return (f"Status code is {c}", [f"pm.test('Status code is {c}', function () {{ pm.response.to.have.status({c}); }});"])
    return ("No server error", ["pm.test('No server error (status < 500)', function () { pm.expect(pm.response.code).to.be.below(500); });"])


def _request_index(data: dict) -> dict:
    rl = F._find(data, "request_log")
    out = {}
    if isinstance(rl, list):
        for r in rl:
            if isinstance(r, dict) and r.get("label"):
                out[r["label"]] = r
    return out


def agent_requests(agent: str, data: dict) -> list[dict]:
    """(name, request) for every API-call test case of an agent. Multi-step records (CRUD
    resources, oauth stages) yield one request per real action, suffixed by the step name."""
    ridx = _request_index(data)
    out = []
    for i, rec in enumerate(F.records(data), 1):
        if not isinstance(rec, dict):
            continue
        tcid = f"TC-{F.code(agent)}-{i:03d}"
        nested = rec.get("steps") or rec.get("stages")
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            for st in nested:
                p = st.get("sent_path") or st.get("path") or st.get("url") or ""
                if not p:
                    continue
                m = str(st.get("method") or "GET").upper()
                step = st.get("step") or st.get("stage") or st.get("action") or ""
                exp = "201" if str(step).upper() == "CREATE" else "200"   # documented CRUD success
                out.append({"name": f"{tcid}-{step}".rstrip("-"),
                            "req": {"method": m, "path": str(p), "params": {}, "body": None,
                                    "auth_required": "/auth/me" in str(p) or m in WRITE_METHODS,
                                    "expected": exp, "log_status": st.get("actual_code")}})
        else:
            r = _request_of(rec, ridx)
            if r:
                out.append({"name": tcid, "req": r})
    return out


def to_item(name: str, req: dict) -> dict:
    raw_path = req["path"].lstrip("/")
    segs = [s for s in raw_path.split("/") if s]
    qs = ("?" + "&".join(f"{k}={v}" for k, v in req["params"].items())) if req["params"] else ""
    url = {"raw": "{{base_url}}/" + raw_path + qs, "host": ["{{base_url}}"], "path": segs}
    if req["params"]:
        url["query"] = [{"key": str(k), "value": str(v)} for k, v in req["params"].items()]
    request = {"method": req["method"], "header": [], "url": url}
    if req.get("body") is not None:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": req["body"] if isinstance(req["body"], str) else json.dumps(req["body"]),
                           "options": {"raw": {"language": "json"}}}
    if req.get("auth_required"):
        request["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
    # pm.test status assertion derived from the case's expected_result
    _, exec_lines = status_test(req.get("expected"), req.get("log_status"))
    event = [{"listen": "test", "script": {"type": "text/javascript", "exec": exec_lines}}]
    return {"name": name, "request": request, "event": event, "response": []}


def login_item() -> dict:
    """A login request whose test script captures the accessToken into {{token}}."""
    return {
        "name": "Login — capture {{token}} (run first)",
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": [
            "var data = pm.response.json();",
            "if (data && data.accessToken) {",
            "    pm.collectionVariables.set('token', data.accessToken);",
            "    pm.environment.set('token', data.accessToken);",
            "}",
            "pm.test('login returns a token', function () {",
            "    pm.expect(data).to.have.property('accessToken');",
            "});",
        ]}}],
        "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {"raw": "{{base_url}}/auth/login", "host": ["{{base_url}}"], "path": ["auth", "login"]},
            "body": {"mode": "raw", "raw": json.dumps({"username": "emilys", "password": "emilyspass", "expiresInMins": 60}),
                     "options": {"raw": {"language": "json"}}},
        },
        "response": [],
    }


def run(run_id: str) -> dict:
    items = [login_item()]
    per_agent = {}
    for agent in TESTER_AGENTS:
        cf = F.find_cases_file(run_id, agent)
        if cf is None:
            continue
        try:
            data = json.loads(cf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        reqs = agent_requests(agent, data)
        per_agent[agent] = len(reqs)
        for r in reqs:
            items.append(to_item(r["name"], r["req"]))

    collection = {
        "info": {"name": f"DummyJSON API Test Suite — {run_id}",
                 "description": "One collection per orchestrated run. Requests named by test_case_id; "
                                "built deterministically from each agent's recorded API calls. "
                                "Run 'Login' first to populate {{token}}.",
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": items,
        "variable": [{"key": "base_url", "value": BASE_URL}, {"key": "token", "value": ""}],
    }
    environment = {"id": f"dummyjson-{run_id}", "name": f"DummyJSON — {run_id}",
                   "values": [{"key": "base_url", "value": BASE_URL, "enabled": True},
                              {"key": "token", "value": "", "enabled": True}],
                   "_postman_variable_scope": "environment"}

    out = WS / "results" / "runs" / run_id / "postman"
    out.mkdir(parents=True, exist_ok=True)
    (out / "collection.json").write_text(json.dumps(collection, indent=2))
    (out / "environment.json").write_text(json.dumps(environment, indent=2))
    total_requests = len(items) - 1  # minus the login item
    print(f"[create-postman-collection] 1 collection | {total_requests} requests "
          f"from {len(per_agent)} agents -> {out}/collection.json", flush=True)
    return {"collection": str(out / "collection.json"), "requests": total_requests,
            "agents": len(per_agent), "per_agent": per_agent}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python build_postman.py <RUN_ID>", file=sys.stderr)
        sys.exit(2)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
