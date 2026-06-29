#!/usr/bin/env python3
"""Gold-set builder for the API caching-headers testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the endpoint catalogue + the agents' input spec (caching_spec.json),
derives the canonical correct caching plan per endpoint, executes the fixed caching
probe sequence against a locally-running DummyJSON (GET -> conditional GET ->
PUT update -> re-GET -> stale conditional GET -> four mutation requests), captures the
REAL Cache-Control/ETag headers, statuses, and the conditional-GET body length, and
records the REAL observed token per scenario.

WRITES NOTE — DummyJSON's data is deepFrozen and its write controllers RETURN computed
objects without persisting (verified in src/controllers/*.js and live: after the writes,
GET shows the record + ETag unchanged). So these real writes do not modify the target.
All HTTP is to the LOCAL target only.

The recorded per-(collection, scenario) observed token is the ground truth. Agents are
later ranked on how faithfully their own runs reproduce this table. The idealized
contract lives in caching_spec.IDEAL; where the real token differs from the ideal is a
genuine QA finding about DummyJSON (it ships NO Cache-Control header, and its
non-persistent writes mean the ETag never changes after an "update").

Outputs (all under data/verify-caching-headers/):
  - caching_spec.json        the endpoint catalogue the agents are briefed from (INPUT)
  - gold/<collection>.json   per-endpoint gold scenarios
  - gold.json                consolidated gold table + empirical caching summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import caching_spec  # noqa: E402

TARGET_ID = 1

# DummyJSON list collections that expose a cacheable GET item + the full mutation set
# (POST /add, PUT/PATCH/DELETE /<id>). id_field is "id" throughout. Tested as-is.
COLLECTIONS = [
    {"collection": "/products", "list_field": "products"},
    {"collection": "/posts",    "list_field": "posts"},
    {"collection": "/comments", "list_field": "comments"},
    {"collection": "/todos",    "list_field": "todos"},
    {"collection": "/users",    "list_field": "users"},
    {"collection": "/recipes",  "list_field": "recipes"},
]


def _cfg(entry: dict) -> dict:
    return {"collection": entry["collection"], "id_field": "id", "target_id": TARGET_ID}


def send(method: str, path: str, body, extra_headers: dict | None = None, _retries: int = 2):
    """Returns (status, headers_lowercased, body_bytes). Small retry on transient only."""
    import time
    url = f"{BASE_URL}{path}"
    data = None
    headers = dict(extra_headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.getcode(), {k.lower(): v for k, v in r.getheaders()}, r.read()
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
            except Exception:  # noqa
                raw = b""
            return e.code, {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}, raw
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return None, {}, b""


def run_plan(plan: dict):
    reqlog = []
    cg = plan["cacheable_get"]
    item = cg["path"]

    # 1. cacheable GET -> ETAG_1 + Cache-Control
    gstatus, gh, graw = send("GET", item, None)
    etag1 = gh.get("etag")
    get_obs = {"status": gstatus, "cache_control": gh.get("cache-control"), "etag": etag1}
    reqlog.append({"label": "get", "method": "GET", "path": item, "status": gstatus,
                   "cache_control": gh.get("cache-control"), "etag": etag1, "body_len": len(graw)})

    # 2. conditional GET with If-None-Match: ETAG_1
    if etag1:
        cstatus, _ch, craw = send("GET", item, None, {"If-None-Match": etag1})
        conditional_obs = {"status": cstatus, "body_len": len(craw)}
        reqlog.append({"label": "conditional_get", "method": "GET", "path": item,
                       "if_none_match": etag1, "status": cstatus, "body_len": len(craw)})
    else:
        conditional_obs = {"status": None, "body_len": None}

    # 3. PUT update (changed field)
    ur = plan["update_request"]
    ustatus, _uh, _ub = send(ur["method"], ur["path"], ur.get("body"))
    update_obs = {"status": ustatus}
    reqlog.append({"label": "update", "method": ur["method"], "path": ur["path"], "status": ustatus})

    # 4. fresh GET -> ETAG_2
    rstatus, rh, _rb = send("GET", item, None)
    etag2 = rh.get("etag")
    reget_obs = {"status": rstatus, "etag": etag2}
    reqlog.append({"label": "reget", "method": "GET", "path": item, "status": rstatus,
                   "etag": etag2, "etag_changed": (etag1 is not None and etag2 is not None and etag2 != etag1)})

    # 5. stale conditional GET with old ETAG_1
    if etag1:
        sstatus, _sh, _sb = send("GET", item, None, {"If-None-Match": etag1})
        stale_obs = {"status": sstatus}
        reqlog.append({"label": "stale_conditional_get", "method": "GET", "path": item,
                       "if_none_match": etag1, "status": sstatus})
    else:
        stale_obs = {"status": None}

    # 6. mutation no-store probes
    mutation_obs = {}
    for req in plan["mutation_requests"]:
        mstatus, mh, _mb = send(req["method"], req["path"], req.get("body"))
        cc = mh.get("cache-control")
        mutation_obs[req["label"]] = {"status": mstatus, "cache_control": cc}
        reqlog.append({"label": f"mutation_{req['label']}", "method": req["method"],
                       "path": req["path"], "status": mstatus, "cache_control": cc})

    return get_obs, conditional_obs, update_obs, reget_obs, stale_obs, mutation_obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's caching
    contract (collection_path, id_field, target_id) WITHOUT the answer plan."""
    return {
        "title": "DummyJSON caching contract (authored for the caching-headers testing task)",
        "description": "Each collection exposes a cacheable GET /<col>/<id> plus the mutation "
                       "endpoints POST /<col>/add and PUT/PATCH/DELETE /<col>/<id>. Agents construct "
                       "the caching test plan from this; ground truth is the live API's observed "
                       "headers/statuses. DummyJSON's writes are non-persistent (deepFrozen data), so "
                       "exercising them does not modify the target.",
        "target": BASE_URL,
        "id_field": "id",
        "target_id": TARGET_ID,
        "collections": [{"collection": c["collection"], "list_field": c["list_field"]}
                        for c in COLLECTIONS],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "caching_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    observed_by_collection = {}
    total_scenarios = correct_scenarios = 0
    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        plan = caching_spec.build_reference_plan(cfg)
        get_obs, cond_obs, upd_obs, reget_obs, stale_obs, mut_obs, reqlog = run_plan(plan)
        observed = caching_spec.evaluate(get_obs, cond_obs, upd_obs, reget_obs, stale_obs, mut_obs)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in caching_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = caching_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": caching_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {"collection": cfg["collection"], "target_id": TARGET_ID,
               "reference_plan": plan, "request_log": reqlog, "scenarios": scenarios}
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    comp = caching_spec.compliance(observed_by_collection)
    correctness = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "collections": len(COLLECTIONS),
        "scenarios_per_collection": len(caching_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_caching_correctness_rate_pct": correctness,
        "headline_caching_header_compliance_rate_pct": comp["rate_pct"],
        "compliance_passing_cases": comp["passing"],
        "compliance_total_cases": comp["total"],
        "note": "Ground truth = live DummyJSON observed token per (collection, scenario). "
                "Express auto-emits a WEAK ETag (non-empty) on GETs and serves a conditional "
                "GET as 304 with an empty body, but adds NO Cache-Control header anywhere "
                "(so cacheable endpoints have no positive max-age and mutations declare no "
                "no-store). DummyJSON's writes are non-persistent (deepFrozen), so after a PUT "
                "the resource is unchanged: the ETag does NOT change (ETAG_2 == ETAG_1) and the "
                "old ETag still matches, so the stale conditional GET still returns 304 instead "
                "of 200. The headline Caching Header Compliance Rate counts a cacheable endpoint "
                "as passing only if Cache-Control has a positive max-age AND ETag is non-empty AND "
                "the conditional GET is 304-with-empty-body AND the post-update ETag changes; no "
                "endpoint satisfies the conjunction, so the rate is 0%. The sub-100% rates are "
                "real QA findings, not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "compliance_cases": comp["cases"], "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
