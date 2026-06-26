"""Shared, deterministic plumbing for the four rate-limit-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue from data/test-rate-limit-enforcement/ratelimit_spec.json
  - build the compact per-endpoint brief handed to the agent
  - execute whatever plan the agent emitted with READ-ONLY GET requests to the
    LOCAL target only (sandbox + host + method guards): fire the at_limit burst,
    the single over_limit request, parse the Retry-After header, then sleep to the
    two real wall-clock probe offsets and fire them
  - evaluate every scenario (shared ratelimit_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified: GET only, no body, no mutation.
Firing limit_n+1 read-only GETs in a tight loop does not change the target.

The framework-specific part — turning one endpoint's brief into the rate-limit
test plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-rate-limit-enforcement" / "ratelimit_spec.json"

# Safety cap so a malformed plan can never fire an unbounded burst at the target.
MAX_BURST = 1000

# DummyJSON's limiter is global per client key (X-Forwarded-For under trust-proxy). To
# keep the four agents from sharing one 100/10s bucket when they run in parallel, the
# harness sends a client key that is ISOLATED per (agent, endpoint): a synthetic private
# IP whose second octet identifies the agent and third octet the endpoint. The gold
# reference uses octet 9. This is a test-harness isolation detail — observed tokens are
# bucket BEHAVIOR (100/10s), identical for any private bucket, so fidelity vs gold holds.
_AGENT_OCTET = {
    "langgraph": 1, "crewai": 2, "claude_sdk": 3,
    "api-tester-test-rate-limit-enforcement": 4,
}


def _client_ip(agent: str, endpoint_index: int) -> str:
    a = _AGENT_OCTET.get(agent, 8)
    return f"10.{a}.{(endpoint_index % 250) + 1}.1"


# Re-burst at most this many times if a burst straddles a global window reset and so fails
# to accumulate N requests in one window (the limiter then does not trip).
_BURST_ATTEMPTS = 3


def _sync_to_fresh_window(path: str, headers: dict, window_seconds: int) -> None:
    """Wait to just past the current global window boundary so the next burst starts on a
    full window. Prime once, read X-RateLimit-Reset, sleep to the boundary + a small margin.
    Best-effort: if the header is absent the call is a no-op."""
    _, _, reset0 = _get(path, headers)
    r0 = _to_int(reset0)
    if r0 is not None:
        wait = (r0 - time.time()) + 0.4
        if 0 < wait <= window_seconds + 2:
            time.sleep(wait)

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import ratelimit_spec  # noqa: E402


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
    out = []
    for e in spec["endpoints"]:
        out.append({
            "endpoint": e["endpoint"],
            "api_key_value": e.get("api_key_value", "forge-test-key"),
            "method": spec.get("method", "GET"),
            "success_code": spec.get("success_code", 200),
            "limit_n": spec.get("limit_n", ratelimit_spec.DEFAULT_LIMIT_N),
            "window_seconds": spec.get("window_seconds", ratelimit_spec.DEFAULT_WINDOW_SECONDS),
            "api_key_header": spec.get("api_key_header", "x-api-key"),
            "retry_after_header": spec.get("retry_after_header", "Retry-After"),
        })
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["endpoint"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous rate-limit contract handed to the LLM."""
    return "\n".join([
        f"endpoint_path: {cfg['endpoint']}",
        f"method: {cfg['method']}",
        f"success_code: {cfg['success_code']}   # status a non-throttled request returns",
        f"limit_n: {cfg['limit_n']}             # documented requests allowed per window per api key",
        f"window_seconds: {cfg['window_seconds']}      # window length in seconds",
        f"api_key_header: {cfg['api_key_header']}   # header that carries the api key",
        f"api_key_value: {cfg['api_key_value']}",
        f"retry_after_header: {cfg['retry_after_header']}   # header advertising the wait before retry",
        "contract: at most limit_n requests succeed per window per api key; request number "
        "limit_n+1 should return 429 carrying a positive-integer Retry-After header; the limit "
        "clears once the window has elapsed.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (read-only GET) + plan execution
# --------------------------------------------------------------------------- #
def _get(path: str, headers: dict, _retries: int = 5):
    """Read-only GET. Returns (status_code, retry_after_value_or_None). A real HTTP
    error code (e.g. 429) is a real response and is returned as-is with its headers;
    only transient connection failures (status -1, e.g. ECONNRESET under burst load)
    retry with backoff so a momentary target hiccup never surfaces as a corrupted
    observation. HTTP status codes are never retried."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    last = -1
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")  # GET only — never mutate the target
        for k, v in (headers or {}).items():
            if k and v is not None:
                req.add_header(k, str(v))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                h = r.headers
                return r.getcode(), h.get("Retry-After"), h.get("X-RateLimit-Reset")
        except urllib.error.HTTPError as e:
            h = e.headers
            return e.code, (h.get("Retry-After") if h else None), (h.get("X-RateLimit-Reset") if h else None)
        except Exception:  # noqa  -- connection refused/reset/timeout: retry with backoff
            last = -1
            if attempt < _retries:
                time.sleep(0.3 * (attempt + 1))
    return last, None, None


def _to_int(v):
    try:
        return int(v)
    except Exception:  # noqa
        return None


def _exec_plan(cfg: dict, plan: dict, agent: str, endpoint_index: int) -> tuple[dict, list]:
    """Execute the AGENT's plan (read-only) with real timing. Tolerant of
    missing/malformed keys — whatever the agent omits is not sent and the dependent
    scenarios score 'missing'. Returns (raw_obs, request_log)."""
    reqlog: list = []
    raw = {
        "at_limit_statuses": None, "over_status": None, "over_retry_after": None,
        "first_429_ordinal": None, "sequence_ran": False,
        "within_status": None, "after_status": None,
    }
    if not isinstance(plan, dict):
        return raw, reqlog

    # The client-key header name comes from the plan/brief (X-Forwarded-For); its VALUE
    # is the harness's per-(agent,endpoint) isolated IP so parallel agents never share a
    # rate-limit bucket. The plan's echoed api_key_value is the nominal documented client
    # id and is recorded, but the wire value is the isolated one.
    header_name = plan.get("api_key_header") or cfg["api_key_header"]
    headers = {header_name: _client_ip(agent, endpoint_index)}
    path = cfg["endpoint"]

    at_limit = plan.get("at_limit") if isinstance(plan.get("at_limit"), dict) else None
    over = plan.get("over_limit") if isinstance(plan.get("over_limit"), dict) else None
    if at_limit is None or over is None:
        return raw, reqlog  # without the burst + over request the sequence is not run

    n = _to_int(at_limit.get("count"))
    if n is None or n < 0:
        return raw, reqlog
    n = min(n, MAX_BURST)
    over_count = _to_int(over.get("count")) or 0

    # 0-2. Sync to a fresh window, fire the at-limit burst + the single over-limit request.
    #      DummyJSON's limiter (express-rate-limit MemoryStore) uses a GLOBAL wall-clock-
    #      aligned window shared across keys; a burst that straddles a reset boundary never
    #      accumulates N in one window, so the limit won't trip. If the over request is not
    #      429 while the limiter is active, the burst straddled — re-sync and re-burst (up to
    #      _BURST_ATTEMPTS times) so the measurement is robust. The plan asks for exactly N+1
    #      requests; a re-burst is a harness reliability detail, not a change to the contract.
    statuses: list = []
    first_429_ordinal = None
    over_status, over_retry, over_reset = (None, None, None)
    t_over = None
    for attempt in range(_BURST_ATTEMPTS):
        _sync_to_fresh_window(path, headers, cfg["window_seconds"])
        statuses, first_429_ordinal = [], None
        for i in range(n):
            status, _, _ = _get(path, headers)
            statuses.append(status)
            if status == 429 and first_429_ordinal is None:
                first_429_ordinal = i + 1
        over_status, over_retry, over_reset = _get(path, headers)
        t_over = time.monotonic()
        if over_status == 429 and first_429_ordinal is None:
            first_429_ordinal = n + 1
        if over_status == 429 or attempt == _BURST_ATTEMPTS - 1:
            break  # tripped cleanly, or out of attempts — accept this measurement

    raw["at_limit_statuses"] = statuses
    raw["over_status"] = over_status
    raw["over_retry_after"] = over_retry
    raw["over_reset_epoch"] = over_reset
    raw["first_429_ordinal"] = first_429_ordinal
    raw["sequence_ran"] = True
    reqlog.append({"label": "at_limit", "count": n, "statuses": statuses})
    reqlog.append({"label": "over_limit", "ordinal": n + 1,
                   "status": over_status, "retry_after": over_retry, "reset_epoch": over_reset})

    # 3. Find the moment the window actually closes, then fire the two probes at their real
    #    wall-clock offsets relative to it. DummyJSON's limiter uses a global wall-clock-
    #    aligned window, so Retry-After is a CONSTANT (= windowMs/1000), NOT the true time
    #    remaining; X-RateLimit-Reset (epoch) is the authoritative close time. Anchor on it
    #    so the probes are deterministic regardless of where the burst lands in the window.
    #    Fall back to Retry-After, then the documented window_seconds.
    secs_to_close = None
    reset_epoch = _to_int(over_reset)
    if reset_epoch is not None:
        secs_to_close = reset_epoch - time.time()
    if secs_to_close is None or secs_to_close < 0:
        retry_secs = _to_int(over_retry)
        secs_to_close = retry_secs if (retry_secs is not None and retry_secs > 0) else cfg["window_seconds"]
    secs_to_close = max(0.0, min(secs_to_close, cfg["window_seconds"] + 2))
    window_close = (t_over if t_over is not None else time.monotonic()) + secs_to_close

    for pr in plan.get("probes", []) if isinstance(plan.get("probes"), list) else []:
        if not isinstance(pr, dict) or "label" not in pr:
            continue
        offset = _to_int(pr.get("offset_seconds")) or 0
        fire_at = window_close + offset
        delay = fire_at - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, cfg["window_seconds"] + 5))  # bounded sleep, never runaway
        status, retry, reset = _get(path, headers)
        if pr["label"] == "within_window":
            raw["within_status"] = status
        elif pr["label"] == "after_window":
            raw["after_status"] = status
        reqlog.append({"label": pr["label"], "offset_seconds": offset,
                       "status": status, "retry_after": retry, "reset_epoch": reset})

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
def run_ratelimit_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the rate-limit plan object (see ratelimit_spec): a dict
        with `at_limit` ({label, count}), `over_limit` ({label, count}), and `probes`
        (each {label, offset_seconds}). The harness executes the AGENT's planned
        requests with real timing and evaluates every scenario. Whatever the agent
        fails to emit scores as 'missing'. generate may raise; recorded per-endpoint.
    """
    cfgs = endpoint_cfgs()
    all_cases = []
    total = correct = 0
    any_429 = False
    trigger = {}
    precision_all_pass = True

    for idx, cfg in enumerate(cfgs):
        # No inter-endpoint wait: each (agent, endpoint) gets its own isolated client-key
        # bucket (see _client_ip), so endpoints never contend for the same rate-limit
        # window — the "reset state between subjects" step is realized by bucket isolation.
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        raw, reqlog = _exec_plan(cfg, plan, agent, idx)
        observed = ratelimit_spec.evaluate(cfg["limit_n"], raw)

        ordinal = raw.get("first_429_ordinal")
        trigger[cfg["endpoint"]] = ordinal if ordinal is not None else "none"
        if ordinal == cfg["limit_n"] + 1:
            pass
        else:
            precision_all_pass = False
        if raw.get("first_429_ordinal") is not None or any(
                s == 429 for s in (raw.get("at_limit_statuses") or [])):
            any_429 = True

        scenarios = []
        for label in ratelimit_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = ratelimit_spec.correct(label, tok, cfg["limit_n"])
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": ratelimit_spec.ideal_for(label, cfg["limit_n"]),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"endpoint": cfg["endpoint"], "api_key_value": cfg["api_key_value"],
                          "limit_n": cfg["limit_n"], "window_seconds": cfg["window_seconds"],
                          "trigger_ordinal": trigger[cfg["endpoint"]],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "rate_limit_contract_correctness_rate_pct": rate,
               "rate_limit_enforced": any_429,
               "trigger_precision_overall_pass": (precision_all_pass and any_429),
               "rate_limit_trigger_precision": trigger,
               "scenarios_total": total, "scenarios_api_correct": correct,
               "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "rate_limit_contract_correctness_rate_pct": rate,
        "rate_limit_enforced": any_429,
        "trigger_precision_overall_pass": (precision_all_pass and any_429),
        "scenarios_total": total})

    everos_note(agent, f"rate-limit-test run: correctness_rate={rate}% "
                       f"enforced={any_429} over {len(cfgs)} endpoints ({total} scenarios)")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    contract-correctness rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-rate-limit-enforcement" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "rate_limit_contract_correctness_rate_pct"),
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
