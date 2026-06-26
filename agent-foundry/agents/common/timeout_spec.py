"""Canonical scenario structure for the API timeout-handling testing task.

ONE definition of the timeout test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-timeout-handling/build_gold.py), and
  - the harness (agents/common/timeout.py) — which executes whatever plan an agent
    emitted against the local gateway and scores it on the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no sockets. Keeps agent output and the gold set on the
same (service, endpoint, scenario) key scheme so the judge compares field-for-field.

Target reality (the local timeout-gateway fixture, tested as-is):
  - Documented contract: each service enforces upstream_timeout_s; under a >timeout
    upstream delay a COMPLIANT endpoint returns 504 within upstream_timeout_s+buffer_s,
    with a safe {"message": ...} body and the connection closed, then recovers to a
    200 under restore_max_ms once the delay is removed.
  - One endpoint is non-compliant (500 + leaky body + connection left open) — a real
    QA finding the suite must surface, exactly like DummyJSON's lenient pagination.

A plan for one service (the agent's output, and the reference) looks like:
  {
    "service": "orders-api",
    "upstream_timeout_s": 10, "buffer_s": 2, "max_wait_s": 12, "restore_max_ms": 500,
    "delayed":  [{"label": "GET /orders", "method": "GET", "path": "/orders"}, ...],
    "restore":  [{"label": "GET /orders", "method": "GET", "path": "/orders"}, ...]
  }
"""
from __future__ import annotations

# Per-endpoint scenarios scored in the delayed phase (upstream delayed 60s) and the
# restore phase (delay removed). `ideal` is what a fully timeout-compliant endpoint
# produces; gold records the gateway's REAL token.
ENDPOINT_SCENARIOS = [
    ("delayed_status",          "504_or_408"),  # 504 or 408, never 500/hang
    ("delayed_within_max_wait", "true"),        # responded within max_wait_s
    ("delayed_conn_closed",     "true"),        # server closed the TCP connection
    ("delayed_body_safe",       "true"),        # non-empty message AND no path/stack/URL leak
    ("restore_status",          "200"),         # 200 once the delay is removed
    ("restore_within_budget",   "true"),        # restore latency < restore_max_ms
]
# Per-service scenario: the agent's one piece of arithmetic.
SERVICE_SCENARIOS = [
    ("max_wait_correct",        "true"),        # max_wait_s == upstream_timeout_s + buffer_s
]

ENDPOINT_SCENARIO_LABELS = [s for s, _ in ENDPOINT_SCENARIOS]
SERVICE_SCENARIO_LABELS = [s for s, _ in SERVICE_SCENARIOS]
IDEAL = dict(ENDPOINT_SCENARIOS + SERVICE_SCENARIOS)

# Leak markers the body-safety check forbids (file path, stack frame, upstream URL).
LEAK_MARKERS = ("http://", "https://", "/srv/", ".js:", ".py:", "Traceback", "    at ", "\tat ")


def build_reference_plan(svc_cfg: dict) -> dict:
    """The canonical CORRECT plan for one service, derived deterministically: echo
    the documented contract, set max_wait_s = upstream_timeout_s + buffer_s, and list
    every endpoint once in both phases (label = "<METHOD> <path>")."""
    t = svc_cfg["upstream_timeout_s"]
    b = svc_cfg["buffer_s"]
    probes = [
        {"label": f"{ep['method'].upper()} {ep['path']}",
         "method": ep["method"].upper(), "path": ep["path"]}
        for ep in svc_cfg["endpoints"]
    ]
    return {
        "service": svc_cfg["service"],
        "upstream_timeout_s": t,
        "buffer_s": b,
        "max_wait_s": t + b,
        "restore_max_ms": svc_cfg["restore_max_ms"],
        "delayed": [dict(p) for p in probes],
        "restore": [dict(p) for p in probes],
    }


def _status_class(code) -> str:
    if code is None:
        return "none"
    if code in (504, 408, 500, 200):
        return str(code)
    return f"other_{code}"


def body_is_safe(body: dict | None) -> tuple[bool, bool]:
    """Return (message_nonempty, no_leak). A safe error body has a non-empty
    "message" string and contains no file path, stack frame, or upstream URL."""
    if not isinstance(body, dict):
        return (False, False)
    msg = body.get("message")
    message_nonempty = isinstance(msg, str) and msg.strip() != ""
    blob = ""
    try:
        import json
        blob = json.dumps(body)
    except Exception:  # noqa
        blob = str(body)
    no_leak = not any(marker in blob for marker in LEAK_MARKERS)
    return (message_nonempty, no_leak)


def evaluate_endpoint(delayed: dict | None, restore: dict | None,
                      agent_max_wait_s, documented_restore_max_ms: int) -> dict:
    """Observed token per per-endpoint scenario.

    delayed : {"status":int|None, "elapsed_s":float|None, "conn_closed":bool|None,
               "message_nonempty":bool|None, "no_leak":bool|None} or None if not probed.
    restore : {"status":int|None, "elapsed_ms":float|None} or None if not probed.
    agent_max_wait_s : the max_wait_s THIS agent emitted (gold uses the correct value).
    documented_restore_max_ms : the target's documented restore budget (a property of
                                the gateway, identical for gold and every agent).
    """
    obs: dict[str, str] = {}

    if delayed is None:
        for s in ("delayed_status", "delayed_within_max_wait",
                  "delayed_conn_closed", "delayed_body_safe"):
            obs[s] = "missing"
    else:
        obs["delayed_status"] = _status_class(delayed.get("status"))
        el = delayed.get("elapsed_s")
        if el is None or agent_max_wait_s is None:
            obs["delayed_within_max_wait"] = "missing" if el is None else "true"
        else:
            obs["delayed_within_max_wait"] = "true" if el <= agent_max_wait_s else "false"
        cc = delayed.get("conn_closed")
        obs["delayed_conn_closed"] = "missing" if cc is None else ("true" if cc else "false")
        mn, nl = delayed.get("message_nonempty"), delayed.get("no_leak")
        if mn is None or nl is None:
            obs["delayed_body_safe"] = "missing"
        else:
            obs["delayed_body_safe"] = "true" if (mn and nl) else "false"

    if restore is None:
        obs["restore_status"] = "missing"
        obs["restore_within_budget"] = "missing"
    else:
        obs["restore_status"] = _status_class(restore.get("status"))
        rel = restore.get("elapsed_ms")
        if rel is None:
            obs["restore_within_budget"] = "missing"
        else:
            obs["restore_within_budget"] = "true" if rel <= documented_restore_max_ms else "false"

    return obs


def evaluate_service(plan: dict | None, svc_cfg: dict) -> dict:
    """Observed token for the per-service arithmetic scenario."""
    expected = svc_cfg["upstream_timeout_s"] + svc_cfg["buffer_s"]
    if not isinstance(plan, dict) or "max_wait_s" not in plan:
        return {"max_wait_correct": "missing"}
    try:
        ok = int(plan["max_wait_s"]) == expected
    except (TypeError, ValueError):
        return {"max_wait_correct": "false"}
    return {"max_wait_correct": "true" if ok else "false"}


def correct(scenario: str, observed_token: str) -> bool:
    """Did the target behave per the idealized timeout contract for this scenario?"""
    if scenario == "delayed_status":
        return observed_token in ("504", "408")
    return observed_token == IDEAL[scenario]


def enforcement_pass(endpoint_obs: dict) -> bool:
    """Headline Timeout-Enforcement test: an endpoint ENFORCES the timeout iff it
    returned 504/408 within max_wait AND closed the connection. (The body-safety and
    restore scenarios are tracked too, but enforcement is this triple — per the task's
    Timeout Enforcement Rate definition.)"""
    return (endpoint_obs.get("delayed_status") in ("504", "408")
            and endpoint_obs.get("delayed_within_max_wait") == "true"
            and endpoint_obs.get("delayed_conn_closed") == "true")
