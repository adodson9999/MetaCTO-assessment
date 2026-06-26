#!/usr/bin/env python3
"""Gold-set builder for the API header-propagation testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the endpoint catalogue + the agents' input spec (header_spec.json),
derives the canonical correct propagation plan per endpoint
(header_spec.build_reference_plan), executes each plan against a locally-running
DummyJSON THROUGH THE SAME HARNESS path the agents use (agents/common/header.py),
and records the REAL observed token per scenario.

DummyJSON is tested AS-IS and never modified. The one POST endpoint is DummyJSON's
simulated, non-persisting create; auth login is read-only. The "API server log" is
DummyJSON's own winston Console output captured to the file at $FORGE_SERVER_LOG.

The recorded per-(endpoint, scenario) observed token is the ground truth. Agents are
later ranked on how faithfully their own runs reproduce this table (correct plan
construction + faithful execution). The idealized contract lives in header_spec.IDEAL;
where the real token differs from the ideal is a genuine QA finding about DummyJSON
(it propagates no correlation id at all -> Header Propagation Rate = 0%).

Outputs (all under data/validate-header-propagation/):
  - header_spec.json        the endpoint catalogue the agents are briefed from (INPUT)
  - gold/<endpoint>.json    per-endpoint gold scenarios
  - gold.json               consolidated gold table + empirical header-propagation summary

Usage:
  FORGE_TARGET_BASE_URL=http://localhost:8899 FORGE_SERVER_LOG=/tmp/dj.log python3 build_gold.py
Stdlib only. No network beyond the local target (read-only auth + simulated POST). Air-gapped.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")

# Ensure the harness + spec are importable, and FORGE_WORKSPACE is set so header.py
# resolves SPEC_PATH/SERVER_LOG the same way the agent runs do.
WS = HERE.parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "agents" / "common"))
import header_spec  # noqa: E402

# Representative endpoints — a mix of POST/GET and authed/public. DummyJSON has NO
# endpoint that calls >=2 downstream services; these stand in so the propagation
# checks have a real surface, and the gold honestly records that downstream count = 0.
ENDPOINTS = [
    {"name": "products_add", "method": "POST", "path": "/products/add", "auth": True,
     "body": {"title": "header-propagation-probe"}},
    {"name": "posts_add", "method": "POST", "path": "/posts/add", "auth": True,
     "body": {"title": "header-propagation-probe", "userId": 1}},
    {"name": "comments_add", "method": "POST", "path": "/comments/add", "auth": True,
     "body": {"body": "header-propagation-probe", "postId": 1, "userId": 1}},
    {"name": "carts_add", "method": "POST", "path": "/carts/add", "auth": True,
     "body": {"userId": 1, "products": [{"id": 1, "quantity": 1}]}},
    {"name": "auth_me", "method": "GET", "path": "/auth/me", "auth": True},
    {"name": "products_get", "method": "GET", "path": "/products/1", "auth": False},
]
# DummyJSON declares no downstream services. If a real multi-service target were used,
# each downstream's grep-able log file would be listed here as {name, log_path}.
DOWNSTREAM_SERVICES = []


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's
    propagation contract WITHOUT the answer plan."""
    return {
        "title": "DummyJSON correlation-header propagation contract (authored for the task)",
        "description": "Send the fixed correlation_id under header_name and assert it propagates "
                       "byte-for-byte into the response header, the API server log, and every "
                       "downstream service log; a second request with no correlation header must "
                       "trigger an auto-generated UUID v4 that also propagates. Agents construct "
                       "the propagation test plan from this; ground truth is the live API's "
                       "observed behavior. DummyJSON is never modified.",
        "target": BASE_URL,
        "correlation_id": header_spec.CORR_ID,
        "header_name": header_spec.HEADER_NAME,
        "token_placeholder": header_spec.TOKEN_PLACEHOLDER,
        "downstream_services": DOWNSTREAM_SERVICES,
        "endpoints": ENDPOINTS,
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    # Write the INPUT spec first so the harness's downstream lookup reads it.
    (HERE / "header_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    # Import the harness AFTER env + spec are in place (it reads env at import time).
    import header  # noqa: E402

    token = header._login_token()
    consolidated = []
    total = correct = rt_total = rt_correct = 0

    for endpoint in ENDPOINTS:
        plan = header_spec.build_reference_plan(endpoint)
        obs = header._exec_plan(endpoint, plan, token)
        observed = header_spec.evaluate(plan, endpoint, obs)

        scenarios = []
        for label in header_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = header_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": header_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
            if label in header_spec.RUNTIME_LABELS:
                rt_total += 1
                rt_correct += 1 if ok else 0

        rec = {"endpoint": endpoint["name"], "method": endpoint["method"], "path": endpoint["path"],
               "auth_required": bool(endpoint.get("auth")),
               "reference_plan": plan, "observations": obs, "scenarios": scenarios}
        (GOLD_DIR / f"{endpoint['name']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * rt_correct / rt_total, 2) if rt_total else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(header_spec.SCENARIO_LABELS),
        "plan_scenarios_per_endpoint": len(header_spec.PLAN_SCENARIOS),
        "runtime_scenarios_per_endpoint": len(header_spec.RUNTIME_SCENARIOS),
        "total_scenarios": total,
        "runtime_scenarios_total": rt_total,
        "runtime_scenarios_propagated": rt_correct,
        "empirical_header_propagation_rate_pct": rate,
        "downstream_services": len(DOWNSTREAM_SERVICES),
        "note": "Ground truth = live DummyJSON observed token per (endpoint, scenario). DummyJSON "
                "echoes no X-Correlation-ID, logs no request headers (so the id is absent from the "
                "API server log), makes zero downstream calls, and generates no UUID when the header "
                "is absent -> empirical Header Propagation Rate = 0%. That 0% is a real, inherent QA "
                "finding, not an agent failure. The plan-correctness scenarios (all 'true' for the "
                "reference plan) are what give the fidelity leaderboard its resolution.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
