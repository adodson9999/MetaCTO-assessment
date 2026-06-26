#!/usr/bin/env python3
"""Gold-set builder for the API-gateway-routing testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the agent-facing input spec (routing_spec.json — the documented contract, with the
gateway's hidden defect flags stripped), derives the canonical correct routing plan
per route, drives each plan against a locally-running routing-gateway (reset every
backend journal, optionally stop the backend for the service-down route, send the
request, read every journal, restart the backend), and records the REAL observed
token per scenario.

The gateway + backends are the air-gapped local stand-in for an API gateway fronting
one WireMock instance per service. Two routes carry seeded defects (one misroute, one
in-transit body mutation), so the gold records real, catchable findings (mirrors
DummyJSON's lenient pagination behavior).

Outputs (all under data/test-api-gateway-routing/):
  - routing_spec.json     the route catalogue the agents are briefed from (INPUT)
  - gold/<route>.json     per-route gold scenarios
  - gold.json             consolidated gold table + empirical forwarding summary

Usage:
  FORGE_TARGET_BASE_URL=http://127.0.0.1:8920 python3 build_gold.py
Stdlib only. No network beyond the local gateway/backends. Air-gapped.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
GOLD_DIR = HERE / "gold"
BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8920").rstrip("/")

# Pin the harness to this workspace/target BEFORE importing it (it reads
# FORGE_WORKSPACE / FORGE_TARGET_BASE_URL at import). Also author routing_spec.json
# first, because the harness reads it for the backend admin URLs.
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ["FORGE_TARGET_BASE_URL"] = BASE_URL
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "tools" / "routing-gateway"))

import fixture_config  # noqa: E402
import routing_spec  # noqa: E402


def _slug(method: str, path: str) -> str:
    return f"{method.upper()}_{path.strip('/').replace('/', '_') or 'root'}"


def _route_cfg(route: dict, services: list[str]) -> dict:
    return {
        "method": route["method"],
        "path": route["path"],
        "headers": dict(route["headers"]),
        "body": route.get("body"),
        "expected_backend": route["expected_backend"],
        "down_test": bool(route.get("down_test")),
        "services": list(services),
    }


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: routing-gateway not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    # author the agent-facing input spec (defect flags stripped; admin URLs in a
    # harness-only block) — written BEFORE importing the harness's spec readers.
    spec = fixture_config.agent_facing_spec(BASE_URL)
    (HERE / "routing_spec.json").write_text(json.dumps(spec, indent=2))

    import routing  # noqa: E402  -- imported now so it sees the just-written spec
    admin = routing._admin_urls()
    services = spec["services"]

    consolidated = []
    total = correct = 0
    routes_total = routes_forwarded = 0

    for route in fixture_config.ROUTES:
        cfg = _route_cfg(route, services)
        route_id = f"{cfg['method'].upper()} {cfg['path']}"
        plan = routing_spec.build_reference_plan(cfg)
        exec_input, _log = routing._execute(plan, cfg, admin)
        plan_obs = routing_spec.evaluate_plan(cfg, plan)
        exec_obs = routing_spec.evaluate_exec(cfg, exec_input)

        observed = dict(plan_obs)
        observed.update(exec_obs)
        ideal = routing_spec.ideal_tokens(cfg)

        scenarios = []
        for label in routing_spec.scenarios_for(cfg):
            tok = observed.get(label, "missing")
            ok = routing_spec.correct(cfg, label, tok)
            scenarios.append({"scenario": label, "ideal": ideal.get(label),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        routes_total += 1
        if routing_spec.forwarding_pass(cfg, exec_obs):
            routes_forwarded += 1

        rec = {"route": route_id, "route_path": cfg["path"], "method": cfg["method"],
               "expected_backend": cfg["expected_backend"], "down_test": cfg["down_test"],
               "reference_plan": plan, "scenarios": scenarios}
        (GOLD_DIR / f"{_slug(cfg['method'], cfg['path'])}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * routes_forwarded / routes_total, 2) if routes_total else None
    scen_rate = round(100.0 * correct / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "routes_total": routes_total,
        "routes_forwarded": routes_forwarded,
        "empirical_route_forwarding_accuracy_pct": rate,
        "total_scenarios": total,
        "api_correct_scenarios": correct,
        "empirical_scenario_correctness_rate_pct": scen_rate,
        "note": "Ground truth = the local routing-gateway's real observed token per "
                "(route, scenario), per-call isolated (every backend journal reset "
                "before each request). GET /api/orders/7 is MISROUTED to payments-mock "
                "and PUT /api/payments/9 has its body MUTATED in transit, so the "
                "forwarding accuracy is below 100% by design — those gaps are real QA "
                "findings, not agent failures. The service-down route correctly yields "
                "503 with no backend receiving the request.",
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "routes": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
