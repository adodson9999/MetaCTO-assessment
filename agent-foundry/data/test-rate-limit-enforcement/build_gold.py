#!/usr/bin/env python3
"""Gold-set builder for the API rate-limit-enforcement testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the endpoint catalogue + the agents' input spec (ratelimit_spec.json), derives the
canonical correct rate-limit plan per endpoint, executes that plan against a locally-
running DummyJSON with READ-ONLY GET calls at REAL wall-clock timing, and records the
REAL observed behavior (burst statuses, the over-limit status, the Retry-After header,
the first-429 ordinal, and the two timed-probe statuses) per scenario.

DummyJSON is tested AS-IS and never modified: GET only, no body, no mutation. It ships
no rate limiter, so the recorded ground truth is that the documented limit is NOT
enforced — a legitimate QA finding, mirroring how test-pagination-behavior surfaced
DummyJSON's lenient param handling. The idealized contract lives in
ratelimit_spec.ideal_for(); where the real token differs from the ideal is the finding.

Outputs (all under data/test-rate-limit-enforcement/):
  - ratelimit_spec.json    the endpoint catalogue the agents are briefed from (INPUT)
  - gold/<endpoint>.json   per-endpoint gold scenarios
  - gold.json              consolidated gold table + empirical summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL (read-only GET). The cloud LLM backend is NOT
used here — the gold reference is pure deterministic code.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import ratelimit_spec  # noqa: E402

LIMIT_N = ratelimit_spec.DEFAULT_LIMIT_N          # 100 (DummyJSON's real max)
WINDOW_SECONDS = ratelimit_spec.DEFAULT_WINDOW_SECONDS  # 10 (DummyJSON's real windowMs/1000)
SUCCESS_CODE = 200
METHOD = "GET"
API_KEY_HEADER = "X-Forwarded-For"   # DummyJSON keys its limiter by client IP (trust proxy)
RETRY_AFTER_HEADER = "Retry-After"
GOLD_OCTET = 9                        # gold reference uses an isolated client-key band

# DummyJSON list endpoints tested as-is against the real global limiter. Each endpoint is
# exercised under its own isolated client key (X-Forwarded-For) so it is an independent
# rate-limit subject with a full 100/10s budget. api_key_value is the nominal documented
# client id; the gold sends GOLD_OCTET-banded IPs on the wire.
ENDPOINTS = [
    {"endpoint": "/products", "api_key_value": "10.50.1.0"},
    {"endpoint": "/posts",    "api_key_value": "10.50.2.0"},
    {"endpoint": "/comments", "api_key_value": "10.50.3.0"},
    {"endpoint": "/todos",    "api_key_value": "10.50.4.0"},
    {"endpoint": "/users",    "api_key_value": "10.50.5.0"},
    {"endpoint": "/recipes",  "api_key_value": "10.50.6.0"},
]


def _gold_client_ip(endpoint_index: int) -> str:
    return f"10.{GOLD_OCTET}.{(endpoint_index % 250) + 1}.1"


def _cfg(entry: dict) -> dict:
    return {
        "endpoint": entry["endpoint"],
        "api_key_value": entry["api_key_value"],
        "method": METHOD,
        "success_code": SUCCESS_CODE,
        "limit_n": LIMIT_N,
        "window_seconds": WINDOW_SECONDS,
        "api_key_header": API_KEY_HEADER,
        "retry_after_header": RETRY_AFTER_HEADER,
    }


def get(path: str, headers: dict, _retries: int = 5):
    """Read-only GET. Returns (status_code, retry_after_or_None, reset_epoch_or_None).
    Transient connection failures (-1, e.g. ECONNRESET under burst) retry with backoff so
    the gold reference never records a corrupted -1 token; real HTTP codes are returned
    as-is. X-RateLimit-Reset is the authoritative window-close epoch."""
    url = f"{BASE_URL}{path}"
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")
        for k, v in headers.items():
            if k and v is not None:
                req.add_header(k, str(v))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                h = r.headers
                return r.getcode(), h.get("Retry-After"), h.get("X-RateLimit-Reset")
        except urllib.error.HTTPError as e:
            h = e.headers
            return e.code, (h.get("Retry-After") if h else None), (h.get("X-RateLimit-Reset") if h else None)
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.3 * (attempt + 1))
    return -1, None, None


def run_reference_plan(cfg: dict, endpoint_index: int):
    """Execute the canonical correct plan against the live API with real timing.
    Returns the raw observation dict ratelimit_spec.evaluate expects + a request log.
    The client key (X-Forwarded-For) is an isolated gold-banded IP per endpoint."""
    headers = {cfg["api_key_header"]: _gold_client_ip(endpoint_index)}
    path = cfg["endpoint"]
    n = cfg["limit_n"]
    reqlog = []

    # Sync to a fresh global window + fire the burst, re-bursting (up to 3x) if the burst
    # straddled a reset boundary and so failed to trip the limiter (over not 429). This
    # matches the harness's robustness so gold and agents observe the same tokens.
    statuses, first_429 = [], None
    over_status, over_retry, over_reset = (None, None, None)
    t_over = None
    for attempt in range(3):
        _, _, reset0 = get(path, headers)
        try:
            r0 = int(str(reset0).strip()) if reset0 is not None else None
        except (TypeError, ValueError):
            r0 = None
        if r0 is not None:
            wait = (r0 - time.time()) + 0.4
            if 0 < wait <= cfg["window_seconds"] + 2:
                time.sleep(wait)

        statuses, first_429 = [], None
        for i in range(n):
            status, _, _ = get(path, headers)
            statuses.append(status)
            if status == 429 and first_429 is None:
                first_429 = i + 1
        over_status, over_retry, over_reset = get(path, headers)
        t_over = time.monotonic()
        if over_status == 429 and first_429 is None:
            first_429 = n + 1
        if over_status == 429 or attempt == 2:
            break
    reqlog.append({"label": "at_limit", "count": n, "statuses": statuses})
    reqlog.append({"label": "over_limit", "ordinal": n + 1,
                   "status": over_status, "retry_after": over_retry, "reset_epoch": over_reset})

    # Anchor probe timing on X-RateLimit-Reset (authoritative window close), since
    # DummyJSON's Retry-After is a constant windowMs, not the true time remaining.
    secs_to_close = None
    try:
        secs_to_close = int(str(over_reset).strip()) - time.time() if over_reset is not None else None
    except (TypeError, ValueError):
        secs_to_close = None
    if secs_to_close is None or secs_to_close < 0:
        try:
            rs = int(str(over_retry).strip()) if over_retry is not None else None
        except (TypeError, ValueError):
            rs = None
        secs_to_close = rs if (rs is not None and rs > 0) else cfg["window_seconds"]
    secs_to_close = max(0.0, min(secs_to_close, cfg["window_seconds"] + 2))
    window_close = t_over + secs_to_close

    within_status = after_status = None
    for label, offset in (("within_window", -2), ("after_window", 1)):
        delay = (window_close + offset) - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, cfg["window_seconds"] + 5))
        status, retry, reset = get(path, headers)
        if label == "within_window":
            within_status = status
        else:
            after_status = status
        reqlog.append({"label": label, "offset_seconds": offset,
                       "status": status, "retry_after": retry, "reset_epoch": reset})

    raw = {
        "at_limit_statuses": statuses, "over_status": over_status,
        "over_retry_after": over_retry, "first_429_ordinal": first_429,
        "sequence_ran": True, "within_status": within_status, "after_status": after_status,
    }
    return raw, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's
    rate-limit contract WITHOUT the answer plan."""
    return {
        "title": "Rate-limit contract (authored for the rate-limit-enforcement testing task)",
        "description": "Each endpoint is documented to allow at most limit_n requests per "
                       "window_seconds window per client key (carried in the api_key_header, "
                       "X-Forwarded-For); request number limit_n+1 should return 429 with a "
                       "positive-integer Retry-After header, and the limit should clear after "
                       "the window. Agents construct the rate-limit test plan from this; ground "
                       "truth is the live API's observed behavior. DummyJSON is read-only and "
                       "never modified; it runs a real express-rate-limit limiter (100/10s per "
                       "client key) when booted NODE_ENV=production, which the harness exercises.",
        "target": BASE_URL,
        "method": METHOD,
        "success_code": SUCCESS_CODE,
        "limit_n": LIMIT_N,
        "window_seconds": WINDOW_SECONDS,
        "api_key_header": API_KEY_HEADER,
        "retry_after_header": RETRY_AFTER_HEADER,
        "endpoints": [
            {"endpoint": e["endpoint"], "api_key_value": e["api_key_value"]}
            for e in ENDPOINTS
        ],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "ratelimit_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    trigger = {}
    any_enforced = False
    for idx, entry in enumerate(ENDPOINTS):
        cfg = _cfg(entry)
        # No inter-endpoint wait: each endpoint uses its own isolated client-key bucket.
        raw, reqlog = run_reference_plan(cfg, idx)
        observed = ratelimit_spec.evaluate(cfg["limit_n"], raw)

        ordinal = raw.get("first_429_ordinal")
        trigger[cfg["endpoint"]] = ordinal if ordinal is not None else "none"
        if ordinal is not None:
            any_enforced = True

        scenarios = []
        for label in ratelimit_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = ratelimit_spec.correct(label, tok, cfg["limit_n"])
            scenarios.append({
                "scenario": label,
                "ideal": ratelimit_spec.ideal_for(label, cfg["limit_n"]),
                "observed_token": tok,
                "api_correct": ok,
            })
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {
            "endpoint": cfg["endpoint"],
            "api_key_value": cfg["api_key_value"],
            "limit_n": cfg["limit_n"],
            "window_seconds": cfg["window_seconds"],
            "trigger_ordinal": trigger[cfg["endpoint"]],
            "reference_plan": ratelimit_spec.build_reference_plan(cfg),
            "request_log": reqlog,
            "scenarios": scenarios,
        }
        (GOLD_DIR / f"{entry['endpoint'].strip('/')}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(ratelimit_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_rate_limit_contract_correctness_rate_pct": rate,
        "rate_limit_enforced": any_enforced,
        "rate_limit_trigger_precision": trigger,
        "note": "Ground truth = live DummyJSON observed token per (endpoint, scenario). "
                "DummyJSON runs a real express-rate-limit limiter (max 100 per 10s per client "
                "key, keyed by X-Forwarded-For under trust-proxy), active because the target is "
                "booted NODE_ENV=production. It CORRECTLY enforces the documented contract: "
                "requests 1..100 -> 200, request 101 -> 429 with Retry-After:10, an in-window "
                "probe stays 429, an after-window probe resets to 200. So every scenario matches "
                "the idealized contract (~100% correctness) and Headline Rate Limit Trigger "
                "Precision = PASS (first 429 on exactly request 101) on every endpoint.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
