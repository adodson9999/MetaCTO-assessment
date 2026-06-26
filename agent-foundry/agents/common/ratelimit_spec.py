"""Canonical scenario structure for the API rate-limit-enforcement testing task.

ONE definition of the rate-limit test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-rate-limit-enforcement/build_gold.py), and
  - the harness (agents/common/ratelimit.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested READ-ONLY as-is — never modified):
  - DummyJSON ships a REAL global rate limiter (express-rate-limit, src/middleware/
    rate-limiter.js): max 100 requests per 10-second window, keyed by client IP. With
    `app.set('trust proxy', true)` the key is taken from `X-Forwarded-For`, so a distinct
    XFF value gets its own 100/10s bucket. The limiter is SKIPPED when NODE_ENV ===
    'development', so the foundry boots the target with NODE_ENV=production to exercise it
    (NODE_ENV does not gate Mongo, so the air-gapped no-Mongo boot is unaffected).
  - Empirically verified contract: requests 1..100 return 200; request 101 returns 429
    with `Retry-After: 10`; a probe inside the window stays 429; a probe after the window
    resets to 200. The limiter therefore CORRECTLY enforces the documented contract.
  - The idealized contract (N=100 requests per W=10s window per client key; request N+1
    -> 429 + positive-integer Retry-After; limit clears after the window) is what each
    scenario's `ideal` token encodes; the gold records the API's REAL token. Here they
    MATCH on every scenario, so the QA finding is "rate limit correctly enforced; first
    429 at request 101 (PASS)" rather than a violation.

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/products", "method": "GET", "success_code": 200,
    "limit_n": 10, "window_seconds": 5,
    "api_key_header": "x-api-key", "api_key_value": "forge-test-key-products",
    "retry_after_header": "Retry-After",
    "at_limit":   {"label": "at_limit",   "count": 10},
    "over_limit": {"label": "over_limit", "count": 1},
    "probes": [
      {"label": "within_window", "offset_seconds": -2},
      {"label": "after_window",  "offset_seconds": 1}
    ]
  }
"""
from __future__ import annotations

# The documented contract the agents are briefed from — DummyJSON's REAL limiter
# (express-rate-limit: max 100 requests per 10-second window per client key).
DEFAULT_LIMIT_N = 100
DEFAULT_WINDOW_SECONDS = 10

# The full, ordered scenario set scored per endpoint (the metric denominator).
# `ideal` is the token a perfectly-enforcing API would produce; gold records the
# REAL token DummyJSON produces. `first_429_ordinal` ideal = str(N+1) and is
# resolved dynamically via ideal_for() so the contract stays single-sourced.
SCENARIOS = [
    ("at_limit_all_non_429",     "true"),   # all N at-limit requests return non-429
    ("over_limit_status",        "429"),    # request N+1 returns exactly 429
    ("first_429_ordinal",        "101"),    # ordinal of the first 429 (= N+1); resolved via ideal_for()
    ("trigger_precision_exact",  "true"),   # first 429 occurs on exactly request N+1
    ("retry_after_present",      "true"),   # the over-limit response carries Retry-After
    ("retry_after_positive_int", "true"),   # that Retry-After value is a positive integer
    ("within_window_still_429",  "429"),    # probe at (window close - 2s) is still 429
    ("after_window_non_429",     "true"),   # probe at (window close + 1s) is non-429
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)


def ideal_for(scenario: str, limit_n: int = DEFAULT_LIMIT_N) -> str:
    """The idealized token for a scenario, resolving first_429_ordinal to N+1 so
    the contract is single-sourced rather than hard-coded to N=10."""
    if scenario == "first_429_ordinal":
        return str(limit_n + 1)
    return IDEAL[scenario]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one endpoint, derived deterministically from
    its config: a burst of exactly limit_n requests (at_limit), one more request
    (over_limit), and two window probes (-2s before close, +1s after close)."""
    return {
        "endpoint": cfg["endpoint"],
        "method": cfg.get("method", "GET"),
        "success_code": cfg.get("success_code", 200),
        "limit_n": cfg["limit_n"],
        "window_seconds": cfg["window_seconds"],
        "api_key_header": cfg.get("api_key_header", "x-api-key"),
        "api_key_value": cfg.get("api_key_value", "forge-test-key"),
        "retry_after_header": cfg.get("retry_after_header", "Retry-After"),
        "at_limit": {"label": "at_limit", "count": cfg["limit_n"]},
        "over_limit": {"label": "over_limit", "count": 1},
        "probes": [
            {"label": "within_window", "offset_seconds": -2},
            {"label": "after_window", "offset_seconds": 1},
        ],
    }


def _status_class(code) -> str:
    """Collapse a status code to the token used for comparison. 429 is exact (the
    whole point of the task); any 2xx is 'success'; None is 'none'; else 'other_<n>'."""
    if code is None:
        return "none"
    if code == 429:
        return "429"
    if 200 <= code < 300:
        return "200"
    return f"other_{code}"


def _is_positive_int(value) -> bool:
    """Retry-After may be an integer-seconds string. A positive-integer value passes;
    absent, non-numeric, zero, negative, or HTTP-date forms do not."""
    if value is None:
        return False
    try:
        return int(str(value).strip()) > 0
    except (TypeError, ValueError):
        return False


def evaluate(limit_n: int, obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    obs is the harness's raw measurement for one endpoint:
      {
        "at_limit_statuses": [int, ...] | None,   # the N burst statuses (None => not run)
        "over_status": int | None,                # status of request N+1
        "over_retry_after": str | None,           # Retry-After header on the over-limit resp
        "first_429_ordinal": int | None,          # 1-based ordinal of the first 429 in burst+over
        "sequence_ran": bool,                      # whether burst+over executed at all
        "within_status": int | None,              # status of the within-window probe
        "after_status": int | None,               # status of the after-window probe
      }

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    out: dict[str, str] = {}
    ran = bool(obs.get("sequence_ran"))
    burst = obs.get("at_limit_statuses")
    over = obs.get("over_status")
    ordinal = obs.get("first_429_ordinal")
    retry_after = obs.get("over_retry_after")

    # 1. all at-limit requests non-429
    if isinstance(burst, list) and burst:
        out["at_limit_all_non_429"] = "true" if all(c != 429 for c in burst) else "false"
    else:
        out["at_limit_all_non_429"] = "missing"

    # 2. over-limit status class
    out["over_limit_status"] = _status_class(over) if ran else "missing"

    # 3. ordinal of the first 429 across the whole sequence
    if not ran:
        out["first_429_ordinal"] = "missing"
    else:
        out["first_429_ordinal"] = str(ordinal) if ordinal is not None else "none"

    # 4. first 429 occurs on exactly request N+1
    if not ran:
        out["trigger_precision_exact"] = "missing"
    else:
        out["trigger_precision_exact"] = "true" if ordinal == (limit_n + 1) else "false"

    # 5. Retry-After present on the over-limit response
    out["retry_after_present"] = ("true" if retry_after not in (None, "") else "false") if ran else "missing"

    # 6. Retry-After is a positive integer
    out["retry_after_positive_int"] = ("true" if _is_positive_int(retry_after) else "false") if ran else "missing"

    # 7. within-window probe still 429
    w = obs.get("within_status")
    out["within_window_still_429"] = _status_class(w) if w is not None else "missing"

    # 8. after-window probe non-429
    a = obs.get("after_status")
    out["after_window_non_429"] = ("true" if a != 429 else "false") if a is not None else "missing"

    return out


def correct(scenario: str, observed_token: str, limit_n: int = DEFAULT_LIMIT_N) -> bool:
    """Did the API behave per the idealized rate-limit contract for this scenario?"""
    return observed_token == ideal_for(scenario, limit_n)
