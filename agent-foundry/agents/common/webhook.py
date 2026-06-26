"""Shared, deterministic plumbing for the four webhook-delivery testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It
is the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the subject catalogue from data/test-webhook-delivery/webhook_spec.json
  - start a LOCAL webhook receiver on 127.0.0.1:<ephemeral> (air-gapped; no ngrok)
    and inject its real URL into the per-subject brief
  - build the compact per-subject brief handed to the agent
  - execute whatever plan the agent emitted: POST the registration, POST the resource,
    poll the receiver for the matching delivery within the deadline, verify the
    delivered payload fields + the HMAC-SHA256 signature, and (only if a first
    delivery actually arrived) exercise the 500-then-retry path
  - evaluate every scenario (shared webhook_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON's SOURCE is never modified. Its POST /<x>/add endpoints are simulated
(echo a created object, persist nothing) and it has no /webhooks route, so executing
the plan against it cannot mutate it. Where the idealized webhook contract is unmet
(no registration endpoint, no delivery, no signature) the recorded token is the QA
finding, not an agent fault.

The framework-specific part — turning one subject's brief into the webhook test plan
via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
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
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-webhook-delivery" / "webhook_spec.json"

# Bound the retry wait so even a webhook-capable target run cannot block for minutes.
# The plan still carries the documented 60s (that value is what fidelity scores); the
# harness execution sleeps min(plan_wait, this cap). Default small for the sandbox.
RETRY_WAIT_CAP_S = int(os.environ.get("FORGE_WEBHOOK_RETRY_WAIT", "5"))

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import webhook_spec  # noqa: E402
from webhook_receiver import WebhookReceiver  # noqa: E402


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
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def subject_cfgs(receiver_url: str) -> list[dict]:
    spec = load_spec()
    out = []
    for s in spec["subjects"]:
        out.append({
            "resource": s["resource"],
            "webhooks_path": spec.get("webhooks_path", "/webhooks"),
            "resource_path": s["resource_path"],
            "resource_body": s["resource_body"],
            "receiver_url": receiver_url,
        })
    only = os.environ.get("FORGE_ONLY_SUBJECTS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["resource"] in wanted or c["resource_path"] in wanted]
    return out


def subject_brief(cfg: dict) -> str:
    """Compact, unambiguous webhook contract handed to the LLM."""
    return "\n".join([
        f"resource: {cfg['resource']}",
        f"webhooks_path: {cfg['webhooks_path']}   # POST here to register a receiver",
        f"resource_path: {cfg['resource_path']}   # POST here to create one resource",
        f"resource_body: {json.dumps(cfg['resource_body'])}   # a valid creation body",
        f"receiver_url: {cfg['receiver_url']}   # the receiver to register, copy verbatim",
        f"event_type: {webhook_spec.EVENT_TYPE}",
        f"events: {json.dumps(webhook_spec.EVENTS)}",
        f"delivery_deadline_seconds: {webhook_spec.DELIVERY_DEADLINE_SECONDS}",
        f"poll_interval_ms: {webhook_spec.POLL_INTERVAL_MS}",
        f"signature_headers: {json.dumps(webhook_spec.SIGNATURE_HEADERS)}",
        f"signature_algorithm: {webhook_spec.SIGNATURE_ALGORITHM}",
        f"signature_format: {webhook_spec.SIGNATURE_FORMAT}",
        f"timestamp_regex: {webhook_spec.TIMESTAMP_REGEX}",
        f"retry_trigger_status: {webhook_spec.RETRY_TRIGGER_STATUS}",
        f"retry_wait_seconds: {webhook_spec.RETRY_WAIT_SECONDS}",
        "contract: registering the receiver and then creating a resource fires a "
        "resource.created event delivered to the receiver within the deadline, carrying "
        "the exact event_type, the created resource_id, an ISO-8601 timestamp, and an "
        "HMAC-SHA256 signature over the raw body keyed by the registered webhook_secret; "
        "a 500 from the receiver is retried.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (POST to the local target) + plan execution
# --------------------------------------------------------------------------- #
def _post(path: str, body: dict, _retries: int = 1):
    """POST a JSON body to the local target. Returns (status, parsed_json_or_None,
    raw_text). DummyJSON's /<x>/add is simulated and persists nothing; /webhooks 404s.
    Real HTTP error codes are returned as-is; only transient connection failures retry."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = json.dumps(body or {}).encode()
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.getcode(), _safe_json(raw), raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace") if e.fp else ""
            return e.code, _safe_json(raw), raw
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None, ""


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa
        return None


def _capture_id(obj) -> str | None:
    if isinstance(obj, dict):
        for k in ("id", "_id", "resource_id", "resourceId"):
            if k in obj and obj[k] not in (None, ""):
                return str(obj[k])
    return None


def _verify_signature(secret: str | None, raw_body: bytes, headers: dict) -> bool:
    """header value == "sha256=" + hex(hmac_sha256(secret, raw_body))."""
    if not secret:
        return False
    header_val = None
    for name in webhook_spec.SIGNATURE_HEADERS:
        for k, v in headers.items():
            if k.lower() == name.lower():
                header_val = v
                break
        if header_val:
            break
    if not header_val:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(header_val).strip(), expected)


def _matching_delivery(events: list[dict], resource_id: str | None) -> dict | None:
    """First inbound delivery whose JSON body resource_id equals the created id."""
    for ev in events:
        payload = _safe_json(ev["raw_body"].decode("utf-8", "replace")) if ev.get("raw_body") else None
        if isinstance(payload, dict):
            rid = payload.get("resource_id", payload.get("resourceId"))
            if resource_id is not None and str(rid) == str(resource_id):
                return {**ev, "payload": payload}
    return None


def _exec_plan(cfg: dict, plan: dict) -> dict:
    """Execute the AGENT's plan against the live local target and the local receiver.
    Tolerant of missing/malformed keys — whatever the agent omits is not sent and the
    dependent scenarios score 'missing'. Returns the raw observation dict that
    webhook_spec.evaluate expects, plus a request log under '_log'."""
    obs = {
        "register_status": None, "resource_status": None, "resource_id": None,
        "delivered": False, "delivery_seconds": None,
        "delivered_event_type": None, "delivered_resource_id": None,
        "delivered_timestamp_ok": False, "signature_valid": False,
        "retry_attempted": False, "retry_redelivered": False, "_log": [],
    }
    if not isinstance(plan, dict):
        return obs

    receiver = WebhookReceiver(path="/hook").start()
    try:
        # 1. register the webhook (POST). Capture webhook_secret if the API returns one.
        reg = plan.get("register") if isinstance(plan.get("register"), dict) else None
        secret = None
        if reg and reg.get("method") == "POST" and reg.get("path"):
            reg_body = reg.get("body") if isinstance(reg.get("body"), dict) else {}
            status, rj, _ = _post(reg["path"], reg_body)
            obs["register_status"] = status
            if isinstance(rj, dict):
                secret = rj.get("webhook_secret") or rj.get("secret")
            obs["_log"].append({"step": "register", "path": reg["path"], "status": status})

        # 2. create the resource (POST). Capture the resource_id; mark T_EVENT.
        trig = plan.get("trigger") if isinstance(plan.get("trigger"), dict) else None
        resource_id = None
        t_event = None
        if trig and trig.get("method") == "POST" and trig.get("path"):
            trig_body = trig.get("body") if isinstance(trig.get("body"), dict) else {}
            status, rj, _ = _post(trig["path"], trig_body)
            t_event = time.monotonic()
            obs["resource_status"] = status
            resource_id = _capture_id(rj)
            obs["resource_id"] = resource_id
            obs["_log"].append({"step": "trigger", "path": trig["path"],
                                "status": status, "resource_id": resource_id})

        # 3. poll the receiver for the matching delivery within the deadline.
        poll = plan.get("poll") if isinstance(plan.get("poll"), dict) else {}
        interval_ms = poll.get("interval_ms") if isinstance(poll.get("interval_ms"), int) else webhook_spec.POLL_INTERVAL_MS
        timeout_s = poll.get("timeout_seconds") if isinstance(poll.get("timeout_seconds"), int) else webhook_spec.DELIVERY_DEADLINE_SECONDS
        timeout_s = min(timeout_s, webhook_spec.DELIVERY_DEADLINE_SECONDS)  # never exceed the contract deadline
        deadline = (t_event or time.monotonic()) + timeout_s
        match = None
        while time.monotonic() < deadline:
            match = _matching_delivery(receiver.events(), resource_id)
            if match:
                break
            time.sleep(max(interval_ms, 50) / 1000.0)

        # 4. verify the delivered payload + HMAC signature.
        if match and t_event is not None:
            obs["delivered"] = True
            obs["delivery_seconds"] = round(match["recv_monotonic"] - t_event, 3)
            payload = match["payload"]
            obs["delivered_event_type"] = payload.get("event_type")
            obs["delivered_resource_id"] = payload.get("resource_id", payload.get("resourceId"))
            ts = payload.get("timestamp")
            obs["delivered_timestamp_ok"] = bool(isinstance(ts, str) and re.match(webhook_spec.TIMESTAMP_REGEX, ts))
            obs["signature_valid"] = _verify_signature(secret, match["raw_body"], match["headers"])
            obs["_log"].append({"step": "delivery", "delivery_seconds": obs["delivery_seconds"],
                                "signature_valid": obs["signature_valid"]})

        # 5. retry path — ONLY when a first delivery actually arrived (so a no-webhook
        #    target like DummyJSON never blocks on the wait). Fresh receiver fails the
        #    first delivery with 500, then we wait (bounded) for a redelivery.
        retry = plan.get("retry") if isinstance(plan.get("retry"), dict) else None
        if obs["delivered"] and retry and trig:
            obs["retry_attempted"] = True
            rcv2 = WebhookReceiver(path="/hook", fail_first=1).start()
            try:
                reg2 = dict(reg or {})
                reg2_body = dict((reg or {}).get("body") or {})
                reg2_body["url"] = rcv2.url
                _post(reg2.get("path", cfg["webhooks_path"]), reg2_body)
                status, rj2, _ = _post(trig["path"], trig.get("body") or {})
                rid2 = _capture_id(rj2)
                plan_wait = retry.get("wait_seconds")
                wait = min(plan_wait if isinstance(plan_wait, int) and plan_wait > 0 else RETRY_WAIT_CAP_S,
                           RETRY_WAIT_CAP_S)
                t_end = time.monotonic() + wait + webhook_spec.DELIVERY_DEADLINE_SECONDS
                while time.monotonic() < t_end:
                    matches = [e for e in rcv2.events()
                               if (lambda p: isinstance(p, dict) and str(p.get("resource_id")) == str(rid2))
                               (_safe_json(e["raw_body"].decode("utf-8", "replace")))]
                    if len(matches) >= 2:  # the 500'd delivery + at least one retry
                        obs["retry_redelivered"] = True
                        break
                    time.sleep(0.5)
            finally:
                rcv2.stop()
    finally:
        receiver.stop()
    return obs


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
def run_webhook_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the webhook test plan object (see webhook_spec): a dict with
        `register`, `trigger`, `poll`, `assertions`, and `retry`. The harness starts a
        local receiver, executes the AGENT's plan, verifies delivery + HMAC, and
        evaluates every scenario. Whatever the agent fails to emit scores as 'missing'.
        generate may raise; recorded per-subject.
    """
    # One receiver URL for briefing/fidelity; each _exec_plan run also starts its own
    # receiver to actually catch deliveries. The brief URL is what the plan must copy.
    brief_receiver = WebhookReceiver(path="/hook").start()
    receiver_url = brief_receiver.url
    brief_receiver.stop()

    cfgs = subject_cfgs(receiver_url)
    all_cases = []
    total = correct = 0
    deliveries = 0
    deliveries_all_fields_ok = 0
    retry_events = 0
    retry_redelivered = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        exec_obs = _exec_plan(cfg, plan)
        observed = webhook_spec.evaluate(cfg, plan, exec_obs)

        # headline accounting (the task's stated metrics)
        if exec_obs.get("delivered"):
            deliveries += 1
            on_time = (exec_obs.get("delivery_seconds") or 1e9) <= webhook_spec.DELIVERY_DEADLINE_SECONDS
            if (on_time and exec_obs.get("delivered_event_type") == webhook_spec.EVENT_TYPE
                    and str(exec_obs.get("delivered_resource_id")) == str(exec_obs.get("resource_id"))
                    and exec_obs.get("delivered_timestamp_ok") and exec_obs.get("signature_valid")):
                deliveries_all_fields_ok += 1
        if exec_obs.get("retry_attempted"):
            retry_events += 1
            if exec_obs.get("retry_redelivered"):
                retry_redelivered += 1

        scenarios = []
        for label in webhook_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = webhook_spec.correct(label, tok)
            scenarios.append({"subject": cfg["resource"], "scenario": label,
                              "ideal": webhook_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        log = exec_obs.pop("_log", [])
        all_cases.append({"subject": cfg["resource"], "resource_path": cfg["resource_path"],
                          "webhooks_path": cfg["webhooks_path"], "receiver_url": receiver_url,
                          "emitted_plan": plan, "exec_obs": exec_obs, "request_log": log,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    delivery_success_rate = round(100.0 * deliveries_all_fields_ok / len(cfgs), 2) if cfgs else 0.0
    retry_rate = round(100.0 * retry_redelivered / retry_events, 2) if retry_events else None

    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "webhook_contract_correctness_rate_pct": rate,
               "webhook_delivery_success_rate_pct": delivery_success_rate,
               "retry_delivery_rate_pct": retry_rate,
               "subjects_total": len(cfgs), "deliveries_received": deliveries,
               "deliveries_all_fields_ok": deliveries_all_fields_ok,
               "scenarios_total": total, "scenarios_api_correct": correct,
               "subjects": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "webhook_contract_correctness_rate_pct": rate,
        "webhook_delivery_success_rate_pct": delivery_success_rate,
        "retry_delivery_rate_pct": retry_rate,
        "scenarios_total": total})

    everos_note(agent, f"webhook-delivery run: contract_correctness={rate}% "
                       f"delivery_success={delivery_success_rate}% over {len(cfgs)} subjects "
                       f"({total} scenarios); deliveries={deliveries}")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    contract-correctness rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-webhook-delivery" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "webhook_contract_correctness_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
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
