"""Shared, deterministic plumbing for the four event-trigger-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the topic catalogue from data/test-event-driven-api-triggers/eventdriven_spec.json
  - build the compact per-topic event-contract brief handed to the agent
  - execute whatever plan the agent emitted against the LOCAL event-driven substrate
    (tools/eventbus_target/app.py) on loopback only (sandbox + host guards):
      * reset the resource to pre_state, publish the well-formed event, poll the resource
        every interval_ms up to timeout_seconds, time the transition, scan the consumer
        log for errors on that event
      * reset the resource, publish the malformed event, confirm the consumer stays
        healthy (no crash), an ERROR is logged naming the message id + parse error, the
        message lands in the DLQ (consume one and confirm it matches), and the resource
        state did not change
  - evaluate every scenario (shared eventdriven_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is never touched here: it has no event consumer, so the SYSTEM under test is
the local air-gapped substrate. The honest "DummyJSON consumes no events => 0%" finding
is recorded by the gold builder; this harness measures each framework's test against the
correct substrate.

The framework-specific part — turning one topic's brief into the event-trigger test plan
via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
EVENTBUS_BASE_URL = os.environ.get("FORGE_EVENTBUS_BASE_URL", "http://127.0.0.1:8930").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-event-driven-api-triggers" / "eventdriven_spec.json"

# The documented health-after window is 60s; for a runnable test the consumer-liveness
# settle window is configurable (default a few seconds). Gold and agents share the same
# value so the comparison holds. Production (real Kafka/SQS) uses the documented 60s.
HEALTH_SETTLE_SECONDS = float(os.environ.get("EVENTDRIVEN_HEALTH_SETTLE_SECONDS", "3"))
# Hard caps so a malformed plan can never make the harness wait forever.
MAX_POLL_TIMEOUT = 15.0
MAX_DLQ_WAIT = 15.0
MAX_LOG_WAIT = 15.0

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import eventdriven_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


# --------------------------------------------------------------------------- #
# G1 staging write
# --------------------------------------------------------------------------- #
def _write_staging_findings(
    agent: str,
    item_id: str,
    item_label: str,
    step_results: list[dict],
) -> None:
    """Write per-item step findings to the G1 staging directory.

    Path: results/runs/{RUN_ID}/staging/{agent}/{item_id}-findings.json

    Called once per item (endpoint / collection / scenario) after all steps
    for that item are complete. The G1b orchestration step reads these files
    and passes them to test-case-creator as evidence of what this agent observed.
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"
    _assert_sandbox(out_path)

    findings = []
    for i, r in enumerate(step_results, start=1):
        findings.append({
            "step_number": i,
            "item_id": item_id,
            "item_label": item_label,
            **r,
        })

    out_path.write_text(json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def topic_cfgs() -> list[dict]:
    spec = load_spec()
    out = list(spec["topics"])
    only = os.environ.get("FORGE_ONLY_TOPICS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["topic"] in wanted]
    return out


def topic_brief(cfg: dict) -> str:
    """Compact, unambiguous event contract handed to the LLM."""
    return "\n".join([
        f"topic: {cfg['topic']}",
        f"resource: {cfg['resource']}",
        f"resource_id: {cfg['resource_id']}",
        f"state_field: {cfg['state_field']}",
        f"pre_state: {cfg['pre_state']}",
        f"expected_state: {cfg['expected_state']}   # state the resource must reach after a valid event",
        f"event_type: {cfg['event_type']}",
        f"required_fields: {json.dumps(cfg['required_fields'])}",
        f"field_values: {json.dumps(cfg['field_values'])}   # exact value for each required field",
        f"drop_field: {cfg['drop_field']}   # omit this one required field to make the malformed event",
        "contract: a valid event carrying every required field drives "
        f"{cfg['resource']}/{cfg['resource_id']}.{cfg['state_field']} from {cfg['pre_state']} to "
        f"{cfg['expected_state']} within 5s; a malformed event (drop_field missing) must be "
        "ERROR-logged, dead-lettered within 30s, leave the state unchanged, and never crash the consumer.",
    ])


# --------------------------------------------------------------------------- #
# HTTP to the local substrate
# --------------------------------------------------------------------------- #
def _request(method: str, path: str, body: dict | None = None, timeout: float = 15.0):
    url = f"{EVENTBUS_BASE_URL}{path}"
    _assert_local_target(url)
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


def _reset(cfg: dict, state: str) -> None:
    _request("POST", "/admin/reset", {
        "resource": cfg["resource"], "resource_id": cfg["resource_id"],
        "state_field": cfg["state_field"], "state": state})


def _publish(topic: str, event) -> tuple[int, str | None]:
    code, resp = _request("POST", "/publish", {"topic": topic, "event": event})
    return code, (resp.get("message_id") if isinstance(resp, dict) else None)


def _resource_state(cfg: dict):
    code, resp = _request("GET", f"/{cfg['resource']}/{cfg['resource_id']}")
    if code != 200 or not isinstance(resp, dict):
        return None
    return resp.get(cfg["state_field"])


def _health_ok() -> bool:
    code, resp = _request("GET", "/health")
    return code == 200 and bool(isinstance(resp, dict) and resp.get("ok"))


def _logs_since(since: float) -> list[dict]:
    code, resp = _request("GET", f"/logs?since={since}")
    return resp.get("lines", []) if (code == 200 and isinstance(resp, dict)) else []


def _consume_dlq(topic: str) -> dict | None:
    code, resp = _request("POST", "/dlq/consume", {"topic": topic})
    return resp.get("message") if (code == 200 and isinstance(resp, dict)) else None


# --------------------------------------------------------------------------- #
# Plan execution (real timing)
# --------------------------------------------------------------------------- #
def _to_int(v, default=None):
    try:
        return int(v)
    except Exception:  # noqa
        return default


def _exec_plan(cfg: dict, plan: dict) -> tuple[dict, list]:
    """Execute the AGENT's plan against the local substrate with real timing. Tolerant of
    missing/malformed keys — whatever the agent omits is not exercised and the dependent
    scenarios score 'missing'. Returns (raw_obs, request_log)."""
    reqlog: list = []
    raw = {
        "wf_published": False, "wf_state_after": None, "wf_elapsed_s": None,
        "wf_consumer_errors": 0,
        "mf_published": False, "mf_health_ok": None, "mf_error_logged": False,
        "mf_in_dlq": False, "mf_state_after": None,
    }
    if not isinstance(plan, dict):
        return raw, reqlog

    topic = plan.get("topic") or cfg["topic"]
    wf_event = plan.get("wellformed_event") if isinstance(plan.get("wellformed_event"), dict) else None
    mf_event = plan.get("malformed_event") if isinstance(plan.get("malformed_event"), dict) else None
    poll = plan.get("poll") if isinstance(plan.get("poll"), dict) else {}
    interval_ms = _to_int(poll.get("interval_ms"), eventdriven_spec.POLL_INTERVAL_MS) or 500
    timeout_s = min(_to_int(poll.get("timeout_seconds"), eventdriven_spec.POLL_TIMEOUT_SECONDS) or 5,
                    MAX_POLL_TIMEOUT)

    # ---------- well-formed phase ----------
    if wf_event is not None:
        _reset(cfg, cfg["pre_state"])
        t_publish = time.monotonic()
        log_since = time.time() - 1.0  # task step 4: filter ts >= T_PUBLISH - 1s
        code, wf_msg_id = _publish(topic, wf_event)
        raw["wf_published"] = code in (200, 202)
        state_after = None
        elapsed = None
        deadline = t_publish + timeout_s
        while time.monotonic() < deadline:
            st = _resource_state(cfg)
            if st is not None and st == cfg["expected_state"]:
                state_after = st
                elapsed = time.monotonic() - t_publish
                break
            time.sleep(interval_ms / 1000.0)
        if state_after is None:
            state_after = _resource_state(cfg)  # final read for state_changed/value tokens
        raw["wf_state_after"] = state_after
        raw["wf_elapsed_s"] = round(elapsed, 3) if elapsed is not None else None
        # consumer errors for THIS event (match by message id; fall back to topic)
        errs = [ln for ln in _logs_since(log_since)
                if ln.get("level") in ("ERROR", "WARN")
                and (ln.get("message_id") == wf_msg_id or ln.get("topic") == topic)]
        raw["wf_consumer_errors"] = len(errs)
        reqlog.append({"phase": "wellformed", "message_id": wf_msg_id,
                       "state_after": state_after, "elapsed_s": raw["wf_elapsed_s"],
                       "consumer_errors": len(errs)})

    # ---------- malformed phase ----------
    if mf_event is not None:
        _reset(cfg, cfg["pre_state"])  # independent subject: pre-event state is pre_state
        log_since = time.time() - 0.001
        code, mf_msg_id = _publish(topic, mf_event)
        raw["mf_published"] = code in (200, 202)

        # (a) consumer does not crash: healthy now and still healthy after the settle window
        health_now = _health_ok()
        time.sleep(min(HEALTH_SETTLE_SECONDS, 60))
        health_after = _health_ok()
        raw["mf_health_ok"] = bool(health_now and health_after)

        # (b) ERROR logged within the bound naming the message id + parse error
        bound = min(_to_int((plan.get("assertions") or {}).get("error_log_within_seconds"),
                            eventdriven_spec.ERROR_LOG_WITHIN_SECONDS) or 30, MAX_LOG_WAIT)
        deadline = time.monotonic() + bound
        error_logged = False
        while time.monotonic() < deadline:
            for ln in _logs_since(log_since):
                if ln.get("level") == "ERROR" and (
                        ln.get("message_id") == mf_msg_id
                        or (mf_msg_id and str(mf_msg_id) in str(ln.get("msg", "")))):
                    error_logged = True
                    break
            if error_logged:
                break
            time.sleep(0.2)
        raw["mf_error_logged"] = error_logged

        # (c) malformed message in the DLQ within the bound (consume one, confirm match)
        dlq_bound = min(_to_int((plan.get("assertions") or {}).get("dlq_within_seconds"),
                                eventdriven_spec.DLQ_WITHIN_SECONDS) or 30, MAX_DLQ_WAIT)
        deadline = time.monotonic() + dlq_bound
        dlq_match = False
        dlq_msg = None
        while time.monotonic() < deadline:
            dlq_msg = _consume_dlq(topic)
            if dlq_msg is not None:
                dlq_match = (dlq_msg.get("message_id") == mf_msg_id) or (
                    dlq_msg.get("payload") == mf_event)
                break
            time.sleep(0.2)
        raw["mf_in_dlq"] = bool(dlq_match)

        # (d) resource state unchanged by the malformed event
        raw["mf_state_after"] = _resource_state(cfg)
        reqlog.append({"phase": "malformed", "message_id": mf_msg_id,
                       "health_ok": raw["mf_health_ok"], "error_logged": error_logged,
                       "in_dlq": dlq_match, "dlq_consumed": dlq_msg,
                       "state_after": raw["mf_state_after"]})

    return raw, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_eventdriven_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the event-trigger plan object (see eventdriven_spec): a dict
        with wellformed_event, malformed_event, poll, assertions, etc. The harness
        publishes the AGENT's planned events with real timing and evaluates every
        scenario. Whatever the agent fails to emit scores as 'missing'. generate may
        raise; recorded per-topic.
    """
    cfgs = topic_cfgs()
    all_cases = []
    total = correct = 0
    wf_total = wf_success = 0
    mf_total = mf_delivered = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        raw, reqlog = _exec_plan(cfg, plan)
        observed = eventdriven_spec.evaluate(cfg, raw)

        scenarios = []
        for label in eventdriven_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = eventdriven_spec.correct(label, tok)
            scenarios.append({"topic": cfg["topic"], "scenario": label,
                              "ideal": eventdriven_spec.ideal_for(label),
                              "observed_token": tok, "service_correct": ok})
            total += 1
            correct += 1 if ok else 0

        wf_total += 1
        if eventdriven_spec.event_processing_success(observed):
            wf_success += 1
        mf_total += 1
        if eventdriven_spec.dlq_delivered(observed):
            mf_delivered += 1

        all_cases.append({"topic": cfg["topic"], "resource": cfg["resource"],
                          "resource_id": cfg["resource_id"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["topic"]).strip("/").replace("/", "-").replace(".", "-") or "topic",
            item_label=str(cfg["topic"]),
            step_results=[
                {
                    "assertion_result": "PASS" if s.get("service_correct") else "FAIL",
                    "assertion_detail": (
                        f"scenario={s.get('scenario')} ideal={s.get('ideal')} "
                        f"observed={s.get('observed_token')}"
                    ),
                    **s,
                }
                for s in scenarios
            ],
        )

    fidelity_correct = correct  # vs the IDEAL; judge later overwrites metric_value w/ fidelity-to-gold
    event_processing_rate = round(100.0 * wf_success / wf_total, 2) if wf_total else 0.0
    dlq_delivery_rate = round(100.0 * mf_delivered / mf_total, 2) if mf_total else 0.0

    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": EVENTBUS_BASE_URL,
               "event_processing_success_rate_pct": event_processing_rate,
               "dead_letter_queue_delivery_rate_pct": dlq_delivery_rate,
               "wellformed_events": wf_total, "wellformed_succeeded": wf_success,
               "malformed_events": mf_total, "malformed_dead_lettered": mf_delivered,
               "scenarios_total": total, "scenarios_service_correct": fidelity_correct,
               "topics": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, event_processing_rate, str(cases_path), extra={
        "event_processing_success_rate_pct": event_processing_rate,
        "dead_letter_queue_delivery_rate_pct": dlq_delivery_rate,
        "scenarios_total": total})

    everos_note(agent, f"event-trigger-test run: event_processing={event_processing_rate}% "
                       f"dlq_delivery={dlq_delivery_rate}% over {len(cfgs)} topics ({total} scenarios)")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline Event
    Processing Success Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-event-driven-api-triggers" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "event_processing_success_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
    import re
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # noqa
        return None
