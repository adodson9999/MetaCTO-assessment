#!/usr/bin/env python3
"""Gold-set builder for the API webhook-delivery testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it reads the
subject catalogue (webhook_spec.json), derives the canonical correct webhook test plan
per subject (webhook_spec.build_reference_plan), starts a LOCAL receiver, executes that
plan against a locally-running DummyJSON (POST the registration, POST the resource, poll
the receiver, verify the delivered payload + HMAC, exercise the bounded retry path), and
records the REAL observed token per scenario.

DummyJSON's source is never modified: its POST /<x>/add endpoints are simulated (echo a
created object, persist nothing) and it has no /webhooks route, so executing the plan
cannot mutate it. It ships no webhook subsystem, so the recorded ground truth is that no
webhook is ever delivered — a legitimate QA finding, mirroring how test-pagination-behavior
surfaced DummyJSON's lenient param handling. The idealized contract lives in
webhook_spec.ideal_for(); where the real token differs from the ideal is the finding.

Outputs (all under data/test-webhook-delivery/):
  - gold/<subject>.json   per-subject gold scenarios
  - gold.json             consolidated gold table + empirical summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL + the loopback receiver. The cloud LLM backend
is NOT used here — the gold reference is pure deterministic code.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")

# Reuse the harness so gold is produced by exactly the same execution path the agents
# are scored on (one source of truth for plan shape, execution, and evaluation).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
os.environ.setdefault("FORGE_TARGET_BASE_URL", BASE_URL)
import webhook_spec  # noqa: E402
import webhook as harness  # noqa: E402
from webhook_receiver import WebhookReceiver  # noqa: E402


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    spec = json.loads((HERE / "webhook_spec.json").read_text())

    # one receiver URL for briefing/fidelity (the canonical plan copies it verbatim)
    rcv = WebhookReceiver(path="/hook").start()
    receiver_url = rcv.url
    rcv.stop()

    consolidated = []
    total_scenarios = correct_scenarios = 0
    deliveries = 0
    for subj in spec["subjects"]:
        cfg = {
            "resource": subj["resource"],
            "webhooks_path": spec.get("webhooks_path", "/webhooks"),
            "resource_path": subj["resource_path"],
            "resource_body": subj["resource_body"],
            "receiver_url": receiver_url,
        }
        ref_plan = webhook_spec.build_reference_plan(cfg)
        exec_obs = harness._exec_plan(cfg, ref_plan)   # real execution, real receiver
        observed = webhook_spec.evaluate(cfg, ref_plan, exec_obs)
        if exec_obs.get("delivered"):
            deliveries += 1

        scenarios = []
        for label in webhook_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = webhook_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": webhook_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        log = exec_obs.pop("_log", [])
        rec = {"subject": cfg["resource"], "resource_path": cfg["resource_path"],
               "webhooks_path": cfg["webhooks_path"], "receiver_url": receiver_url,
               "reference_plan": ref_plan, "exec_obs": exec_obs, "request_log": log,
               "scenarios": scenarios}
        (GOLD_DIR / f"{cfg['resource']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "subjects": len(spec["subjects"]),
        "scenarios_per_subject": len(webhook_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_webhook_contract_correctness_rate_pct": rate,
        "deliveries_received": deliveries,
        "note": "Ground truth = live DummyJSON observed token per (subject, scenario). "
                "DummyJSON ships no webhook subsystem: POST /webhooks 404s (registration "
                "not accepted) and no event is ever delivered, so every exec_delivered_* / "
                "exec_signature_valid / exec_retry_* scenario is 'false' or 'missing' and the "
                "Webhook Delivery Success Rate is 0% — a real QA finding, not an agent failure. "
                "The plan_* scenarios are all 'true' for the canonical reference plan; that is "
                "the framework-attributable signal the judge scores fidelity against.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "subjects": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
