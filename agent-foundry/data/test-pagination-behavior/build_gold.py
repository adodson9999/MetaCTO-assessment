#!/usr/bin/env python3
"""Gold-set builder for the API pagination-behavior testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the collection catalogue + the agents' input spec (pagination_spec.json),
derives the canonical correct pagination plan per collection, sends every plan
request to a locally-running DummyJSON with READ-ONLY GET calls, and records the
REAL observed behavior (status, returned ids, total, derived has-next) per scenario.

DummyJSON is tested AS-IS and never modified. "Seed exactly 25 records" is honored
by DESIGNATING a 25-record window per collection via a read-only GET ?limit=25&skip=0
(the datasets are fixed, so EXPECTED_IDS = the first 25 ids the API returns).

The recorded per-(collection, scenario) observed token is the ground truth. Agents
are later ranked on how faithfully their own runs reproduce this table (coverage +
correct request construction). The idealized contract lives in pagination_spec.IDEAL;
where the real token differs from the ideal is a genuine QA finding about DummyJSON.

Outputs (all under data/test-pagination-behavior/):
  - pagination_spec.json     the collection catalogue the agents are briefed from (INPUT)
  - gold/<collection>.json   per-collection gold scenarios
  - gold.json                consolidated gold table + empirical pagination-correctness summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL (read-only GET). Air-gapped.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import pagination_spec  # noqa: E402

PAGE_SIZE = 10
WINDOW_SIZE = 25

# DummyJSON list collections tested as-is. Each paginates via ?limit&skip and
# wraps its items under <list_field> with a sibling `total`. All have > 25 items
# so a 25-record window is well-defined. id_field is "id" throughout.
COLLECTIONS = [
    {"collection": "/products", "list_field": "products"},
    {"collection": "/posts",    "list_field": "posts"},
    {"collection": "/comments", "list_field": "comments"},
    {"collection": "/todos",    "list_field": "todos"},
    {"collection": "/users",    "list_field": "users"},
    {"collection": "/recipes",  "list_field": "recipes"},
]


def _cfg(entry: dict) -> dict:
    return {
        "collection": entry["collection"],
        "list_field": entry["list_field"],
        "id_field": "id",
        "limit_param": "limit",
        "offset_param": "skip",
        "page_size": PAGE_SIZE,
        "window_size": WINDOW_SIZE,
    }


def get(path: str, params: dict, _retries: int = 2):
    """Read-only GET with a small retry on transient connection failure (status -1).
    Returns (status_code, parsed_json_or_None)."""
    import time
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


def window_ids(cfg: dict) -> list:
    """Designate the 25-record window (read-only): EXPECTED_IDS = ids from
    GET <collection>?limit=25&skip=0."""
    status, body = get(cfg["collection"], {cfg["limit_param"]: WINDOW_SIZE, cfg["offset_param"]: 0})
    if status == 200 and isinstance(body, dict):
        items = body.get(cfg["list_field"], [])
        return [it.get(cfg["id_field"]) for it in items][:WINDOW_SIZE]
    return []


def run_plan(cfg: dict, plan: dict):
    """Execute a plan's requests against the live API (read-only). Returns
    (page_obs, invalid_obs) in the shape pagination_spec.evaluate expects, plus a
    raw request log."""
    page_obs, invalid_obs, reqlog = {}, {}, []
    lp, op = cfg["limit_param"], cfg["offset_param"]
    lf, idf = cfg["list_field"], cfg["id_field"]

    for pg in plan["pages"]:
        params = {lp: pg["limit"], op: pg["skip"]}
        status, body = get(cfg["collection"], params)
        ids, total = None, None
        if status == 200 and isinstance(body, dict):
            items = body.get(lf, [])
            ids = [it.get(idf) for it in items] if isinstance(items, list) else None
            total = body.get("total")
        page_obs[pg["label"]] = {"status": status, "ids": ids, "skip": pg["skip"], "total": total}
        reqlog.append({"label": pg["label"], "params": params, "status": status,
                       "returned_count": (len(ids) if ids is not None else None), "total": total})

    for iv in plan["invalid"]:
        status, _ = get(cfg["collection"], iv["params"])
        invalid_obs[iv["label"]] = {"status": status}
        reqlog.append({"label": iv["label"], "params": iv["params"], "status": status})

    return page_obs, invalid_obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each collection's
    pagination contract (param names, page size, window) WITHOUT the answer plan."""
    return {
        "title": "DummyJSON pagination contract (authored for the pagination-testing task)",
        "description": "Each collection paginates via query params `limit` (page size) and "
                       "`skip` (offset) and wraps items under <list_field> alongside a `total`. "
                       "Agents construct the pagination test plan from this; ground truth is the "
                       "live API's observed behavior. DummyJSON is read-only and never modified.",
        "target": BASE_URL,
        "page_size": PAGE_SIZE,
        "window_size": WINDOW_SIZE,
        "limit_param": "limit",
        "offset_param": "skip",
        "id_field": "id",
        "collections": [
            {"collection": c["collection"], "list_field": c["list_field"]}
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

    (HERE / "pagination_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        plan = pagination_spec.build_reference_plan(cfg)
        win = window_ids(cfg)
        page_obs, invalid_obs, reqlog = run_plan(cfg, plan)
        observed = pagination_spec.evaluate(win, page_obs, invalid_obs)

        scenarios = []
        for label in pagination_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = pagination_spec.correct(label, tok)
            scenarios.append({
                "scenario": label,
                "ideal": pagination_spec.IDEAL[label],
                "observed_token": tok,
                "api_correct": ok,
            })
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {
            "collection": cfg["collection"],
            "list_field": cfg["list_field"],
            "page_size": PAGE_SIZE,
            "window_size": WINDOW_SIZE,
            "expected_ids": win,
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
        "scenarios_per_collection": len(pagination_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_pagination_correctness_rate_pct": rate,
        "note": "Ground truth = live DummyJSON observed token per (collection, scenario). "
                "DummyJSON uses offset pagination with no cursor/next_cursor and is lenient on "
                "invalid params (only non-numeric limit/skip -> 400), so the empirical correctness "
                "rate is below 100% by design — those gaps are real QA findings, not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
