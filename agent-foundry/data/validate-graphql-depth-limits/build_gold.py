#!/usr/bin/env python3
"""Gold-set builder for the GraphQL-query-depth-limit testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the documented depth-limit contract + the agents' input spec (gqldepth_spec.json),
derives the canonical correct 4-case depth test plan per endpoint (depth_3,
at_limit=max_depth, one_over=max_depth+1, deep_15), builds the GraphQL query for each
depth, POSTs each to the LOCAL GraphQL SUT with read-only queries, and records the
REAL observed behavior (status class, data-present, errors, error message, and
response time) per scenario.

All ideals are fixed constants from the documented depth-limit contract (200/400/true),
so the gold is an independent ground truth. The live SUT is then checked against it:
where it matches, the empirical GraphQL Depth Enforcement Rate is 100% (the SUT is
built to the documented contract).

DummyJSON is never used or modified by this task — the target is the air-gapped local
GraphQL SUT only. Every request is a read-only GraphQL query over POST (the SUT has no
mutation resolvers).

Outputs (all under data/validate-graphql-depth-limits/):
  - gqldepth_spec.json    the contract + per-endpoint max_depth (INPUT to harness)
  - gold/<endpoint>.json  per-endpoint gold scenarios
  - gold.json             consolidated gold table + empirical enforcement summary

Usage:
  BASE_URL=http://localhost:8940 python3 build_gold.py
Stdlib only. No network beyond BASE_URL (read-only GraphQL queries). Air-gapped.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8940").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure + query generator (one source of truth with the harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import gqldepth_spec  # noqa: E402
# The SUT's documented endpoint/max_depth map (the DB ground truth for the contract).
sys.path.insert(0, str(HERE.parents[1] / "tools" / "graphql-depth-server"))
import server as sut  # noqa: E402

# The endpoints served by the local SUT. /graphql (max_depth 7) is the primary;
# /graphql-strict (max_depth 4) is the held-out set for the staged evolution gate.
ENDPOINTS = [{"endpoint": p, "max_depth": d} for p, d in sut.MAX_DEPTH_BY_PATH.items()]


def post_query(path: str, query: str, _retries: int = 2):
    """Read-only GraphQL POST. Returns (status_code, parsed_json|None, elapsed_s)."""
    url = f"{BASE_URL}{path}"
    body = json.dumps({"query": query}).encode()
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                el = time.perf_counter() - start
                try:
                    return r.getcode(), json.loads(raw), el
                except Exception:  # noqa
                    return r.getcode(), None, el
        except urllib.error.HTTPError as e:
            el = time.perf_counter() - start
            try:
                return e.code, json.loads(e.read()), el
            except Exception:  # noqa
                return e.code, None, el
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None, None


def run_plan(cfg: dict, plan: dict):
    """Execute a plan's cases against the live SUT (read-only). Returns
    (case_obs, reqlog) where case_obs feeds gqldepth_spec.evaluate."""
    case_obs, reqlog = {}, {}
    path = cfg["endpoint"]
    for case in plan["cases"]:
        depth = case["depth"]
        query = gqldepth_spec.build_query(depth)
        status, body, el = post_query(path, query)
        data_present, errors, message = False, None, None
        if isinstance(body, dict):
            data_present = body.get("data") is not None
            errs = body.get("errors")
            if isinstance(errs, list):
                errors = errs
                if errs and isinstance(errs[0], dict):
                    msg = errs[0].get("message")
                    message = msg if isinstance(msg, str) else None
        case_obs[case["label"]] = {"status": status, "data_present": data_present,
                                   "errors": errors, "message": message, "elapsed": el}
        reqlog[case["label"]] = {"type": case.get("type"), "path": path,
                                 "sent_depth": depth, "status": status,
                                 "data_present": data_present,
                                 "errors_count": (len(errors) if isinstance(errors, list) else None),
                                 "message": message,
                                 "elapsed_s": round(el, 4) if el is not None else None}
    return case_obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the harness is briefed from. Carries the documented depth-limit
    contract per endpoint (endpoint path + max_depth). The four probe depths are NOT
    pre-resolved here — the agent must derive at_limit=max_depth and one_over=max+1."""
    return {
        "title": "Local GraphQL depth-limit contract (authored for the depth-limit task)",
        "description": "A purpose-built, air-gapped local GraphQL SUT enforcing a documented "
                       "maximum query depth per endpoint (DummyJSON is never used or modified). "
                       "Agents construct the depth test plan from the documented max_depth; ground "
                       "truth is the fixed contract outcomes and the live SUT's observed behavior.",
        "target": BASE_URL,
        "depth_unit": gqldepth_spec.DEPTH_UNIT,
        "deep_time_budget_s": gqldepth_spec.DEEP_TIME_BUDGET_S,
        "endpoints": [{"endpoint": e["endpoint"], "max_depth": e["max_depth"]} for e in ENDPOINTS],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: local GraphQL SUT not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "gqldepth_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    findings = []
    for entry in ENDPOINTS:
        cfg = {"endpoint": entry["endpoint"], "max_depth": entry["max_depth"]}
        plan = gqldepth_spec.build_reference_plan(cfg)
        case_obs, reqlog = run_plan(cfg, plan)
        observed = gqldepth_spec.evaluate(case_obs)

        scenarios = []
        for label in gqldepth_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = gqldepth_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": gqldepth_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0
            if not ok:
                findings.append({"endpoint": cfg["endpoint"], "scenario": label,
                                 "ideal": gqldepth_spec.ideal_for(label), "observed": tok})

        rec = {"endpoint": cfg["endpoint"], "max_depth": cfg["max_depth"],
               "reference_plan": plan, "request_log": reqlog, "scenarios": scenarios}
        safe = entry["endpoint"].strip("/").replace("/", "_") or "root"
        (GOLD_DIR / f"{safe}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(gqldepth_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_depth_enforcement_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = the fixed depth-limit contract outcomes + the live local SUT's "
                "observed token per (endpoint, scenario). The SUT is built to the documented "
                "contract (depth<=max -> 200+data; depth>max -> 400+depth/complexity error; deep "
                "reject < 1s), so empirical Depth Enforcement is expected to be 100% — a clean "
                "positive finding. Any non-100% row is a genuine defect in the SUT or contract, not "
                "an agent failure. DummyJSON is never used or modified.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
