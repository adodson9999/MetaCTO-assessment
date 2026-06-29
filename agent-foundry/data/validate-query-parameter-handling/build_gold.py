#!/usr/bin/env python3
"""Gold-set builder for the API query-parameter-handling testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the documented query-parameter contract + the agents' input spec
(queryparam_spec.json), derives the canonical correct 9-case query-parameter test
plan per collection, sends every case to a locally-running DummyJSON with READ-ONLY
GET calls, and records the REAL observed behavior (status class + realized filter
effect) per scenario.

DummyJSON is tested AS-IS and never modified. All HTTP is GET only — no
POST/PUT/PATCH/DELETE against the target.

The recorded per-(collection, scenario) observed token is the ground truth. Agents
are later ranked on how faithfully their own runs reproduce this table (coverage +
correct request construction + filter verification). The idealized contract lives in
queryparam_spec.IDEAL; where the real token differs from the ideal is a genuine QA
finding about DummyJSON (chiefly: the search endpoint does not require its `q`
parameter, so an absent-required-param request returns 200 instead of 400).

Outputs (all under data/validate-query-parameter-handling/):
  - queryparam_spec.json     the contract the agents are briefed from (INPUT)
  - gold/<collection>.json   per-collection gold scenarios
  - gold.json                consolidated gold table + empirical accuracy summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL (read-only GET). Air-gapped.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import queryparam_spec  # noqa: E402

# The four DummyJSON list collections that ALSO expose a /search route, so every
# documented parameter — including the idealized-required `q` on /search — is
# uniformly testable. Each has id_field "id".
COLLECTIONS = [
    {"collection": "/products", "list_field": "products", "search_path": "/products/search"},
    {"collection": "/posts",    "list_field": "posts",    "search_path": "/posts/search"},
    {"collection": "/users",    "list_field": "users",    "search_path": "/users/search"},
    {"collection": "/recipes",  "list_field": "recipes",  "search_path": "/recipes/search"},
]


def _cfg(entry: dict) -> dict:
    return {
        "collection": entry["collection"],
        "list_field": entry["list_field"],
        "id_field": "id",
        "search_path": entry["search_path"],
    }


def get(path: str, params: dict, _retries: int = 2):
    """Read-only GET with a small retry on transient connection failure (status -1).
    Returns (status_code, parsed_json_or_None)."""
    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{path}?{qs}" if qs else f"{BASE_URL}{path}"
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                try:
                    return r.getcode(), json.loads(body)
                except Exception:  # noqa
                    return r.getcode(), None
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None


def run_plan(cfg: dict, plan: dict):
    """Execute a plan's cases against the live API (read-only). Returns
    (case_obs, reqlog) where case_obs feeds queryparam_spec.evaluate."""
    case_obs, reqlog = {}, {}
    lf, idf = cfg["list_field"], cfg["id_field"]
    list_path, search_path = cfg["collection"], cfg["search_path"]

    for case in plan["cases"]:
        path = search_path if case.get("route") == "search" else list_path
        params = case.get("params", {})
        status, body = get(path, params)
        records = None
        total = None
        if status == 200 and isinstance(body, dict):
            items = body.get(lf)
            records = items if isinstance(items, list) else None
            total = body.get("total")
        rec = {"status": status, "records": records, "total": total}
        if case.get("filter"):
            rec["filter"] = case["filter"]
            rec["filter_value"] = case.get("filter_value")
        case_obs[case["label"]] = rec
        reqlog[case["label"]] = {
            "route": case.get("route"), "path": path, "params": params,
            "status": status,
            "returned_count": (len(records) if records is not None else None),
        }
    _ = idf
    return case_obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each collection's
    documented query-parameter contract WITHOUT the answer plan."""
    return {
        "title": "DummyJSON query-parameter contract (authored for the query-parameter-handling task)",
        "description": "Each list collection exposes the documented query parameters under "
                       "'documented_params' and a sibling /search route whose required parameter "
                       "is `q`. Agents construct the query-parameter test plan from this; ground "
                       "truth is the live API's observed behavior. DummyJSON is read-only and never modified.",
        "target": BASE_URL,
        "id_field": "id",
        "documented_params": queryparam_spec.DOCUMENTED_PARAMS,
        "undocumented_param_policy": queryparam_spec.UNDOCUMENTED_POLICY,
        "collections": [
            {"collection": c["collection"], "list_field": c["list_field"],
             "search_path": c["search_path"]}
            for c in COLLECTIONS
        ],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "queryparam_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    findings = []
    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        plan = queryparam_spec.build_reference_plan(cfg)
        case_obs, reqlog = run_plan(cfg, plan)
        observed = queryparam_spec.evaluate(case_obs, cfg["id_field"])

        scenarios = []
        for label in queryparam_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = queryparam_spec.correct(label, tok)
            scenarios.append({
                "scenario": label,
                "ideal": queryparam_spec.IDEAL[label],
                "observed_token": tok,
                "api_correct": ok,
            })
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0
            if not ok:
                findings.append({
                    "collection": cfg["collection"], "scenario": label,
                    "ideal": queryparam_spec.IDEAL[label], "observed": tok})

        rec = {
            "collection": cfg["collection"],
            "list_field": cfg["list_field"],
            "search_path": cfg["search_path"],
            "reference_plan": plan,
            "request_log": reqlog,
            "scenarios": scenarios,
        }
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "collections": len(COLLECTIONS),
        "scenarios_per_collection": len(queryparam_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_query_param_handling_accuracy_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = live DummyJSON observed token per (collection, scenario). "
                "DummyJSON is strict on parameter TYPE (non-numeric limit/skip and an out-of-enum "
                "order with sortBy all -> 400) but lenient on parameter PRESENCE: the /search route "
                "does not require its `q` parameter, so an absent-required-param request returns 200 "
                "instead of 400. That gap is a real QA finding, not an agent failure.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
