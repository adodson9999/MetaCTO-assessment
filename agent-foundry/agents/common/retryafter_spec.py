"""Canonical scenario structure for the API Retry-After-header-compliance testing task.

ONE definition of the Retry-After test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/validate-retry-after-header-compliance/build_gold.py), and
  - the harness (agents/common/retryafter.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

What this task validates (distinct from test-rate-limit-enforcement):
  - Drive the endpoint to a 429 (request limit_n+1).
  - The 429 MUST carry the Retry-After header; the value MUST be either a
    positive-integer number of seconds OR an RFC 7231 HTTP-date whose delta from
    the moment of the 429 (T_429) is positive. Either way -> RETRY_SECONDS > 0.
  - STILL-LIMITED probe at T_429 + RETRY_SECONDS - 1 should still be 429.
  - RESET probe at T_429 + RETRY_SECONDS + 1 should be non-429 (the advertised
    wait is honored: a request after the advertised duration succeeds).

Target reality (DummyJSON, tested READ-ONLY as-is — never modified):
  - DummyJSON ships a REAL global rate limiter (express-rate-limit, src/middleware/
    rate-limiter.js): max 100 requests per 10-second window, keyed by client IP
    (X-Forwarded-For under trust-proxy). Skipped when NODE_ENV === 'development', so the
    foundry boots the target NODE_ENV=production to exercise it.
  - express-rate-limit emits Retry-After as a CONSTANT (= windowMs/1000 = 10), NOT the
    true seconds remaining, and X-RateLimit-Reset (epoch) as the authoritative close.
    The advertised Retry-After therefore slightly OVERSTATES the true remaining time by
    the burst duration; the harness fires the two probes at the literal advertised
    deadline (T_429 + RETRY_SECONDS +/- 1) and records the real outcome. The headline
    Retry-After Accuracy does not depend on the still-limited probe; it depends on the
    header being present, positive, and HONORED (a request after the advertised duration
    succeeds), which DummyJSON satisfies.

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/products", "method": "GET", "success_code": 200,
    "limit_n": 100, "window_seconds": 10,
    "api_key_header": "X-Forwarded-For", "api_key_value": "10.60.1.0",
    "retry_after_header": "Retry-After",
    "at_limit":   {"label": "at_limit",   "count": 100},
    "over_limit": {"label": "over_limit", "count": 1},
    "probes": [
      {"label": "still_limited", "anchor": "retry_after_deadline", "offset_seconds": -1},
      {"label": "reset",         "anchor": "retry_after_deadline", "offset_seconds": 1}
    ]
  }
"""
from __future__ import annotations

from email.utils import parsedate_to_datetime
from math import ceil

# The documented contract the agents are briefed from — DummyJSON's REAL limiter
# (express-rate-limit: max 100 requests per 10-second window per client key).
DEFAULT_LIMIT_N = 100
DEFAULT_WINDOW_SECONDS = 10

# The literal anchor every probe in this task is measured against: the retry-after
# deadline = T_429 (moment the over-limit 429 was observed) + RETRY_SECONDS (the
# integer seconds parsed from the 429's Retry-After header / HTTP-date).
RETRY_AFTER_DEADLINE_ANCHOR = "retry_after_deadline"

# The full, ordered scenario set scored per endpoint (the fidelity denominator).
# `ideal` is the token a perfectly-compliant API would produce; gold records the
# REAL token DummyJSON produces.
SCENARIOS = [
    ("over_limit_is_429",             "429"),    # request N+1 returns exactly 429 (precondition)
    ("retry_after_present",           "true"),   # the 429 carries the Retry-After header
    ("retry_after_positive",          "true"),   # value is a positive-int OR future HTTP-date -> RETRY_SECONDS > 0
    ("still_limited_before_deadline", "429"),    # probe at deadline-1s is still 429
    ("reset_after_deadline_non_429",  "true"),   # probe at deadline+1s is non-429 (advertised wait honored)
    ("retry_after_honored",           "true"),   # present AND positive AND reset non-429 (the headline boolean)
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# The headline boolean per endpoint that the Retry-After Accuracy metric averages.
HEADLINE_SCENARIO = "retry_after_honored"


def ideal_for(scenario: str, limit_n: int = DEFAULT_LIMIT_N) -> str:
    """The idealized token for a scenario. (No scenario depends on limit_n here, but
    the signature mirrors ratelimit_spec.ideal_for so the harness/gold call it uniformly.)"""
    return IDEAL[scenario]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one endpoint: a burst of exactly limit_n requests
    (at_limit), one more request (over_limit, expected 429), and two probes anchored on
    the retry_after_deadline (-1s still limited, +1s reset)."""
    return {
        "endpoint": cfg["endpoint"],
        "method": cfg.get("method", "GET"),
        "success_code": cfg.get("success_code", 200),
        "limit_n": cfg["limit_n"],
        "window_seconds": cfg["window_seconds"],
        "api_key_header": cfg.get("api_key_header", "X-Forwarded-For"),
        "api_key_value": cfg.get("api_key_value", "forge-test-key"),
        "retry_after_header": cfg.get("retry_after_header", "Retry-After"),
        "at_limit": {"label": "at_limit", "count": cfg["limit_n"]},
        "over_limit": {"label": "over_limit", "count": 1},
        "probes": [
            {"label": "still_limited", "anchor": RETRY_AFTER_DEADLINE_ANCHOR, "offset_seconds": -1},
            {"label": "reset", "anchor": RETRY_AFTER_DEADLINE_ANCHOR, "offset_seconds": 1},
        ],
    }


def parse_retry_after(value, t429_epoch: float | None = None) -> tuple[int | None, str]:
    """Parse a Retry-After header value into (retry_seconds, form).

    RFC 7231 allows two forms:
      (a) delta-seconds — a non-negative integer count of seconds.
      (b) HTTP-date — an absolute date; the wait is (date - now).
    Returns (retry_seconds, form) where form is one of:
      "integer" | "http-date" | "absent" | "invalid".
    retry_seconds is the computed positive wait, or the raw integer (which may be
    <= 0) for the integer form, or None when absent/invalid. The caller decides
    positivity via retry_seconds is not None and retry_seconds > 0.
    t429_epoch is the wall-clock epoch of the 429 (defaults handled by caller).
    """
    if value is None or str(value).strip() == "":
        return None, "absent"
    raw = str(value).strip()
    # Form (a): integer delta-seconds.
    try:
        return int(raw), "integer"
    except (TypeError, ValueError):
        pass
    # Form (b): RFC 7231 HTTP-date.
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None, "invalid"
    if dt is None:
        return None, "invalid"
    base = t429_epoch if t429_epoch is not None else dt.timestamp()
    delta = dt.timestamp() - base
    return ceil(delta), "http-date"


def _status_class(code) -> str:
    """Collapse a status code to the token used for comparison. 429 is exact (the
    whole point of the task); any 2xx is '200'; None is 'none'; else 'other_<n>'."""
    if code is None:
        return "none"
    if code == 429:
        return "429"
    if 200 <= code < 300:
        return "200"
    return f"other_{code}"


def evaluate(limit_n: int, obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    obs is the harness's raw measurement for one endpoint:
      {
        "over_status": int | None,           # status of request N+1
        "over_retry_after": str | None,      # raw Retry-After header on the 429
        "retry_seconds": int | None,         # parsed positive wait (int or from HTTP-date)
        "retry_after_form": str,             # "integer"|"http-date"|"absent"|"invalid"
        "sequence_ran": bool,                # whether burst+over executed at all
        "still_limited_status": int | None,  # status of the deadline-1s probe
        "reset_status": int | None,          # status of the deadline+1s probe
      }

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    out: dict[str, str] = {}
    ran = bool(obs.get("sequence_ran"))
    over = obs.get("over_status")
    retry_after = obs.get("over_retry_after")
    retry_seconds = obs.get("retry_seconds")

    # 1. over-limit status class (must be 429 to have a Retry-After to inspect)
    out["over_limit_is_429"] = _status_class(over) if ran else "missing"

    # 2. Retry-After present on the over-limit 429 response
    present = retry_after not in (None, "")
    out["retry_after_present"] = ("true" if present else "false") if ran else "missing"

    # 3. Retry-After value is positive (positive-int seconds OR future HTTP-date)
    positive = retry_seconds is not None and retry_seconds > 0
    out["retry_after_positive"] = ("true" if positive else "false") if ran else "missing"

    # 4. still-limited probe at deadline-1s is still 429
    s = obs.get("still_limited_status")
    out["still_limited_before_deadline"] = _status_class(s) if s is not None else "missing"

    # 5. reset probe at deadline+1s is non-429 (advertised wait honored)
    r = obs.get("reset_status")
    reset_ok = r is not None and r != 429
    out["reset_after_deadline_non_429"] = ("true" if reset_ok else "false") if r is not None else "missing"

    # 6. headline: Retry-After honored = present AND positive AND reset non-429
    if not ran or r is None:
        out["retry_after_honored"] = "missing"
    else:
        out["retry_after_honored"] = "true" if (present and positive and reset_ok) else "false"

    return out


def correct(scenario: str, observed_token: str, limit_n: int = DEFAULT_LIMIT_N) -> bool:
    """Did the API behave per the idealized Retry-After contract for this scenario?"""
    return observed_token == ideal_for(scenario, limit_n)


def retry_after_accuracy(per_endpoint_tokens: list[dict]) -> dict:
    """Retry-After Accuracy = (endpoints where the headline boolean is true / total
    endpoints) x 100. `per_endpoint_tokens` is a list of {scenario: token} dicts, one
    per endpoint. Pass = 100%."""
    total = len(per_endpoint_tokens)
    honored = sum(1 for t in per_endpoint_tokens if t.get(HEADLINE_SCENARIO) == "true")
    pct = round(100.0 * honored / total, 2) if total else None
    return {"retry_after_accuracy_pct": pct, "endpoints_honored": honored,
            "endpoints_total": total, "pass": (pct == 100.0) if total else False}
