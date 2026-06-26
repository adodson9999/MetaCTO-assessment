#!/usr/bin/env python3
"""Gold-set builder for the API Retry-After-header-compliance testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the endpoint catalogue + the agents' input spec (retryafter_spec.json), derives the
canonical correct Retry-After plan per endpoint, executes that plan against a locally-
running DummyJSON with READ-ONLY GET calls at REAL wall-clock timing, and records the
REAL observed behavior (the over-limit status, the Retry-After header value + parsed
form, the two deadline-anchored probe statuses) per scenario.

DummyJSON is tested AS-IS and never modified: GET only, no body, no mutation. It ships a
REAL express-rate-limit limiter (max 100 per 10s per client key, keyed by X-Forwarded-For
under trust-proxy), active because the target is booted NODE_ENV=production. Its
Retry-After is the constant windowMs/1000 (= 10), which is PRESENT and POSITIVE and is
HONORED (a request after the advertised duration succeeds), so the documented
Retry-After contract is satisfied. The idealized contract lives in retryafter_spec; where
the real token differs from the ideal is the finding.

To keep gold and the agents on the same machine conditions, phase4_retryafter_run.sh
rebuilds gold immediately before running the four agents, so even the timing-sensitive
still-limited probe is observed under identical conditions and fidelity holds.

Outputs (all under data/validate-retry-after-header-compliance/):
  - retryafter_spec.json   the endpoint catalogue the agents are briefed from (INPUT)
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
import retryafter_spec  # noqa: E402

LIMIT_N = retryafter_spec.DEFAULT_LIMIT_N          # 100 (DummyJSON's real max)
WINDOW_SECONDS = retryafter_spec.DEFAULT_WINDOW_SECONDS  # 10 (DummyJSON's real windowMs/1000)
SUCCESS_CODE = 200
METHOD = "GET"
API_KEY_HEADER = "X-Forwarded-For"   # DummyJSON keys its limiter by client IP (trust proxy)
RETRY_AFTER_HEADER = "Retry-After"
GOLD_OCTET = 69                      # gold reference uses an isolated client-key band

# DummyJSON list endpoints tested as-is against the real global limiter. Each endpoint is
# exercised under its own isolated client key (X-Forwarded-For) so it is an independent
# rate-limit subject with a full 100/10s budget.
ENDPOINTS = [
    {"endpoint": "/products", "api_key_value": "10.60.1.0"},
    {"endpoint": "/posts",    "api_key_value": "10.60.2.0"},
    {"endpoint": "/comments", "api_key_value": "10.60.3.0"},
    {"endpoint": "/todos",    "api_key_value": "10.60.4.0"},
    {"endpoint": "/users",    "api_key_value": "10.60.5.0"},
    {"endpoint": "/recipes",  "api_key_value": "10.60.6.0"},
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
    as-is."""
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
    Returns the raw observation dict retryafter_spec.evaluate expects + a request log.
    The client key (X-Forwarded-For) is an isolated gold-banded IP per endpoint."""
    headers = {cfg["api_key_header"]: _gold_client_ip(endpoint_index)}
    path = cfg["endpoint"]
    n = cfg["limit_n"]
    reqlog = []

    # Sync to a fresh global window + fire the burst, re-bursting (up to 3x) if the burst
    # straddled a reset boundary and so failed to trip the limiter (over not 429).
    statuses, first_429 = [], None
    over_status, over_retry, over_reset = (None, None, None)
    t_over_mono = t_over_epoch = None
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
        t_over_mono = time.monotonic()
        t_over_epoch = time.time()
        if over_status == 429 and first_429 is None:
            first_429 = n + 1
        if over_status == 429 or attempt == 2:
            break
    reqlog.append({"label": "at_limit", "count": n, "statuses": statuses})
    reqlog.append({"label": "over_limit", "ordinal": n + 1, "status": over_status,
                   "retry_after": over_retry, "reset_epoch": over_reset})

    # Parse Retry-After -> RETRY_SECONDS and anchor the two probes on the
    # retry_after_deadline = T_429 + RETRY_SECONDS (the value under test).
    retry_seconds, retry_form = retryafter_spec.parse_retry_after(over_retry, t_over_epoch)
    deadline_secs = retry_seconds if (retry_seconds is not None and retry_seconds > 0) else cfg["window_seconds"]
    deadline_secs = max(0, min(deadline_secs, cfg["window_seconds"] + 5))
    retry_after_deadline = t_over_mono + deadline_secs
    max_sleep = cfg["window_seconds"] + 7

    still_limited_status = still_limited_retry = reset_status = None
    for label, offset in (("still_limited", -1), ("reset", 1)):
        fire_at = retry_after_deadline + offset
        delay = fire_at - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, max_sleep))
        status, retry, reset = get(path, headers)
        if label == "still_limited":
            still_limited_status, still_limited_retry = status, retry
        else:
            reset_status = status
        reqlog.append({"label": label, "anchor": "retry_after_deadline", "offset_seconds": offset,
                       "status": status, "retry_after": retry, "reset_epoch": reset})

    raw = {
        "over_status": over_status, "over_retry_after": over_retry, "over_reset_epoch": over_reset,
        "t_429_epoch": t_over_epoch, "retry_seconds": retry_seconds, "retry_after_form": retry_form,
        "first_429_ordinal": first_429, "sequence_ran": True,
        "still_limited_status": still_limited_status, "still_limited_retry_after": still_limited_retry,
        "reset_status": reset_status,
    }
    return raw, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's
    rate-limit contract WITHOUT the answer plan."""
    return {
        "title": "Retry-After compliance contract (authored for the Retry-After-header-compliance testing task)",
        "description": "Each endpoint is documented to allow at most limit_n requests per "
                       "window_seconds window per client key (carried in the api_key_header, "
                       "X-Forwarded-For); request number limit_n+1 should return 429 carrying a "
                       "positive Retry-After header that advertises the wait before retrying. A "
                       "request before that advertised wait elapses should still be 429, and a "
                       "request after it should succeed. Agents construct the Retry-After test plan "
                       "from this; ground truth is the live API's observed behavior. DummyJSON is "
                       "read-only and never modified; it runs a real express-rate-limit limiter "
                       "(100/10s per client key, Retry-After = windowMs/1000) when booted "
                       "NODE_ENV=production, which the harness exercises.",
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

    (HERE / "retryafter_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_scenarios = correct_scenarios = 0
    per_endpoint_tokens = []
    any_enforced = False
    for idx, entry in enumerate(ENDPOINTS):
        cfg = _cfg(entry)
        # No inter-endpoint wait: each endpoint uses its own isolated client-key bucket.
        raw, reqlog = run_reference_plan(cfg, idx)
        observed = retryafter_spec.evaluate(cfg["limit_n"], raw)
        per_endpoint_tokens.append(observed)
        if raw.get("over_status") == 429:
            any_enforced = True

        scenarios = []
        for label in retryafter_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = retryafter_spec.correct(label, tok, cfg["limit_n"])
            scenarios.append({
                "scenario": label,
                "ideal": retryafter_spec.ideal_for(label, cfg["limit_n"]),
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
            "over_status": raw.get("over_status"),
            "retry_after_value": raw.get("over_retry_after"),
            "retry_after_form": raw.get("retry_after_form"),
            "retry_seconds": raw.get("retry_seconds"),
            "trigger_ordinal": raw.get("first_429_ordinal"),
            "reference_plan": retryafter_spec.build_reference_plan(cfg),
            "request_log": reqlog,
            "scenarios": scenarios,
        }
        (GOLD_DIR / f"{entry['endpoint'].strip('/')}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    accuracy = retryafter_spec.retry_after_accuracy(per_endpoint_tokens)
    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(retryafter_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "api_correct_scenarios": correct_scenarios,
        "empirical_contract_correctness_rate_pct": rate,
        "retry_after_accuracy_pct": accuracy["retry_after_accuracy_pct"],
        "retry_after_accuracy_pass": accuracy["pass"],
        "endpoints_honored": accuracy["endpoints_honored"],
        "rate_limit_enforced": any_enforced,
        "note": "Ground truth = live DummyJSON observed token per (endpoint, scenario). "
                "DummyJSON runs a real express-rate-limit limiter (max 100 per 10s per client key, "
                "keyed by X-Forwarded-For under trust-proxy), active because the target is booted "
                "NODE_ENV=production. Request 101 -> 429 with Retry-After present and positive "
                "(= windowMs/1000 = 10), and a request after the advertised duration succeeds, so "
                "the documented Retry-After contract IS honored (Retry-After Accuracy = 100%). "
                "Note: express-rate-limit's Retry-After is the CONSTANT windowMs, slightly "
                "overstating the true remaining time by the burst duration; the still-limited probe "
                "at deadline-1s is fired at the advertised deadline and recorded honestly.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
