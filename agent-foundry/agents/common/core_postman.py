# Used by: shared — builds the Postman v2.1 deliverable (collection + environment) from the
# core_requirements scenarios. Consumed by run_pipeline (results/<date>/<time>/Postman/); asserted
# by guardrail G17 and the postman unit test.
"""Folder-organised Postman collection for the four Core Requirements.

Folders: Authentication, CRUD — Products, Search & Filtering, Error Handling. {{base_url}} points
at https://dummyjson.com so a grader runs the suite straight against the real API. The Login
request captures {{token}}/{{refreshToken}} into collection variables; protected requests send
`Bearer {{token}}`. Every request carries a test script with one pm.test() per assertion derived
from the SAME scenario contract that drives the test cases — so the collection asserts the
documented behaviour, not the local mock's quirks.
"""
from __future__ import annotations

import json

from core_requirements import INVALID_BEARER, PUBLIC_BASE_URL

FOLDER_OF_AREA = {"Authentication": "Authentication", "CRUD": "CRUD — Products",
                  "Search & Filtering": "Search & Filtering"}
ERROR_FOLDER = "Error Handling"


def _folder(sc: dict) -> str:
    # invalid-input negatives live in the Error Handling folder; the non-persistence proof stays in CRUD
    if sc["expected_status"] >= 400 and sc["id"] != "CRUD-CREATE-NONPERSIST":
        return ERROR_FOLDER
    return FOLDER_OF_AREA[sc["area"]]


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


def _item(sc: dict) -> dict:
    headers = _auth_header(sc)
    body = _body(sc)
    req = {"method": sc["method"], "header": headers, "url": _url(sc),
           "description": (sc.get("note") or "") + (f"\n\nExpected: HTTP {sc['expected_status']}.")}
    if body is not None:
        req["header"] = headers + [{"key": "Content-Type", "value": "application/json"}]
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                       "options": {"raw": {"language": "json"}}}
    return {"name": f"{sc['id']} — {sc['title']}", "request": req,
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": _test_script(sc)}}]}


def build(results: list[dict]) -> tuple[dict, dict]:
    """Return (collection, environment) Postman v2.1 objects from executed scenarios."""
    order = ["Authentication", "CRUD — Products", "Search & Filtering", "Error Handling"]
    folders: dict[str, list] = {name: [] for name in order}
    for sc in results:
        folders[_folder(sc)].append(_item(sc))
    collection = {
        "info": {"name": "DummyJSON API — Core Requirements Suite",
                 "description": "Auth (JWT lifecycle), CRUD (products), Search & Filtering, and Error "
                                "Handling. Set {{base_url}} to https://dummyjson.com and run top-to-bottom "
                                "(the Authentication › Login request captures {{token}}/{{refreshToken}}).",
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [{"name": name, "item": items} for name, items in folders.items() if items],
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
