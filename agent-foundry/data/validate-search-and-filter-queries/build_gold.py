#!/usr/bin/env python3
"""Gold-set builder for the API search-and-filter-query testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the documented filter contract + the agents' input spec (searchfilter_spec.json),
derives the canonical correct 5-case filter test plan per collection, sends every
case to the LOCAL seeded /resources SUT with READ-ONLY GET calls, and records the
REAL observed behavior (status class, returned count, filter-match, exclusion, and
message reference) per scenario.

The expected count for each count scenario is computed directly from the seed
(seed.known_count) — the "known count of matching records in the database" — NOT
from the server, so the gold is an independent ground truth. The server is then
checked against it: where the live SUT matches the seed-derived ideal, the empirical
Filter Accuracy is 100% (the SUT is built to the documented contract).

DummyJSON is never used or modified by this task — the target is the air-gapped local
SUT only. All HTTP is GET (no POST/PUT/PATCH/DELETE).

Outputs (all under data/validate-search-and-filter-queries/):
  - searchfilter_spec.json   the contract + per-collection expected counts/forbidden ids (INPUT to harness)
  - gold/<list_field>.json   per-collection gold scenarios
  - gold.json                consolidated gold table + empirical accuracy summary

Usage:
  BASE_URL=http://localhost:8920 python3 build_gold.py
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

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8920").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import searchfilter_spec  # noqa: E402
# Seed = the DB ground truth (independent of the server).
sys.path.insert(0, str(HERE.parents[1] / "tools" / "filter-resource-server"))
import seed  # noqa: E402

# The collections served by the local SUT. /resources is the spec's exact 20-record
# DB; /widgets is the held-out set for the staged evolution gate.
COLLECTIONS = [
    {"collection": "/resources", "list_field": "resources"},
    {"collection": "/widgets", "list_field": "widgets"},
]


def _cfg(entry: dict) -> dict:
    return {"collection": entry["collection"], "list_field": entry["list_field"],
            "id_field": "id"}


def get(path: str, params: dict, _retries: int = 2):
    """Read-only GET. Returns (status_code, parsed_json_or_None)."""
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
            try:
                return e.code, json.loads(e.read())
            except Exception:  # noqa
                return e.code, None
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None


def run_plan(cfg: dict, plan: dict):
    """Execute a plan's cases against the live SUT (read-only). Returns
    (case_obs, reqlog) where case_obs feeds searchfilter_spec.evaluate."""
    case_obs, reqlog = {}, {}
    lf = cfg["list_field"]
    list_path = cfg["collection"]
    for case in plan["cases"]:
        params = case.get("params", {})
        status, body = get(list_path, params)
        records, total, message = None, None, None
        if isinstance(body, dict):
            if status == 200:
                items = body.get(lf)
                records = items if isinstance(items, list) else None
                total = body.get("total")
            msg = body.get("message")
            message = msg if isinstance(msg, str) else None
        case_obs[case["label"]] = {"status": status, "records": records,
                                   "total": total, "message": message}
        reqlog[case["label"]] = {"type": case.get("type"), "path": list_path,
                                 "params": params, "status": status,
                                 "returned_count": (len(records) if records is not None else None),
                                 "message": message}
    return case_obs, reqlog


def _forbidden(collection: str) -> dict:
    return {"inactive_ids": seed.inactive_ids(collection),
            "category_b_ids": seed.category_b_ids(collection)}


def build_input_spec() -> dict:
    """The INPUT the harness is briefed from. Carries the documented filter contract
    plus each collection's seed-derived expected counts and forbidden-id sets (used
    by the harness's count/exclusion scenarios — NOT shown to the LLM agent)."""
    collections = []
    for c in COLLECTIONS:
        collections.append({
            "collection": c["collection"], "list_field": c["list_field"],
            "expected_counts": seed.expected_counts(c["collection"]),
            "forbidden": _forbidden(c["collection"]),
        })
    return {
        "title": "Local seeded /resources filter contract (authored for the search-and-filter task)",
        "description": "A purpose-built, air-gapped local SUT seeded with exactly the task's 20 "
                       "records (DummyJSON is never used or modified). Agents construct the filter "
                       "test plan from the documented contract; ground truth is the seed-derived "
                       "known counts and the live SUT's observed behavior.",
        "target": BASE_URL,
        "id_field": "id",
        "documented_filters": searchfilter_spec.DOCUMENTED_FILTERS,
        "unknown_param_policy": searchfilter_spec.UNKNOWN_PARAM_POLICY,
        "collections": collections,
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: local filter SUT not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "searchfilter_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    findings = []
    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        ec = seed.expected_counts(cfg["collection"])
        forbidden = _forbidden(cfg["collection"])
        plan = searchfilter_spec.build_reference_plan(cfg)
        case_obs, reqlog = run_plan(cfg, plan)
        observed = searchfilter_spec.evaluate(case_obs, forbidden)

        scenarios = []
        for label in searchfilter_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = searchfilter_spec.correct(label, tok, ec)
            scenarios.append({"scenario": label,
                              "ideal": searchfilter_spec.ideal_for(label, ec),
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0
            if not ok:
                findings.append({"collection": cfg["collection"], "scenario": label,
                                 "ideal": searchfilter_spec.ideal_for(label, ec),
                                 "observed": tok})

        rec = {"collection": cfg["collection"], "list_field": cfg["list_field"],
               "expected_counts": ec, "forbidden": forbidden,
               "reference_plan": plan, "request_log": reqlog, "scenarios": scenarios}
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "collections": len(COLLECTIONS),
        "scenarios_per_collection": len(searchfilter_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_filter_accuracy_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = seed-derived known counts + the live local SUT's observed token "
                "per (collection, scenario). The SUT is built to the documented strict filter "
                "contract, so empirical Filter Accuracy is expected to be 100% — a clean positive "
                "finding. Any non-100% row is a genuine defect in the SUT or contract, not an agent "
                "failure. DummyJSON is never used or modified.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
