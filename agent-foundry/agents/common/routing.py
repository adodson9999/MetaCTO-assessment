"""Shared, deterministic plumbing for the four API-gateway-routing testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the route catalogue from data/test-api-gateway-routing/routing_spec.json
  - build the compact per-route brief handed to the agent (NO backend admin URLs)
  - execute whatever plan the agent emitted: reset every backend's request journal,
    (for the service-down route) stop the expected backend, send the planned request
    to the LOCAL gateway, read every backend's /__admin/requests journal, (re)start
    the backend, and record the real routing observation
  - evaluate every scenario (shared routing_spec.evaluate_*), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The gateway + backends are the air-gapped local stand-in for an API gateway fronting
one WireMock instance per service; the framework-specific part — turning one route's
brief into the routing plan via the model — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8920").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-api-gateway-routing" / "routing_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import routing_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def route_cfgs() -> list[dict]:
    spec = load_spec()
    services = spec["services"]
    out = []
    for r in spec["routes"]:
        out.append({
            "method": r["method"],
            "path": r["path"],
            "headers": dict(r["headers"]),
            "body": r.get("body"),
            "expected_backend": r["expected_backend"],
            "down_test": bool(r.get("down_test")),
            "services": list(services),
        })
    only = os.environ.get("FORGE_ONLY_ROUTES", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["path"] in wanted]
    return out


def _admin_urls() -> dict:
    return dict(load_spec().get("_services_admin", {}))


def route_brief(cfg: dict) -> str:
    """Compact, unambiguous routing contract handed to the model. Backend admin URLs
    are NEVER included — the agent only knows the documented gateway-facing contract."""
    body_repr = "none" if cfg.get("body") in (None, "") else json.dumps(cfg["body"])
    lines = [
        f"route_path: {cfg['path']}        # the gateway path to send the request to",
        f"method: {cfg['method'].upper()}",
        f"headers: {json.dumps(cfg['headers'])}   # send exactly these request headers",
        f"body: {body_repr}        # the request body to send (the literal 'none' means no body)",
        f"expected_backend: {cfg['expected_backend']}   # the one backend that must receive this request",
        f"all_services: {json.dumps(cfg['services'])}   # every downstream backend service, in order",
        f"down_test: {str(bool(cfg.get('down_test'))).lower()}   # if true this route's backend is stopped and the gateway must answer 503",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP helpers (gateway send, admin journal read/reset, down/up control)
# --------------------------------------------------------------------------- #
def _http(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None,
          timeout: float = 15.0):
    _assert_local(url)
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:  # noqa
        return -1, b""


def _reset_journals(admin: dict) -> None:
    for base in admin.values():
        _http("DELETE", f"{base.rstrip('/')}/__admin/requests")


def _read_journals(admin: dict) -> dict:
    out = {}
    for svc, base in admin.items():
        code, body = _http("GET", f"{base.rstrip('/')}/__admin/requests")
        reqs = []
        if code == 200:
            try:
                reqs = json.loads(body).get("requests", [])
            except Exception:  # noqa
                reqs = []
        out[svc] = reqs
    return out


def _control_down(service: str, down: bool) -> None:
    url = f"{TARGET_BASE_URL}/__control/down"
    data = json.dumps({"service": service}).encode()
    _http("PUT" if down else "DELETE", url, headers={"Content-Type": "application/json"}, data=data)


def _send_to_gateway(plan: dict, cfg: dict) -> dict | None:
    """Send the agent's planned request to the gateway and capture status + body +
    the body string sent. Returns None if the plan lacks a usable method/path."""
    method = plan.get("method") if isinstance(plan.get("method"), str) else None
    path = plan.get("route") if isinstance(plan.get("route"), str) else None
    if not method or not path:
        return None
    headers = plan.get("headers") if isinstance(plan.get("headers"), dict) else {}
    body_obj = plan.get("body")
    sent_body = "" if body_obj in (None, "") else json.dumps(body_obj)
    data = sent_body.encode() if sent_body else None
    url = f"{TARGET_BASE_URL}{path}"
    code, raw = _http(method, url, headers={str(k): str(v) for k, v in headers.items()}, data=data)
    return {"gateway_status": code, "gateway_body": raw.decode("utf-8", errors="replace"),
            "sent_body": sent_body}


def _execute(plan: dict, cfg: dict, admin: dict) -> tuple[dict | None, dict]:
    """Run one route's planned request with per-call isolation. Returns
    (exec_obs_for_routing_spec, request_log_entry)."""
    expected = cfg["expected_backend"]
    _reset_journals(admin)
    if cfg.get("down_test"):
        _control_down(expected, True)
    sent = _send_to_gateway(plan, cfg)
    journals = _read_journals(admin)
    if cfg.get("down_test"):
        _control_down(expected, False)

    if sent is None:
        return None, {"route": cfg["path"], "sent": False, "journals_total": sum(len(v) for v in journals.values())}

    obs = {"gateway_status": sent["gateway_status"], "gateway_body": sent["gateway_body"],
           "sent_body": sent["sent_body"], "journals": journals}
    log = {"route": cfg["path"], "sent": True, "gateway_status": sent["gateway_status"],
           "journal_counts": {k: len(v) for k, v in journals.items()},
           "down_test": bool(cfg.get("down_test"))}
    return obs, log


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
            data = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=data,
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
def run_routing_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the routing plan object for one route (see routing_spec): a
        dict with route/method/headers/body/expected_backend/other_backends/down_test.
        The harness resets every backend journal, (for the down route) stops the
        backend, sends the AGENT's planned request to the local gateway, reads every
        backend's journal, restarts the backend, and evaluates every scenario. Whatever
        the agent omits scores as 'missing'. generate may raise; recorded per route.
    """
    cfgs = route_cfgs()
    admin = _admin_urls()
    all_cases = []
    scenarios_total = scenarios_correct = 0
    routes_total = routes_forwarded = 0
    reqlog = []

    for cfg in cfgs:
        # Unique route identity = METHOD + path. Two routes can share a path (e.g.
        # PUT and GET /api/payments/9), so the path alone is not a safe scenario key.
        route_id = f"{cfg['method'].upper()} {cfg['path']}"
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        plan_obs = routing_spec.evaluate_plan(cfg, plan)
        exec_input, log = _execute(plan, cfg, admin)
        exec_obs = routing_spec.evaluate_exec(cfg, exec_input)
        log["route_id"] = route_id
        reqlog.append(log)

        observed = dict(plan_obs)
        observed.update(exec_obs)
        ideal = routing_spec.ideal_tokens(cfg)

        scenarios = []
        for label in routing_spec.scenarios_for(cfg):
            tok = observed.get(label, "missing")
            ok = routing_spec.correct(cfg, label, tok)
            scenarios.append({"route": route_id, "scenario": label,
                              "ideal": ideal.get(label), "observed_token": tok,
                              "api_correct": ok})
            scenarios_total += 1
            scenarios_correct += 1 if ok else 0

        routes_total += 1
        if routing_spec.forwarding_pass(cfg, exec_obs):
            routes_forwarded += 1

        all_cases.append({"route": route_id, "route_path": cfg["path"],
                          "method": cfg["method"],
                          "expected_backend": cfg["expected_backend"],
                          "down_test": cfg["down_test"], "emitted_plan": plan,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * routes_forwarded / routes_total, 2) if routes_total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "route_forwarding_accuracy_pct": rate,
           "routes_total": routes_total, "routes_forwarded": routes_forwarded,
           "scenarios_total": scenarios_total, "scenarios_api_correct": scenarios_correct,
           "request_log": reqlog, "routes": all_cases}

    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "route_forwarding_accuracy_pct": rate,
        "routes_total": routes_total, "routes_forwarded": routes_forwarded})

    everos_note(agent, f"api-gateway-routing run: route_forwarding_accuracy={rate}% "
                       f"over {routes_total} routes ({routes_forwarded} forwarded correctly)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline Route
    Forwarding Accuracy; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-api-gateway-routing" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "route_forwarding_accuracy_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary model text."""
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
