"""Canonical scenario structure for the API correlation-ID-propagation testing task.

ONE definition of the propagation test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/validate-correlation-id-propagation/build_gold.py), and
  - the harness (agents/common/cid.py) — which executes whatever plan an agent emitted
    and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same scenario key
scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested AS-IS — never modified):
  - DummyJSON sets no `X-Correlation-ID` on any response.
  - Its request logger (src/middleware/request-logger.js) logs only
    method/status/times/ip/url/referrer/user_agent — no correlation id, no request headers.
  - It makes no outbound service calls: there is no inventory-service or payment-service and
    no downstream log to grep.
  - A no-header request triggers no UUID-v4 generation.
  ⇒ The empirical Correlation-ID Propagation Rate is 0%. Where the real token differs from the
  idealized `true` is the genuine QA finding this task surfaces, not an agent bug.

The plan one agent emits (and the reference) is a single JSON object:
  {
    "correlation_id": "corr-abc-12345-test",
    "header_name": "X-Correlation-ID",
    "endpoint": {"method": "POST", "path": "/products/add"},
    "downstream_services": ["inventory-service", "payment-service"],
    "with_header_request": {"method": "POST", "path": "/products/add",
        "headers": {"Authorization": "Bearer <valid_token>",
                    "X-Correlation-ID": "corr-abc-12345-test"}},
    "no_header_request": {"method": "POST", "path": "/products/add",
        "headers": {"Authorization": "Bearer <valid_token>"}},
    "uuid_v4_regex": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    "assertions": [ ...the ten labels below, in order... ]
  }
"""
from __future__ import annotations

# Fixed contract values (the deterministic brief the agent is handed).
CORR_ID = "corr-abc-12345-test"
HEADER_NAME = "X-Correlation-ID"
ENDPOINT = {"method": "POST", "path": "/products/add"}
DOWNSTREAM_SERVICES = ["inventory-service", "payment-service"]
UUID_V4_REGEX = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
TOKEN_PLACEHOLDER = "Bearer <valid_token>"

# The exact ten assertion labels the agent must emit, in order. They are also the
# full, ordered scenario set scored per run (the metric denominator). `ideal` is the
# token a perfectly-propagating API would produce; gold records DummyJSON's REAL token.
SCENARIOS = [
    ("resp_header_echo_exact",      "true"),   # with-header response echoes CORR_ID byte-for-byte
    ("api_log_present",             "true"),   # >=1 API-log entry contains CORR_ID
    ("api_log_unmodified",          "true"),   # the logged value equals CORR_ID exactly
    ("downstream_count_ge2",        "true"),   # the endpoint calls >=2 downstream services
    ("inventory_log_present",       "true"),   # CORR_ID in the inventory-service log
    ("payment_log_present",         "true"),   # CORR_ID in the payment-service log
    ("no_header_uuid_generated",    "true"),   # no-header response X-Correlation-ID matches UUID v4
    ("no_header_uuid_in_api_log",   "true"),   # generated id appears in the API log
    ("no_header_uuid_in_inventory", "true"),   # generated id in the inventory-service log
    ("no_header_uuid_in_payment",   "true"),   # generated id in the payment-service log
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
ASSERTION_LABELS = list(SCENARIO_LABELS)  # the agent emits exactly these, in this order
IDEAL = dict(SCENARIOS)


def build_reference_plan() -> dict:
    """The canonical CORRECT correlation-ID propagation test plan, derived
    deterministically from the fixed contract. This is what the gold reference
    executes; the agents must reproduce the same plan from their brief."""
    return {
        "correlation_id": CORR_ID,
        "header_name": HEADER_NAME,
        "endpoint": dict(ENDPOINT),
        "downstream_services": list(DOWNSTREAM_SERVICES),
        "with_header_request": {
            "method": ENDPOINT["method"],
            "path": ENDPOINT["path"],
            "headers": {"Authorization": TOKEN_PLACEHOLDER, HEADER_NAME: CORR_ID},
        },
        "no_header_request": {
            "method": ENDPOINT["method"],
            "path": ENDPOINT["path"],
            "headers": {"Authorization": TOKEN_PLACEHOLDER},
        },
        "uuid_v4_regex": UUID_V4_REGEX,
        "assertions": list(ASSERTION_LABELS),
    }


def plan_emits(plan: dict) -> dict:
    """What the harness can extract from an emitted plan in order to execute it.

    Returns a normalized view; whatever the agent omitted or mis-shaped is reported
    as absent so the affected scenarios score 'missing'. Pure (no I/O)."""
    if not isinstance(plan, dict):
        return {"with_req": None, "no_header_req": None, "assertions": [],
                "downstream_services": [], "header_name": None, "corr_id": None,
                "uuid_regex": None}

    def _req(obj):
        if not isinstance(obj, dict):
            return None
        m, p = obj.get("method"), obj.get("path")
        h = obj.get("headers")
        if not (isinstance(m, str) and isinstance(p, str) and isinstance(h, dict)):
            return None
        return {"method": m, "path": p, "headers": dict(h)}

    ds = plan.get("downstream_services")
    asrt = plan.get("assertions")
    return {
        "with_req": _req(plan.get("with_header_request")),
        "no_header_req": _req(plan.get("no_header_request")),
        "assertions": list(asrt) if isinstance(asrt, list) else [],
        "downstream_services": list(ds) if isinstance(ds, list) else [],
        "header_name": plan.get("header_name") if isinstance(plan.get("header_name"), str) else None,
        "corr_id": plan.get("correlation_id") if isinstance(plan.get("correlation_id"), str) else None,
        "uuid_regex": plan.get("uuid_v4_regex") if isinstance(plan.get("uuid_v4_regex"), str) else None,
    }


def evaluate(obs: dict) -> dict:
    """Compute the observed token for every scenario from raw harness observations.

    obs keys (any absent => the agent's plan did not let the harness observe it =>
    the dependent scenarios score 'missing'):
      with_request_sent           : bool  — the with-header request was actually sent
      no_header_request_sent      : bool  — the no-header request was actually sent
      resp_header_value           : str|None — X-Correlation-ID on the with-header response
      api_log_hits_corr           : int   — API-log lines containing CORR_ID
      api_log_corr_unmodified     : bool  — an API-log line contains CORR_ID byte-for-byte
      downstream_services_observed: int   — downstream services the endpoint actually called
      inventory_log_hits_corr     : int
      payment_log_hits_corr       : int
      no_header_resp_value        : str|None — X-Correlation-ID on the no-header response
      no_header_is_uuid_v4        : bool
      api_log_hits_uuid           : int
      inventory_log_hits_uuid     : int
      payment_log_hits_uuid       : int

    Returns {scenario_label: observed_token in {"true","false","missing"}}.
    """
    out: dict[str, str] = {}
    with_sent = bool(obs.get("with_request_sent"))
    no_hdr_sent = bool(obs.get("no_header_request_sent"))

    def b(flag: bool) -> str:
        return "true" if flag else "false"

    # --- with-header scenarios (require the with-header request) ---
    if with_sent:
        out["resp_header_echo_exact"] = b(obs.get("resp_header_value") == CORR_ID)
        out["api_log_present"] = b(int(obs.get("api_log_hits_corr", 0)) >= 1)
        out["api_log_unmodified"] = b(bool(obs.get("api_log_corr_unmodified")))
        out["downstream_count_ge2"] = b(int(obs.get("downstream_services_observed", 0)) >= 2)
        out["inventory_log_present"] = b(int(obs.get("inventory_log_hits_corr", 0)) >= 1)
        out["payment_log_present"] = b(int(obs.get("payment_log_hits_corr", 0)) >= 1)
    else:
        for s in ("resp_header_echo_exact", "api_log_present", "api_log_unmodified",
                  "downstream_count_ge2", "inventory_log_present", "payment_log_present"):
            out[s] = "missing"

    # --- no-header scenarios (require the no-header request) ---
    if no_hdr_sent:
        out["no_header_uuid_generated"] = b(bool(obs.get("no_header_is_uuid_v4")))
        out["no_header_uuid_in_api_log"] = b(int(obs.get("api_log_hits_uuid", 0)) >= 1)
        out["no_header_uuid_in_inventory"] = b(int(obs.get("inventory_log_hits_uuid", 0)) >= 1)
        out["no_header_uuid_in_payment"] = b(int(obs.get("payment_log_hits_uuid", 0)) >= 1)
    else:
        for s in ("no_header_uuid_generated", "no_header_uuid_in_api_log",
                  "no_header_uuid_in_inventory", "no_header_uuid_in_payment"):
            out[s] = "missing"

    return out


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized propagation contract for this scenario?"""
    return observed_token == IDEAL[scenario]
