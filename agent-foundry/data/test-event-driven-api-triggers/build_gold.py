#!/usr/bin/env python3
"""Gold-set builder for the Test-Event-Driven-API-Triggers task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
  - topics.json           the consumer contract the local substrate loads, AND
  - eventdriven_spec.json  the agents' input brief catalogue,
both from the single source of truth eventdriven_spec.TOPICS. It then executes the
canonical CORRECT event-trigger plan per topic against the locally-running substrate
(tools/eventbus_target/app.py) with REAL timing — publishing the well-formed event,
polling the resource, and publishing the malformed event, then reading the consumer log
and the DLQ — and records the REAL observed behavior per scenario.

Two findings are recorded:
  1. Against the LOCAL substrate (a correct event-driven service), the documented contract
     holds: Event Processing Success Rate = 100% and Dead-Letter Queue Delivery Rate = 100%.
     This is the gold the four agents are scored against (fidelity-to-gold).
  2. Against DummyJSON-as-the-system, the rates are 0%: DummyJSON consumes no topics, has
     no consumer, no DLQ, and no consumer-liveness signal (its only AWS usage is S3), so an
     event published nowhere changes nothing. This is the honest QA finding, recorded in the
     summary as the contrast. DummyJSON is never modified.

Outputs (all under data/test-event-driven-api-triggers/):
  - topics.json            consumer contract for the substrate (CONFIG)
  - eventdriven_spec.json  the topic catalogue the agents are briefed from (INPUT)
  - gold/<topic>.json      per-topic gold scenarios
  - gold.json              consolidated gold table + empirical summary

Usage:
  EVENTBUS_BASE_URL=http://127.0.0.1:8930 python3 build_gold.py
Stdlib only. No network beyond EVENTBUS_BASE_URL (loopback). The cloud LLM backend is NOT
used here — the gold reference is pure deterministic code.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("EVENTBUS_BASE_URL", "http://127.0.0.1:8930").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import eventdriven_spec  # noqa: E402

HEALTH_SETTLE_SECONDS = float(os.environ.get("EVENTDRIVEN_HEALTH_SETTLE_SECONDS", "3"))


def _request(method, path, body=None, timeout=15.0):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.getcode(), (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        try:
            return e.code, (json.loads(raw) if raw else {})
        except Exception:  # noqa
            return e.code, {}
    except Exception:  # noqa
        return -1, {}


def reset(cfg, state):
    _request("POST", "/admin/reset", {"resource": cfg["resource"],
             "resource_id": cfg["resource_id"], "state_field": cfg["state_field"], "state": state})


def publish(topic, event):
    code, resp = _request("POST", "/publish", {"topic": topic, "event": event})
    return code, (resp.get("message_id") if isinstance(resp, dict) else None)


def resource_state(cfg):
    code, resp = _request("GET", f"/{cfg['resource']}/{cfg['resource_id']}")
    return resp.get(cfg["state_field"]) if (code == 200 and isinstance(resp, dict)) else None


def health_ok():
    code, resp = _request("GET", "/health")
    return code == 200 and bool(isinstance(resp, dict) and resp.get("ok"))


def logs_since(since):
    code, resp = _request("GET", f"/logs?since={since}")
    return resp.get("lines", []) if (code == 200 and isinstance(resp, dict)) else []


def consume_dlq(topic):
    code, resp = _request("POST", "/dlq/consume", {"topic": topic})
    return resp.get("message") if (code == 200 and isinstance(resp, dict)) else None


def run_reference_plan(cfg, plan):
    """Execute the canonical correct plan against the live substrate with real timing.
    Returns the raw observation dict eventdriven_spec.evaluate expects + a request log."""
    raw = {"wf_published": False, "wf_state_after": None, "wf_elapsed_s": None,
           "wf_consumer_errors": 0, "mf_published": False, "mf_health_ok": None,
           "mf_error_logged": False, "mf_in_dlq": False, "mf_state_after": None}
    reqlog = []

    # well-formed
    reset(cfg, cfg["pre_state"])
    t0 = time.monotonic()
    log_since = time.time() - 1.0
    code, wf_id = publish(cfg["topic"], plan["wellformed_event"])
    raw["wf_published"] = code in (200, 202)
    interval = plan["poll"]["interval_ms"] / 1000.0
    deadline = t0 + plan["poll"]["timeout_seconds"]
    state_after, elapsed = None, None
    while time.monotonic() < deadline:
        st = resource_state(cfg)
        if st == cfg["expected_state"]:
            state_after, elapsed = st, time.monotonic() - t0
            break
        time.sleep(interval)
    if state_after is None:
        state_after = resource_state(cfg)
    raw["wf_state_after"] = state_after
    raw["wf_elapsed_s"] = round(elapsed, 3) if elapsed is not None else None
    errs = [ln for ln in logs_since(log_since)
            if ln.get("level") in ("ERROR", "WARN")
            and (ln.get("message_id") == wf_id or ln.get("topic") == cfg["topic"])]
    raw["wf_consumer_errors"] = len(errs)
    reqlog.append({"phase": "wellformed", "message_id": wf_id, "state_after": state_after,
                   "elapsed_s": raw["wf_elapsed_s"], "consumer_errors": len(errs)})

    # malformed
    reset(cfg, cfg["pre_state"])
    log_since = time.time() - 0.001
    code, mf_id = publish(cfg["topic"], plan["malformed_event"])
    raw["mf_published"] = code in (200, 202)
    h_now = health_ok()
    time.sleep(min(HEALTH_SETTLE_SECONDS, 60))
    h_after = health_ok()
    raw["mf_health_ok"] = bool(h_now and h_after)

    bound = plan["assertions"]["error_log_within_seconds"]
    dl = time.monotonic() + min(bound, 15)
    error_logged = False
    while time.monotonic() < dl:
        for ln in logs_since(log_since):
            if ln.get("level") == "ERROR" and (
                    ln.get("message_id") == mf_id or (mf_id and str(mf_id) in str(ln.get("msg", "")))):
                error_logged = True
                break
        if error_logged:
            break
        time.sleep(0.2)
    raw["mf_error_logged"] = error_logged

    dlq_bound = plan["assertions"]["dlq_within_seconds"]
    dl = time.monotonic() + min(dlq_bound, 15)
    dlq_match, dlq_msg = False, None
    while time.monotonic() < dl:
        dlq_msg = consume_dlq(cfg["topic"])
        if dlq_msg is not None:
            dlq_match = (dlq_msg.get("message_id") == mf_id) or (dlq_msg.get("payload") == plan["malformed_event"])
            break
        time.sleep(0.2)
    raw["mf_in_dlq"] = bool(dlq_match)
    raw["mf_state_after"] = resource_state(cfg)
    reqlog.append({"phase": "malformed", "message_id": mf_id, "health_ok": raw["mf_health_ok"],
                   "error_logged": error_logged, "in_dlq": dlq_match, "dlq_consumed": dlq_msg,
                   "state_after": raw["mf_state_after"]})
    return raw, reqlog


def build_topics_config() -> dict:
    """The consumer contract the substrate loads (topics.json)."""
    return {"topics": [
        {"topic": t["topic"], "event_type": t["event_type"], "resource": t["resource"],
         "resource_id": t["resource_id"], "state_field": t["state_field"],
         "pre_state": t["pre_state"], "expected_state": t["expected_state"],
         "required_fields": list(t["required_fields"])}
        for t in eventdriven_spec.TOPICS]}


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each topic's event contract
    WITHOUT the answer plan."""
    return {
        "title": "Event-driven trigger contract (authored for the test-event-driven-api-triggers task)",
        "description": "Each topic carries a typed event whose payload must contain every "
                       "required field. A valid event drives resource/<resource_id>.<state_field> "
                       "from pre_state to expected_state within 5s; a malformed event (the one "
                       "drop_field omitted) must be ERROR-logged, dead-lettered within 30s, leave "
                       "the state unchanged, and never crash the consumer. Agents construct the "
                       "event-trigger test plan from this; ground truth is the live substrate's "
                       "observed behavior. DummyJSON is never modified and consumes no events, so "
                       "against DummyJSON the rates are 0% (the QA finding); the local substrate "
                       "implements the correct consumer so the contract is exercisable.",
        "target": BASE_URL,
        "topics": [
            {"topic": t["topic"], "resource": t["resource"], "resource_id": t["resource_id"],
             "state_field": t["state_field"], "pre_state": t["pre_state"],
             "expected_state": t["expected_state"], "event_type": t["event_type"],
             "required_fields": list(t["required_fields"]),
             "field_values": dict(t["field_values"]), "drop_field": t["drop_field"]}
            for t in eventdriven_spec.TOPICS]}


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # Always (re)write the substrate config + agent input from the single source of truth.
    (HERE / "topics.json").write_text(json.dumps(build_topics_config(), indent=2))
    (HERE / "eventdriven_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    # health gate
    if not health_ok():
        print(f"FATAL: event-driven substrate not reachable/healthy at {BASE_URL}", file=sys.stderr)
        sys.exit(2)

    consolidated = []
    total = correct = 0
    wf_total = wf_success = 0
    mf_total = mf_delivered = 0

    for t in eventdriven_spec.TOPICS:
        plan = eventdriven_spec.build_reference_plan(t)
        raw, reqlog = run_reference_plan(t, plan)
        observed = eventdriven_spec.evaluate(t, raw)

        scenarios = []
        for label in eventdriven_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = eventdriven_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": eventdriven_spec.ideal_for(label),
                              "observed_token": tok, "service_correct": ok})
            total += 1
            correct += 1 if ok else 0

        wf_total += 1
        if eventdriven_spec.event_processing_success(observed):
            wf_success += 1
        mf_total += 1
        if eventdriven_spec.dlq_delivered(observed):
            mf_delivered += 1

        rec = {"topic": t["topic"], "resource": t["resource"], "resource_id": t["resource_id"],
               "state_field": t["state_field"], "pre_state": t["pre_state"],
               "expected_state": t["expected_state"], "reference_plan": plan,
               "request_log": reqlog, "scenarios": scenarios}
        (GOLD_DIR / f"{t['topic']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    fidelity_rate = round(100.0 * correct / total, 2) if total else None
    event_processing_rate = round(100.0 * wf_success / wf_total, 2) if wf_total else None
    dlq_rate = round(100.0 * mf_delivered / mf_total, 2) if mf_total else None
    summary = {
        "target_local_substrate": BASE_URL,
        "topics": len(eventdriven_spec.TOPICS),
        "scenarios_per_topic": len(eventdriven_spec.SCENARIO_LABELS),
        "total_scenarios": total,
        "service_correct_scenarios": correct,
        "gold_contract_correctness_rate_pct": fidelity_rate,
        "event_processing_success_rate_pct": event_processing_rate,
        "dead_letter_queue_delivery_rate_pct": dlq_rate,
        "dummyjson_finding": {
            "event_processing_success_rate_pct": 0,
            "dead_letter_queue_delivery_rate_pct": 0,
            "note": "DummyJSON consumes no message topics, ships no consumer, no dead-letter "
                    "queue, and no consumer-liveness signal (only AWS usage is S3 object "
                    "storage). An event published nowhere changes nothing, so against "
                    "DummyJSON-as-the-system both rates are 0%. DummyJSON is never modified. "
                    "The local air-gapped substrate implements the correct consumer so the "
                    "documented contract is exercisable and the four frameworks are ranked on "
                    "fidelity-to-this-gold.",
        },
        "note": "Ground truth = live local-substrate observed token per (topic, scenario). The "
                "substrate implements the correct event-driven contract, so a correct test plan "
                "yields 100% on both headline rates; gaps in an agent's plan show up as lower "
                "fidelity-to-gold.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "topics": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
