#!/usr/bin/env python3
"""Gold-set builder for the API timeout-handling testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the agent-facing input spec (timeout_spec.json — the documented contract, with the
fixture's compliance flags stripped), derives the canonical correct timeout plan per
service, drives the plan against a locally-running timeout-gateway (inject the 60s
upstream delay, probe each endpoint, remove the delay, re-probe), and records the
REAL observed token per scenario.

The gateway is the air-gapped local stand-in for a WireMock upstream stub fronted by
a Toxiproxy latency toxic. One endpoint is deliberately non-compliant, so the gold
records a real, catchable defect (mirrors DummyJSON's lenient pagination behavior).

Outputs (all under data/test-timeout-handling/):
  - timeout_spec.json        the service catalogue the agents are briefed from (INPUT)
  - gold/<service>.json      per-service gold scenarios
  - gold.json                consolidated gold table + empirical enforcement summary

Usage:
  FORGE_TARGET_BASE_URL=http://127.0.0.1:8911 python3 build_gold.py
Stdlib only. No network beyond the local gateway. Air-gapped.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
GOLD_DIR = HERE / "gold"
BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8911").rstrip("/")

# Make the shared modules importable, and pin the harness to this workspace/target
# BEFORE importing it (it reads FORGE_WORKSPACE / FORGE_TARGET_BASE_URL at import).
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ["FORGE_TARGET_BASE_URL"] = BASE_URL
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "tools" / "timeout-gateway"))

import fixture_config  # noqa: E402
import timeout_spec  # noqa: E402
import timeout as harness  # noqa: E402  (reuse the raw-socket probe + toxic lifecycle)


def _svc_cfg(svc: dict) -> dict:
    return {
        "service": svc["service"],
        "upstream_timeout_s": svc["upstream_timeout_s"],
        "buffer_s": svc["buffer_s"],
        "restore_max_ms": svc["restore_max_ms"],
        "endpoints": [{"method": e["method"], "path": e["path"]} for e in svc["endpoints"]],
    }


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: timeout-gateway not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    # author the agent-facing input spec (no compliance answers)
    (HERE / "timeout_spec.json").write_text(
        json.dumps(fixture_config.agent_facing_spec(BASE_URL), indent=2))

    injected_ms = fixture_config.INJECTED_DELAY_S * 1000
    consolidated = []
    total = correct = 0
    endpoints_total = endpoints_enforced = 0

    cfgs = [_svc_cfg(s) for s in fixture_config.SERVICES]

    # Build the reference plans, then run all delayed probes under one injected toxic,
    # remove it, run all restore probes — the same lifecycle the harness uses.
    plans = {c["service"]: timeout_spec.build_reference_plan(c) for c in cfgs}
    delayed_obs, restore_obs = {}, {}

    harness.inject_toxic(injected_ms)
    for c in cfgs:
        rt = c["upstream_timeout_s"] + c["buffer_s"] + 5.0
        for probe in plans[c["service"]]["delayed"]:
            p = harness.http_probe(probe["method"], probe["path"],
                                   delay_ms=injected_ms, read_timeout_s=rt)
            delayed_obs[(c["service"], probe["path"])] = harness._delayed_observation(p)
    harness.remove_toxic()
    for c in cfgs:
        for probe in plans[c["service"]]["restore"]:
            p = harness.http_probe(probe["method"], probe["path"], delay_ms=0, read_timeout_s=5.0)
            restore_obs[(c["service"], probe["path"])] = {"status": p.get("status"),
                                                          "elapsed_ms": p.get("elapsed_ms")}

    for c in cfgs:
        svc = c["service"]
        plan = plans[svc]
        ref_max_wait = plan["max_wait_s"]
        scenarios = []

        svc_obs = timeout_spec.evaluate_service(plan, c)
        for label in timeout_spec.SERVICE_SCENARIO_LABELS:
            tok = svc_obs.get(label, "missing")
            ok = timeout_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": timeout_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        for ep in c["endpoints"]:
            d = delayed_obs.get((svc, ep["path"]))
            r = restore_obs.get((svc, ep["path"]))
            ep_eval = timeout_spec.evaluate_endpoint(d, r, ref_max_wait, c["restore_max_ms"])
            for label in timeout_spec.ENDPOINT_SCENARIO_LABELS:
                tok = ep_eval.get(label, "missing")
                ok = timeout_spec.correct(label, tok)
                scenarios.append({"scenario": f"{ep['path']}::{label}",
                                  "ideal": timeout_spec.IDEAL[label],
                                  "observed_token": tok, "api_correct": ok})
                total += 1
                correct += 1 if ok else 0
            endpoints_total += 1
            if timeout_spec.enforcement_pass(ep_eval):
                endpoints_enforced += 1

        rec = {"service": svc, "upstream_timeout_s": c["upstream_timeout_s"],
               "buffer_s": c["buffer_s"], "restore_max_ms": c["restore_max_ms"],
               "reference_plan": plan, "scenarios": scenarios}
        (GOLD_DIR / f"{svc}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct / total, 2) if total else None
    enf = round(100.0 * endpoints_enforced / endpoints_total, 2) if endpoints_total else None
    summary = {
        "target": BASE_URL,
        "services": len(cfgs),
        "endpoints_total": endpoints_total,
        "endpoints_enforced": endpoints_enforced,
        "empirical_timeout_enforcement_rate_pct": enf,
        "total_scenarios": total,
        "api_correct_scenarios": correct,
        "empirical_scenario_correctness_rate_pct": rate,
        "note": "Ground truth = the local timeout-gateway's real observed token per "
                "(service, scenario) under a 60s injected upstream delay. One endpoint "
                "(GET /inventory/low-stock) is non-compliant (500 + leaky body + open "
                "connection), so the enforcement rate is below 100% by design — that gap "
                "is a real QA finding, not an agent failure.",
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "services": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
