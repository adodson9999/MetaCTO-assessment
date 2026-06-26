"""Shared, deterministic plumbing for the four correlation-ID-propagation agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the fixed correlation-ID propagation contract from
    data/validate-correlation-id-propagation/cid_spec.json and build the compact brief
  - obtain a real bearer token from POST /auth/login (read-only) and substitute it for
    the agent's literal "Bearer <valid_token>" placeholder
  - execute whatever plan the agent emitted: send the with-header request and the
    no-header request to the LOCAL target only (sandbox + host guards), with a fixed,
    harness-owned minimal body — capturing each response's X-Correlation-ID header
  - grep the captured API server log file (FORGE_API_LOG_PATH) for CORR_ID and for any
    generated UUID, and grep the per-downstream-service log files (which do not exist
    for DummyJSON) the same way
  - evaluate every scenario (shared cid_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified: the single POST is its simulated,
non-persisting create (MONGODB_URI unset); auth login is read-only.

The framework-specific part — turning the brief into the propagation test plan via the
backend LLM — is injected as `generate(brief) -> plan dict`.
"""
from __future__ import annotations

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
SPEC_PATH = WORKSPACE / "data" / "validate-correlation-id-propagation" / "cid_spec.json"
API_LOG_PATH = os.environ.get("FORGE_API_LOG_PATH", "")
DOWNSTREAM_LOG_DIR = os.environ.get("FORGE_DOWNSTREAM_LOG_DIR", "")

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import cid_spec  # noqa: E402

# A fixed, harness-owned minimal body for the POST. NOT agent-supplied — so the agent
# never fabricates product data, and the body is identical for every framework.
FIXED_POST_BODY = {"title": "forge-corr-probe"}


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
    if SPEC_PATH.exists():
        return json.loads(SPEC_PATH.read_text())
    # Fall back to the canonical in-code contract.
    return {
        "correlation_id": cid_spec.CORR_ID,
        "header_name": cid_spec.HEADER_NAME,
        "endpoint": cid_spec.ENDPOINT,
        "downstream_services": cid_spec.DOWNSTREAM_SERVICES,
        "uuid_v4_regex": cid_spec.UUID_V4_REGEX,
        "auth": {"login_endpoint": {"method": "POST", "path": "/auth/login"},
                 "scheme": "Bearer", "token_placeholder": cid_spec.TOKEN_PLACEHOLDER},
    }


def contract_brief(spec: dict) -> str:
    """Compact, unambiguous correlation-ID propagation contract handed to the LLM."""
    ep = spec["endpoint"]
    auth = spec.get("auth", {})
    ds = ", ".join(spec["downstream_services"])
    return "\n".join([
        f"correlation_id: {spec['correlation_id']}     # the verbatim id to propagate, never modify",
        f"header_name: {spec['header_name']}      # the exact correlation-id header, case preserved",
        f"endpoint.method: {ep['method']}",
        f"endpoint.path: {ep['path']}            # the endpoint under test",
        f"downstream_services: [{ds}]   # the services this endpoint is contracted to call",
        f"uuid_v4_regex: {spec['uuid_v4_regex']}",
        f"authorization: a bearer token is supplied; write it verbatim as "
        f"'{auth.get('token_placeholder', cid_spec.TOKEN_PLACEHOLDER)}' "
        "(a separate program substitutes a real token before sending)",
    ])


# --------------------------------------------------------------------------- #
# Auth (read-only) + HTTP execution
# --------------------------------------------------------------------------- #
def _login_token(spec: dict) -> str | None:
    auth = spec.get("auth", {})
    le = auth.get("login_endpoint", {"method": "POST", "path": "/auth/login"})
    creds = auth.get("creds", {"username": "emilys", "password": "emilyspass"})
    url = f"{TARGET_BASE_URL}{le['path']}"
    _assert_local_target(url)
    body = json.dumps(creds).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        return data.get("accessToken") or data.get("token")
    except Exception:  # noqa
        return None


def _send(method: str, path: str, headers: dict, body: dict | None):
    """Send one request to the local target. Returns (status, response_headers_dict)."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode(), {k: v for k, v in r.getheaders()}
    except urllib.error.HTTPError as e:
        return e.code, {k: v for k, v in (e.headers.items() if e.headers else [])}
    except Exception:  # noqa
        return -1, {}


def _resolve_token_placeholder(headers: dict, token: str | None) -> dict:
    """Replace the literal 'Bearer <valid_token>' with the real bearer token."""
    out = {}
    for k, v in (headers or {}).items():
        if isinstance(v, str) and "<valid_token>" in v and token:
            v = v.replace("<valid_token>", token)
        out[k] = v
    return out


def _header_value(resp_headers: dict, name: str) -> str | None:
    """Case-insensitive header lookup (HTTP header names are case-insensitive)."""
    if not isinstance(resp_headers, dict):
        return None
    low = {str(k).lower(): v for k, v in resp_headers.items()}
    return low.get(str(name).lower())


# --------------------------------------------------------------------------- #
# Log grepping (captured winston API log + per-downstream-service logs)
# --------------------------------------------------------------------------- #
def _read_log(path: str) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        return p.read_text(errors="replace").splitlines()
    except Exception:  # noqa
        return []


def _count_hits(lines: list[str], needle: str) -> int:
    if not needle:
        return 0
    return sum(1 for ln in lines if needle in ln)


def _downstream_log_path(service: str) -> str:
    if not DOWNSTREAM_LOG_DIR:
        return ""
    return str(Path(DOWNSTREAM_LOG_DIR) / f"{service}.log")


def _downstream_services_observed(spec: dict) -> int:
    """How many of the contracted downstream services actually exist (have a log)?
    DummyJSON calls none, so no downstream log files exist -> 0."""
    n = 0
    for svc in spec.get("downstream_services", []):
        p = _downstream_log_path(svc)
        if p and Path(p).exists():
            n += 1
    return n


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
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


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_cid_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(brief: str) -> the propagation test plan object (see cid_spec): a dict
    with the eight keys. The harness substitutes a real token, executes the agent's
    planned requests, greps the captured logs, and evaluates every scenario. Whatever
    the agent fails to emit scores as 'missing'. generate may raise; recorded.
    """
    spec = load_spec()
    brief = contract_brief(spec)
    corr_id = spec["correlation_id"]
    header_name = spec["header_name"]
    uuid_re = re.compile(spec["uuid_v4_regex"])

    try:
        plan = generate(brief) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    norm = cid_spec.plan_emits(plan)
    token = _login_token(spec)

    obs: dict = {"with_request_sent": False, "no_header_request_sent": False}
    reqlog = []

    # 1. with-header request
    if norm["with_req"]:
        wr = norm["with_req"]
        hdrs = _resolve_token_placeholder(wr["headers"], token)
        status, resp_headers = _send(wr["method"], wr["path"], hdrs, FIXED_POST_BODY)
        obs["with_request_sent"] = True
        obs["resp_header_value"] = _header_value(resp_headers, header_name)
        reqlog.append({"phase": "with_header", "method": wr["method"], "path": wr["path"],
                       "status": status, "resp_header_value": obs["resp_header_value"]})

    # 2. no-header request
    if norm["no_header_req"]:
        nr = norm["no_header_req"]
        hdrs = _resolve_token_placeholder(nr["headers"], token)
        status, resp_headers = _send(nr["method"], nr["path"], hdrs, FIXED_POST_BODY)
        obs["no_header_request_sent"] = True
        gen_val = _header_value(resp_headers, header_name)
        obs["no_header_resp_value"] = gen_val
        obs["no_header_is_uuid_v4"] = bool(gen_val and uuid_re.match(gen_val))
        reqlog.append({"phase": "no_header", "method": nr["method"], "path": nr["path"],
                       "status": status, "resp_header_value": gen_val})

    # 3. let winston flush (it logs on response-finished), then grep the captured logs
    time.sleep(1.0)
    api_lines = _read_log(API_LOG_PATH)
    inv_lines = _read_log(_downstream_log_path("inventory-service"))
    pay_lines = _read_log(_downstream_log_path("payment-service"))

    obs["api_log_hits_corr"] = _count_hits(api_lines, corr_id)
    obs["api_log_corr_unmodified"] = any(corr_id in ln for ln in api_lines)
    obs["inventory_log_hits_corr"] = _count_hits(inv_lines, corr_id)
    obs["payment_log_hits_corr"] = _count_hits(pay_lines, corr_id)
    obs["downstream_services_observed"] = _downstream_services_observed(spec)

    gen_uuid = obs.get("no_header_resp_value")
    if gen_uuid and obs.get("no_header_is_uuid_v4"):
        obs["api_log_hits_uuid"] = _count_hits(api_lines, gen_uuid)
        obs["inventory_log_hits_uuid"] = _count_hits(inv_lines, gen_uuid)
        obs["payment_log_hits_uuid"] = _count_hits(pay_lines, gen_uuid)
    else:
        obs["api_log_hits_uuid"] = obs["inventory_log_hits_uuid"] = obs["payment_log_hits_uuid"] = 0

    # 4. evaluate every scenario
    observed = cid_spec.evaluate(obs)
    scenarios = []
    total = correct = 0
    propagated = 0
    for label in cid_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = cid_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": cid_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0
        propagated += 1 if tok == "true" else 0

    propagation_rate = round(100.0 * propagated / total, 2) if total else 0.0

    raw = {
        "agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
        "correlation_id_propagation_rate_pct": propagation_rate,
        "scenarios_total": total, "scenarios_propagated": propagated,
        "scenarios_api_correct": correct,
        "emitted_plan": plan, "normalized_plan": norm, "observations": obs,
        "request_log": reqlog, "scenarios": scenarios,
        "token_obtained": bool(token), "error": gen_error,
        "api_log_path": API_LOG_PATH, "downstream_log_dir": DOWNSTREAM_LOG_DIR,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, propagation_rate, str(cases_path), extra={
        "correlation_id_propagation_rate_pct": propagation_rate,
        "scenarios_total": total})

    everos_note(agent, f"correlation-id-propagation run: propagation_rate={propagation_rate}% "
                       f"over {total} scenarios (propagated={propagated})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    propagation rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "validate-correlation-id-propagation" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "correlation_id_propagation_rate_pct"),
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
