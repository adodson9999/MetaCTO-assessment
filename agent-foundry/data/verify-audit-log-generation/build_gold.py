#!/usr/bin/env python3
"""Gold-set builder for the API audit-log-generation verification task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the collection catalogue + the agents' input spec (auditlog_spec.json), derives the
canonical correct audit-verification plan per collection (auditlog_spec.build_reference_plan),
and runs it through the SAME shared harness the four agents use (authenticate ->
create/update/delete -> capture the target's log -> query it per audit_query ->
evaluate every scenario). The recorded per-(collection, scenario) observed token is the
ground truth; agents are later ranked on how faithfully their own runs reproduce it.

Reusing the harness guarantees the gold is exactly what a perfect agent (one that
emits build_reference_plan verbatim) would observe — no second execution path to drift.

DummyJSON is NEVER modified: writes are non-persistent (deepFrozen), all HTTP is LOCAL,
and capturing the winston request-log uses the runtime LOG_ENABLED flag (not a source
change). The idealized audit contract (3 valid entries, each with all required fields
non-null and timestamp within 5s) has no analog in DummyJSON — capturing its request-log
yields lines with timestamp + ip_address but user_id/action_type/resource_id NULL =>
Audit Log Coverage Rate = 0%, the honest QA finding.

Outputs (all under data/verify-audit-log-generation/):
  - auditlog_spec.json       the collection catalogue the agents are briefed from (INPUT)
  - gold/<collection>.json   per-collection gold scenarios
  - gold.json                consolidated gold table + empirical coverage summary

Usage:
  BASE_URL=http://localhost:8899 FORGE_AUDIT_LOG=/tmp/dj_audit.log \
      python3 build_gold.py
Stdlib only. No network beyond BASE_URL (local). Air-gapped except the optional Claude
backend (not used by this reference builder — it runs the deterministic reference plan).
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
WS = HERE.parents[1]

# Point the shared harness at this target + log BEFORE importing it (it reads env at import).
os.environ.setdefault("FORGE_TARGET_BASE_URL", BASE_URL)
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ.setdefault("FORGE_SANDBOX_ROOT", str(WS))

sys.path.insert(0, str(WS / "agents" / "common"))
import auditlog_spec  # noqa: E402
import auditlog       # noqa: E402  (reads the env set above)

TEST_USER_ID = "user-test-001"

# DummyJSON list collections with create(/add) + update/delete(/:id) endpoints, as-is.
COLLECTIONS = [
    {"collection": "/products", "list_field": "products"},
    {"collection": "/posts",    "list_field": "posts"},
    {"collection": "/comments", "list_field": "comments"},
    {"collection": "/todos",    "list_field": "todos"},
    {"collection": "/users",    "list_field": "users"},
    {"collection": "/recipes",  "list_field": "recipes"},
]


def _cfg(entry: dict) -> dict:
    return {"collection": entry["collection"], "id_field": "id", "test_user_id": TEST_USER_ID}


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each collection's audit
    contract (collection_path, list_field) WITHOUT the answer plan."""
    return {
        "title": "DummyJSON audit-logging contract (authored for the audit-log-verification task)",
        "description": "Each collection exposes POST /<col>/add (create), PUT /<col>/<id> "
                       "(update), and DELETE /<col>/<id> (delete). The agent builds an "
                       "audit-verification plan from this; ground truth is the live API's "
                       "observed behavior + its captured log. DummyJSON's writes are "
                       "non-persistent (deepFrozen) and it has no audit-log system, so "
                       "exercising it does not modify the target and produces no audit entries.",
        "target": BASE_URL,
        "id_field": "id",
        "test_user_id": TEST_USER_ID,
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

    (HERE / "auditlog_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    token = auditlog.authenticate()
    consolidated = []
    observed_by_collection = {}
    total_scenarios = correct_scenarios = 0

    for entry in COLLECTIONS:
        cfg = _cfg(entry)
        plan = auditlog_spec.build_reference_plan(cfg)
        op_obs, op_log, t_start, t_end, rid = auditlog._exec_ops(cfg, plan, token)
        audit_obs = auditlog._query_audit(plan, op_log, t_start, t_end)
        observed = auditlog_spec.evaluate(op_obs, audit_obs)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in auditlog_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = auditlog_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": auditlog_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {"collection": cfg["collection"], "test_user_id": TEST_USER_ID,
               "reference_plan": plan, "resource_id": rid, "op_log": op_log,
               "audit_query_result": audit_obs, "scenarios": scenarios}
        (GOLD_DIR / f"{entry['list_field']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    cov = auditlog_spec.coverage(observed_by_collection)
    correctness = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "authenticated": token is not None,
        "collections": len(COLLECTIONS),
        "scenarios_per_collection": len(auditlog_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_audit_correctness_rate_pct": correctness,
        "headline_audit_log_coverage_rate_pct": cov["rate_pct"],
        "coverage_covered_ops": cov["covered"],
        "coverage_total_ops": cov["total"],
        "note": "Ground truth = live DummyJSON observed token per (collection, scenario). "
                "DummyJSON has NO audit-log system; the only log is request-logger.js's "
                "winston 'HTTP Request' stdout (LOG_ENABLED=true), which carries timestamp "
                "+ ip but NO user_id/action_type/resource_id and is not user-scoped. So no "
                "captured line qualifies as a correctly-populated audit entry => Audit Log "
                "Coverage Rate = 0% (0/N auditable ops). CREATE returns 201 (status ok) but "
                "the returned id is a non-persistent phantom (length+1), so the literal "
                "follow-on PUT/DELETE on it return 404 (update/delete status NOT ok). The "
                "sub-100% rates are real QA findings, not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "coverage_cases": cov["cases"], "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
