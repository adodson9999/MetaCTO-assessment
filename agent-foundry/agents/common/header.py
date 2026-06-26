"""Shared, deterministic plumbing for the four header-propagation-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue from data/validate-header-propagation/header_spec.json
  - build the compact per-endpoint brief handed to the agent
  - obtain a real bearer token via POST /auth/login (best-effort, read-only auth)
  - EXECUTE whatever plan the agent emitted against the LOCAL target only:
      * send the with-header request, capture response headers
      * send the no-header request, capture response headers + detect an auto-UUID
      * grep the captured API SERVER LOG file (FORGE_SERVER_LOG) for the sent id and
        for any auto-generated id
      * enumerate downstream service logs from the spec (DummyJSON = none) and grep each
  - evaluate every scenario (shared header_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified. The one POST endpoint is DummyJSON's
simulated, non-persisting create. Auth login is read-only.

The framework-specific part — turning one endpoint's brief into the propagation test
plan via the backend LLM — is injected as `generate(endpoint) -> plan dict`.
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
SERVER_LOG = os.environ.get("FORGE_SERVER_LOG", "")  # captured API-server stdout (winston JSON)
SPEC_PATH = WORKSPACE / "data" / "validate-header-propagation" / "header_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import header_spec  # noqa: E402

UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


# --------------------------------------------------------------------------- #
# Sandbox + host + method guards
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


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = list(spec["endpoints"])
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [e for e in out if e["name"] in wanted or e["path"] in wanted]
    return out


def downstream_log_paths() -> list[dict]:
    """[{name, log_path}] of downstream services. DummyJSON declares none."""
    spec = load_spec()
    return spec.get("downstream_services", [])


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous propagation contract handed to the LLM."""
    auth = "yes" if cfg.get("auth") else "no"
    body = cfg.get("body")
    lines = [
        f"endpoint_name: {cfg['name']}",
        f"method: {cfg['method']}",
        f"path: {cfg['path']}",
        f"auth_required: {auth}   # if yes, include an Authorization: Bearer {header_spec.TOKEN_PLACEHOLDER} header",
        f"correlation_id: {header_spec.CORR_ID}   # the fixed test id, used verbatim",
        f"header_name: {header_spec.HEADER_NAME}   # the exact correlation header name",
    ]
    if body is not None:
        lines.append(f"request_body: {json.dumps(body)}   # JSON body to send for this endpoint")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Auth + HTTP execution
# --------------------------------------------------------------------------- #
def _login_token() -> str | None:
    """Best-effort bearer token via POST /auth/login (DummyJSON default user)."""
    body = json.dumps({"username": "emilys", "password": "emilyspass", "expiresInMins": 30}).encode()
    url = f"{TARGET_BASE_URL}/auth/login"
    _assert_local_target(url)
    try:
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("accessToken") or data.get("token")
    except Exception:  # noqa
        return None


def _send(method: str, path: str, headers: dict, body, _retries: int = 2):
    """Send one request to the LOCAL target. Returns (status, response_headers dict).
    Small retry on transient connection failure; HTTP error codes are real responses."""
    if not isinstance(path, str) or not path.startswith("/"):
        return -1, {}
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = None
    hdrs = dict(headers) if isinstance(headers, dict) else {}
    if body is not None and str(method).upper() in ("POST", "PUT", "PATCH"):
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=str(method).upper(), headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.getcode(), {k: v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            return e.code, {k: v for k, v in (e.headers.items() if e.headers else [])}
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, {}


def _resp_corr_value(resp_headers: dict) -> str | None:
    """Case-insensitive lookup of the correlation header in a response."""
    for k, v in (resp_headers or {}).items():
        if str(k).lower() == header_spec.HEADER_NAME.lower():
            return v
    return None


def _subst_token(headers: dict, token: str | None) -> dict:
    if not isinstance(headers, dict):
        return {}
    if not token:
        return dict(headers)
    return {k: (str(v).replace(header_spec.TOKEN_PLACEHOLDER, token) if isinstance(v, str) else v)
            for k, v in headers.items()}


# --------------------------------------------------------------------------- #
# Log grep (file-based; the chosen ELK/grep substrate)
# --------------------------------------------------------------------------- #
def _grep_counts(log_path: str, needle: str) -> tuple[int, int]:
    """Return (exact_hits, modified_hits) for `needle` across a log file.
    modified = a lowercased or truncated variant present where the exact id is not."""
    if not needle or not log_path or not Path(log_path).exists():
        return 0, 0
    try:
        text = Path(log_path).read_text(errors="ignore")
    except Exception:  # noqa
        return 0, 0
    exact = text.count(needle)
    variants = {needle.lower(), needle[: max(1, len(needle) // 2)]} - {needle}
    modified = 0
    if exact == 0:
        for var in variants:
            if var and var in text:
                modified += text.count(var)
    return exact, modified


def _downstream_presence(needle: str) -> tuple[list[str], bool | None]:
    """(service names, all_have_id|None). DummyJSON declares no downstream services."""
    services = downstream_log_paths()
    names = [s["name"] for s in services]
    if not services or not needle:
        return names, None
    return names, all(_grep_counts(s.get("log_path", ""), needle)[0] > 0 for s in services)


# --------------------------------------------------------------------------- #
# Plan execution -> observations
# --------------------------------------------------------------------------- #
def _exec_plan(cfg: dict, plan: dict, token: str | None) -> dict:
    plan = plan if isinstance(plan, dict) else {}
    wh = plan.get("with_header_request") if isinstance(plan.get("with_header_request"), dict) else {}
    nh = plan.get("no_header_request") if isinstance(plan.get("no_header_request"), dict) else {}

    # --- with-header request ---
    with_obs = {"sent_id": None, "resp_corr_value": None,
                "api_log_hits_exact": 0, "api_log_hits_modified": 0}
    if wh.get("method") and wh.get("path"):
        sent_id = None
        for k, v in (wh.get("headers") or {}).items():
            if str(k).lower() == header_spec.HEADER_NAME.lower():
                sent_id = v
        with_obs["sent_id"] = sent_id
        _send(wh["method"], wh["path"], _subst_token(wh.get("headers", {}), token), wh.get("body"))
        time.sleep(0.6)  # let winston onFinished flush the log line
        if sent_id:
            ex, mod = _grep_counts(SERVER_LOG, sent_id)
            with_obs["api_log_hits_exact"], with_obs["api_log_hits_modified"] = ex, mod

    # re-send to read the response headers (kept separate so the log-flush sleep above
    # is not on the response-capture path); a single send would also work — DummyJSON
    # is idempotent for these probes (simulated create). Capture from a fresh send:
    if wh.get("method") and wh.get("path"):
        _st, rh = _send(wh["method"], wh["path"], _subst_token(wh.get("headers", {}), token), wh.get("body"))
        with_obs["resp_corr_value"] = _resp_corr_value(rh)

    # --- no-header request ---
    no_obs = {"resp_corr_value": None, "generated_is_uuidv4": False, "api_log_hits_generated": 0}
    if nh.get("method") and nh.get("path"):
        _st, rh = _send(nh["method"], nh["path"], _subst_token(nh.get("headers", {}), token), nh.get("body"))
        gen = _resp_corr_value(rh)
        no_obs["resp_corr_value"] = gen
        if gen:
            no_obs["generated_is_uuidv4"] = bool(UUID_V4_RE.match(str(gen).strip()))
            time.sleep(0.4)
            ex, _ = _grep_counts(SERVER_LOG, str(gen))
            no_obs["api_log_hits_generated"] = ex

    # --- downstream ---
    sent_id = with_obs["sent_id"]
    services, all_id = _downstream_presence(sent_id)
    _services2, all_gen = _downstream_presence(no_obs["resp_corr_value"])

    return {
        "with_header": with_obs,
        "no_header": no_obs,
        "downstream_services": services,
        "downstream_all_have_id": all_id,
        "downstream_all_have_generated": all_gen,
    }


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
def run_header_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(endpoint: dict) -> the propagation plan object (see header_spec): a dict
        with correlation_id, header_name, with_header_request, no_header_request, and
        assertions. The harness obtains a token, executes the AGENT's requests, greps
        the API server log, and evaluates every scenario. Whatever the agent fails to
        emit scores as a mismatch vs gold. generate may raise; recorded per-endpoint.
    """
    cfgs = endpoint_cfgs()
    token = _login_token()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        obs = _exec_plan(cfg, plan, token)
        observed = header_spec.evaluate(plan, cfg, obs)

        scenarios = []
        for label in header_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = header_spec.correct(label, tok)
            scenarios.append({"endpoint": cfg["name"], "scenario": label,
                              "ideal": header_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"endpoint": cfg["name"], "method": cfg["method"], "path": cfg["path"],
                          "emitted_plan": plan, "observations": obs,
                          "scenarios": scenarios, "error": gen_error})

    # Headline Header-Propagation Rate uses only the RUNTIME scenarios (the real
    # propagation behavior), not the plan-correctness scenarios.
    rt_total = rt_correct = 0
    for case in all_cases:
        for s in case["scenarios"]:
            if s["scenario"] in header_spec.RUNTIME_LABELS:
                rt_total += 1
                rt_correct += 1 if s["api_correct"] else 0
    rate = round(100.0 * rt_correct / rt_total, 2) if rt_total else 0.0

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "header_propagation_rate_pct": rate,
           "runtime_scenarios_total": rt_total, "runtime_scenarios_propagated": rt_correct,
           "scenarios_total": total, "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "header_propagation_rate_pct": rate,
        "scenarios_total": total})

    everos_note(agent, f"header-propagation run: propagation_rate={rate}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    header-propagation rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "validate-header-propagation" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "header_propagation_rate_pct"),
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
