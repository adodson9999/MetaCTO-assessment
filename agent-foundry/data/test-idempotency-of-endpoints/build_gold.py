#!/usr/bin/env python3
"""Gold-set builder for the API idempotency-of-endpoints testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the collection catalogue + the agents' input spec (idempotency_spec.json),
derives the canonical correct idempotency plan per collection, executes every planned
request against a locally-running DummyJSON (real PUT/DELETE/POST, each replayed with
one Idempotency-Key), captures every response BYTE-FOR-BYTE, runs the read-only
state-effect probes, and records the REAL observed token per scenario.

WRITES NOTE — DummyJSON's data is deepFrozen and its write controllers RETURN computed
objects without persisting (verified in src/controllers/*.js and live: after the writes,
GET shows the record unchanged and the collection `total` unchanged). So these real
writes do not modify the target. All HTTP is to the LOCAL target only.

"SELECT COUNT(*) = 1" is honored without a SQL database by a read-only state-effect
probe: GET the target record (present exactly once) and confirm no duplication.

The recorded per-(collection, scenario) observed token is the ground truth. Agents are
later ranked on how faithfully their own runs reproduce this table. The idealized
contract lives in idempotency_spec.IDEAL; where the real token differs from the ideal
is a genuine QA finding about DummyJSON.

Outputs (all under data/test-idempotency-of-endpoints/):
  - idempotency_spec.json    the collection catalogue the agents are briefed from (INPUT)
  - gold/<collection>.json   per-collection gold scenarios
  - gold.json                consolidated gold table + empirical idempotency summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import idempotency_spec  # noqa: E402

TARGET_ID = 1

# DummyJSON list collections with PUT/DELETE/POST write endpoints, tested as-is.
# Each has a record at id=1 and an /add create endpoint. id_field is "id" throughout.
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


def send(method: str, path: str, body, idem_key, _retries: int = 2):
    """Returns (status_code, raw_body_str). Small retry on transient -1 only."""
    url = f"{BASE_URL}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if idem_key is not None:
        headers[idempotency_spec.HEADER_NAME] = idem_key
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception:  # noqa
                return e.code, None
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None


def replay(req: dict) -> dict:
    n = int(req.get("replays", idempotency_spec.REPLAYS))
    codes, bodies = [], []
    for i in range(n):
        if i:
            time.sleep(idempotency_spec.INTER_REPLAY_DELAY_S)  # surface time-varying fields
        code, raw = send(req["method"], req["path"], req.get("body"), req.get("idempotency_key"))
        codes.append(code)
        bodies.append(raw)
    return {"method": req["method"], "path": req["path"],
            "idempotency_key": req.get("idempotency_key"), "replays": n,
            "codes": codes, "bodies": bodies}


def record_count(path: str):
    code, _ = send("GET", path, None, None)
    if code == 200:
        return 1
    if code == 404:
        return 0
    return None


def run_plan(plan: dict):
    write_obs, reqlog = {}, []
    for req in plan["idempotent_requests"]:
        rec = replay(req)
        write_obs[req["label"]] = rec
        reqlog.append({"label": req["label"], "method": rec["method"], "path": rec["path"],
                       "idempotency_key": rec["idempotency_key"], "replays": rec["replays"],
                       "codes": rec["codes"],
                       "bodies_identical": all(b == rec["bodies"][0] for b in rec["bodies"])})

    cr = plan["create_request"]
    create_obs = replay(cr)
    scode, sbody = send(cr["method"], cr["path"], cr.get("body"), cr.get("second_key"))
    create_obs["second"] = {"code": scode, "body": sbody, "second_key": cr.get("second_key")}
    reqlog.append({"label": cr["label"], "method": create_obs["method"], "path": create_obs["path"],
                   "idempotency_key": create_obs["idempotency_key"], "replays": create_obs["replays"],
                   "codes": create_obs["codes"],
                   "bodies_identical": all(b == create_obs["bodies"][0] for b in create_obs["bodies"]),
                   "second_key": cr.get("second_key"), "second_code": scode,
                   "second_distinct_from_first": (sbody is not None and sbody != create_obs["bodies"][0])})

    state = {
        "put_record_count": record_count(write_obs["put"]["path"]),
        "delete_record_count": record_count(write_obs["delete"]["path"]),
    }
    return write_obs, create_obs, reqlog, state


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each collection's
    idempotency contract (collection_path, id_field, target_id) WITHOUT the answer plan."""
    return {
        "title": "DummyJSON idempotency contract (authored for the idempotency-testing task)",
        "description": "Each collection exposes PUT /<col>/<id>, DELETE /<col>/<id>, and "
                       "POST /<col>/add. Agents construct the idempotency test plan from this; "
                       "ground truth is the live API's observed behavior. DummyJSON's writes are "
                       "non-persistent (deepFrozen data), so exercising them does not modify the target.",
        "target": BASE_URL,
        "id_field": "id",
        "target_id": TARGET_ID,
        "header_name": idempotency_spec.HEADER_NAME,
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

    (HERE / "idempotency_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    observed_by_collection = {}
    total_scenarios = correct_scenarios = 0
    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        plan = idempotency_spec.build_reference_plan(cfg)
        write_obs, create_obs, reqlog, state = run_plan(plan)
        observed = idempotency_spec.evaluate(write_obs, create_obs, state)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in idempotency_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = idempotency_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": idempotency_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {"collection": cfg["collection"], "target_id": TARGET_ID,
               "reference_plan": plan, "request_log": reqlog,
               "state_probe": state, "scenarios": scenarios}
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    comp = idempotency_spec.compliance(observed_by_collection)
    correctness = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "collections": len(COLLECTIONS),
        "scenarios_per_collection": len(idempotency_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_idempotency_correctness_rate_pct": correctness,
        "headline_idempotency_compliance_rate_pct": comp["rate_pct"],
        "compliance_passing_cases": comp["passing"],
        "compliance_total_cases": comp["total"],
        "note": "Ground truth = live DummyJSON observed token per (collection, scenario). "
                "PUT replays are byte-identical (idempotent); DELETE replays DIFFER byte-for-byte "
                "because each body carries a fresh `deletedOn` timestamp (idempotency violation); "
                "POST replays and a fresh-key POST return the same id (the Idempotency-Key header "
                "is ignored, so a new key does NOT create a distinct record). There is no SQL "
                "database and writes do not persist, so the 'exactly one record' check is a read-only "
                "state probe. Compliance counts only the idempotent endpoints (PUT, DELETE); POST is "
                "informational since DummyJSON documents no Idempotency-Key support. The sub-100% "
                "rates are real QA findings, not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "compliance_cases": comp["cases"], "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
