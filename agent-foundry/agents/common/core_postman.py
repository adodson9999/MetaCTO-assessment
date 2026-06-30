# Used by: shared — builds the Postman v2.1 deliverable (collection + environment) from the
# core_requirements scenarios. Consumed by run_pipeline (results/<date>/<time>/Postman/); asserted
# by guardrail G17 and the postman unit test.
"""Agent-organised Postman collection for the Core Requirements.

Top-level folders are the AGENT that owns each area (test-authentication-flows,
verify-crud-operation-integrity, validate-search-and-filter-queries) — matching the
TestCases/<agent>/ layout. Inside each folder, every request is named by the test_case_id
(TC-AUTH-001, …) of the matching test case, so a request lines up 1:1 with a row in that
agent's cases.json. {{base_url}} points at https://dummyjson.com so a grader runs the suite
straight against the real API. The Login request (TC-AUTH-001) captures {{token}}/{{refreshToken}}
into collection variables; protected requests send `Bearer {{token}}`. Every request carries a
test script with one pm.test() per assertion derived from the SAME scenario contract that drives
the test cases.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import core_testcases as CT
from core_requirements import INVALID_BEARER, PUBLIC_BASE_URL

# Parse "Send <METHOD> <path>" out of a formatted test step; require a real "/path"
# (so generic "Send GET  to ..." rows and ephemeral-mock targets are skipped).
_STEP_RE = re.compile(r"\bSend\s+(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)")
_BODY_RE = re.compile(r"with body [\"'](.+?)[\"']\s*$")
_STATUS_RE = re.compile(r"\b([1-5]\d{2}|[1-5]xx)\b")


def _url(sc: dict) -> dict:
    raw_path = sc["path"]
    segs = [s for s in raw_path.strip("/").split("/") if s]
    q = [{"key": k, "value": str(v)} for k, v in (sc.get("query") or {}).items()]
    url = {"raw": "{{base_url}}" + raw_path + ("?" + "&".join(f"{i['key']}={i['value']}" for i in q) if q else ""),
           "host": ["{{base_url}}"], "path": segs}
    if q:
        url["query"] = q
    return url


def _auth_header(sc: dict) -> list[dict]:
    a = sc.get("auth")
    if a == "bearer":
        return [{"key": "Authorization", "value": "Bearer {{token}}"}]
    if a in ("bad", "expired", "revoked"):
        return [{"key": "Authorization", "value": INVALID_BEARER}]
    return []


def _body(sc: dict):
    if sc.get("auth") == "refresh":
        return {"refreshToken": "{{refreshToken}}"}
    return sc.get("body")


def _js_get() -> str:
    return ("var json = (function(){ try { return pm.response.json(); } catch(e){ return {}; } })();\n"
            "function get(o,p){ if(p==='$root') return o; return p.split('.').reduce(function(a,k){"
            " return (a==null)?undefined:a[k]; }, o); }\n")


def _assertion_js(a: dict) -> str:
    t = a["t"]
    if t == "status":
        if "eq" in a:
            return f'pm.test("status is {a["eq"]}", function(){{ pm.response.to.have.status({a["eq"]}); }});'
        codes = json.dumps(a["in"])
        return (f'pm.test("status in {a["in"]}", function(){{ pm.expect({codes})'
                f'.to.include(pm.response.code); }});')
    p = a.get("path", "$root")
    if t == "has":
        return f'pm.test("has {p}", function(){{ pm.expect(get(json,"{p}")).to.not.be.undefined; }});'
    if t == "eq":
        return (f'pm.test("{p} == {a["val"]!r}", function(){{ pm.expect(get(json,"{p}"))'
                f'.to.eql({json.dumps(a["val"])}); }});')
    if t == "type":
        chk = {"array": 'pm.expect(Array.isArray(v)).to.be.true;',
               "number": 'pm.expect(typeof v === "number").to.be.true;',
               "string": 'pm.expect(typeof v === "string").to.be.true;'}[a["is"]]
        return f'pm.test("{p} is {a["is"]}", function(){{ var v=get(json,"{p}"); {chk} }});'
    if t == "len_lte":
        return (f'pm.test("len({p}) <= {a["n"]}", function(){{ pm.expect(get(json,"{p}").length)'
                f'.to.be.at.most({a["n"]}); }});')
    if t == "contains":
        return (f'pm.test("{p} contains {a["sub"]!r}", function(){{ pm.expect(String(get(json,"{p}"))'
                f'.toLowerCase()).to.include({json.dumps(a["sub"].lower())}); }});')
    if t == "each":
        return (f'pm.test("every {p}[].{a["key"]} == {a["val"]!r}", function(){{ get(json,"{p}")'
                f'.forEach(function(it){{ pm.expect(it["{a["key"]}"]).to.eql({json.dumps(a["val"])}); }}); }});')
    if t == "subset_keys":
        allowed = json.dumps(a["allowed"])
        return (f'pm.test("{p}[] keys subset of {a["allowed"]}", function(){{ var al={allowed};'
                f' get(json,"{p}").forEach(function(it){{ Object.keys(it).forEach(function(k){{'
                f' pm.expect(al).to.include(k); }}); }}); }});')
    if t == "sorted":
        rev = "true" if a.get("order") == "desc" else "false"
        return (f'pm.test("{p} sorted by {a["key"]} {a.get("order","asc")}", function(){{'
                f' var ks=get(json,"{p}").map(function(it){{return it["{a["key"]}"];}});'
                f' var s=ks.slice().sort(); if({rev}) s.reverse();'
                f' pm.expect(ks).to.eql(s); }});')
    return f'// unknown assertion {t}'


def _test_script(sc: dict) -> list[str]:
    lines = [_js_get()]
    for a in sc["assertions"]:
        lines.append(_assertion_js(a))
    cap = sc.get("capture") or {}
    for env_var, key in cap.items():
        lines.append(f'if (json["{key}"]) pm.collectionVariables.set("{env_var}", json["{key}"]);')
    return "\n".join(lines).splitlines()


def _item(sc: dict, tc_id: str) -> dict:
    headers = _auth_header(sc)
    body = _body(sc)
    req = {"method": sc["method"], "header": headers, "url": _url(sc),
           "description": (sc.get("note") or "") + (f"\n\nExpected: HTTP {sc['expected_status']}.")}
    if body is not None:
        req["header"] = headers + [{"key": "Content-Type", "value": "application/json"}]
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                       "options": {"raw": {"language": "json"}}}
    return {"name": f"{tc_id} — {sc['title']}", "request": req,
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": _test_script(sc)}}]}


def build(results: list[dict]) -> tuple[dict, dict]:
    """Return (collection, environment) Postman v2.1 objects from executed scenarios, organised
    into one folder per AGENT with each request named by the matching test_case_id."""
    by_agent = CT.to_testcases(results)                       # {agent: [8-field cases]} (assigns tc_ids)
    sid_to = {c["test_data"]["scenario_id"]: (agent, c["test_case_id"])
              for agent, cases in by_agent.items() for c in cases}
    folders: dict[str, list] = {agent: [] for agent in by_agent}   # auth, crud, search (scenario order)
    for sc in results:
        hit = sid_to.get(sc["id"])
        if not hit:
            continue
        agent, tc_id = hit
        folders[agent].append(_item(sc, tc_id))
    collection = {
        "info": {"name": "DummyJSON API — Core Requirements Suite",
                 "description": "One folder per test agent (test-authentication-flows, "
                                "verify-crud-operation-integrity, validate-search-and-filter-queries); "
                                "each request is named by the test_case_id it matches in that agent's "
                                "cases.json. Set {{base_url}} to https://dummyjson.com and run top-to-bottom "
                                "(test-authentication-flows › TC-AUTH-001 captures {{token}}/{{refreshToken}}).",
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [{"name": agent, "item": items} for agent, items in folders.items() if items],
        "variable": [{"key": "base_url", "value": PUBLIC_BASE_URL},
                     {"key": "token", "value": ""}, {"key": "refreshToken", "value": ""},
                     {"key": "newProductId", "value": ""}],
    }
    environment = {"name": "DummyJSON (public)",
                   "values": [{"key": "base_url", "value": PUBLIC_BASE_URL, "enabled": True},
                              {"key": "token", "value": "", "enabled": True},
                              {"key": "refreshToken", "value": "", "enabled": True},
                              {"key": "newProductId", "value": "", "enabled": True}],
                   "_postman_variable_scope": "environment"}
    return collection, environment


# --------------------------------------------------------------------------- #
# Non-core agents: derive a basic request (method + path + status assertion) from
# each formatted test case, so every agent that issues real API calls is included.
# --------------------------------------------------------------------------- #
def _parse_request(case: dict):
    """Return (method, path, query, body) from a test case's steps, or None if it isn't a
    concrete API call against the documented target (skips no-path/ephemeral-mock rows)."""
    for step in case.get("test_steps", []):
        m = _STEP_RE.search(step)
        if not m:
            continue
        method, raw = m.group(1), m.group(2).rstrip(".")
        path, _, qs = raw.partition("?")
        if not path.startswith("/"):
            continue
        query = dict(p.split("=", 1) for p in qs.split("&") if "=" in p) if qs else {}
        body = None
        bm = _BODY_RE.search(step)
        if bm:
            try:
                body = json.loads(bm.group(1))
            except (ValueError, json.JSONDecodeError):
                body = None
        return method, path, query, body
    return None


def _status_test(case: dict) -> list[str]:
    m = _STATUS_RE.search(case.get("expected_result", ""))
    code = m.group(1) if m else None
    js = []
    if code and code.endswith("xx"):
        lo = int(code[0]) * 100
        js.append(f'pm.test("status is {code}", function(){{ pm.expect(pm.response.code)'
                  f'.to.be.within({lo}, {lo + 99}); }});')
    elif code:
        js.append(f'pm.test("status is {code}", function(){{ pm.response.to.have.status({code}); }});')
    else:
        js.append('pm.test("response received", function(){ pm.expect(pm.response.code).to.be.a("number"); });')
    return js


def _basic_item(case: dict):
    pr = _parse_request(case)
    if pr is None:
        return None
    method, path, query, body = pr
    qstr = ("?" + "&".join(f"{k}={v}" for k, v in query.items())) if query else ""
    url = {"raw": "{{base_url}}" + path + qstr, "host": ["{{base_url}}"],
           "path": [s for s in path.strip("/").split("/") if s]}
    if query:
        url["query"] = [{"key": k, "value": str(v)} for k, v in query.items()]
    req = {"method": method, "header": [], "url": url,
           "description": f"Expected: {case.get('expected_result', '')}"}
    if body is not None:
        req["header"] = [{"key": "Content-Type", "value": "application/json"}]
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                       "options": {"raw": {"language": "json"}}}
    return {"name": f"{case['test_case_id']} — {case['title_summary']}", "request": req,
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": _status_test(case)}}]}


def build_full(out_root, core_results: list[dict]) -> tuple[dict, dict]:
    """Full collection: the rich core-agent folders (from core_results) PLUS a folder for every
    OTHER agent under out_root/TestCases that has >=1 concrete API-call test case (requests named
    by test_case_id, with a status assertion). Agents whose cases aren't real API calls (generic
    no-path probes, ephemeral local-mock targets) get no folder."""
    collection, environment = build(core_results)
    core_agents = set(CT.AGENT_OF_AREA.values())
    tc_root = Path(out_root) / "TestCases"
    if not tc_root.is_dir():
        return collection, environment
    for agent_dir in sorted(p for p in tc_root.iterdir() if p.is_dir()):
        agent = agent_dir.name
        if agent in core_agents:
            continue
        try:
            cases = json.loads((agent_dir / "cases.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        items = [it for it in (_basic_item(c) for c in cases) if it]
        if items:
            collection["item"].append({"name": agent, "item": items})
    return collection, environment
