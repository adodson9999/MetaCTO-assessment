"""Canonical scenario structure for the API header-propagation testing task.

ONE definition of the propagation test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/validate-header-propagation/build_gold.py), and
  - the harness (agents/common/header.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested AS-IS — never modified):
  - A single monolithic service. It does NOT echo X-Correlation-ID in responses,
    does NOT log request headers (the request IS logged, but without the id), makes
    ZERO downstream service calls, and does NOT auto-generate a UUID when no
    X-Correlation-ID is sent. So the IDEAL propagation contract (id echoed + logged +
    propagated to >=2 downstream logs + auto-UUID when absent) is what each runtime
    scenario's `ideal` token encodes; the gold records the API's REAL token. Where
    they differ is a genuine QA finding about DummyJSON, not an agent bug.

Two scenario families per endpoint:
  A) PLAN scenarios  — did the agent EMIT the correct, complete propagation test plan?
     (deterministic, pure-over-the-plan; gives the leaderboard resolution.)
  B) RUNTIME scenarios — what did DummyJSON actually DO when the plan ran?
     (the honest Header-Propagation-Rate QA finding; 0% for DummyJSON.)
"""
from __future__ import annotations

# Fixed test correlation id — used verbatim, never normalized (Step 1 of the task).
CORR_ID = "test-corr-550e8400-e29b-41d4-a716"
# Exact header name, casing preserved (HTTP header names are case-insensitive on the
# wire, but the TEST must assert the documented spelling).
HEADER_NAME = "X-Correlation-ID"
# Placeholder the harness substitutes with a real token from POST /auth/login.
TOKEN_PLACEHOLDER = "<valid_token>"

# A) PLAN-correctness scenarios (ideal == gold == "true"; the reference plan is correct
#    by construction). Each rewards one pin-downable property of a correct propagation test.
PLAN_SCENARIOS = [
    ("plan_correlation_id_exact",   "true"),   # plan.correlation_id == CORR_ID, verbatim
    ("plan_header_name_exact",      "true"),   # plan.header_name == "X-Correlation-ID", exact casing
    ("plan_with_header_present",    "true"),   # with-header request carries header_name:CORR_ID (+ Bearer when auth)
    ("plan_no_header_absent",       "true"),   # no-header request present and does NOT carry header_name
    ("plan_assertions_complete",    "true"),   # assertions list covers all RUNTIME scenario labels
]

# B) RUNTIME-observation scenarios (the propagation QA finding).
RUNTIME_SCENARIOS = [
    ("resp_header_echo_exact",        "true"),    # with-header resp echoes the sent id, byte-for-byte
    ("api_log_present",               "true"),    # >=1 API-server-log entry contains the sent id
    ("api_log_unmodified",            "true"),    # the logged id value equals the sent id (not truncated/lowercased)
    ("downstream_services_count",     ">=2"),     # endpoint calls at least 2 downstream services
    ("downstream_log_present",        "true"),    # the sent id appears in EVERY downstream service log
    ("no_header_uuid_generated",      "true"),    # no-header resp carries an auto-generated UUID v4
    ("no_header_uuid_in_api_log",     "true"),    # that generated id appears in the API server log
    ("no_header_uuid_in_downstream",  "true"),    # that generated id appears in every downstream log
]
RUNTIME_LABELS = [s for s, _ in RUNTIME_SCENARIOS]

SCENARIOS = PLAN_SCENARIOS + RUNTIME_SCENARIOS
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)


def build_reference_plan(endpoint: dict) -> dict:
    """The canonical CORRECT propagation test plan for one endpoint, derived
    deterministically. `endpoint` = {name, method, path, auth(bool), body?}."""
    method = endpoint["method"]
    path = endpoint["path"]
    auth = bool(endpoint.get("auth"))
    body = endpoint.get("body")

    with_headers = {HEADER_NAME: CORR_ID}
    no_headers: dict[str, str] = {}
    if auth:
        with_headers = {"Authorization": f"Bearer {TOKEN_PLACEHOLDER}", **with_headers}
        no_headers = {"Authorization": f"Bearer {TOKEN_PLACEHOLDER}"}

    def _req(headers: dict) -> dict:
        r = {"method": method, "path": path, "headers": headers}
        if body is not None:
            r["body"] = body
        return r

    return {
        "endpoint": endpoint["name"],
        "method": method,
        "path": path,
        "auth_required": auth,
        "correlation_id": CORR_ID,
        "header_name": HEADER_NAME,
        "with_header_request": _req(with_headers),
        "no_header_request": _req(no_headers),
        "assertions": list(RUNTIME_LABELS),
    }


# --------------------------------------------------------------------------- #
# Evaluation — observed token per scenario
# --------------------------------------------------------------------------- #
def _lc_keys(d) -> dict:
    return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}


def evaluate_plan(plan: dict, endpoint: dict) -> dict:
    """PLAN-correctness observed tokens — pure over the agent's emitted plan."""
    plan = plan if isinstance(plan, dict) else {}
    auth = bool(endpoint.get("auth"))
    cid = plan.get("correlation_id")
    hn = plan.get("header_name")
    wh = plan.get("with_header_request") if isinstance(plan.get("with_header_request"), dict) else {}
    nh = plan.get("no_header_request") if isinstance(plan.get("no_header_request"), dict) else {}
    wh_headers = wh.get("headers") if isinstance(wh.get("headers"), dict) else {}
    nh_headers = nh.get("headers") if isinstance(nh.get("headers"), dict) else {}

    # with-header request carries the correlation header with the plan's own id value
    wh_has_corr = any(str(k).lower() == HEADER_NAME.lower() and v == cid for k, v in wh_headers.items())
    wh_auth = str(_lc_keys(wh_headers).get("authorization", "")).lower().startswith("bearer ")
    wh_ok = bool(wh_has_corr and wh.get("method") and wh.get("path") and (wh_auth or not auth))

    # no-header request present and free of the correlation header
    nh_has_corr = any(str(k).lower() == HEADER_NAME.lower() for k in nh_headers)
    nh_ok = bool(nh.get("method") and nh.get("path") and not nh_has_corr)

    assertions = plan.get("assertions") if isinstance(plan.get("assertions"), list) else []

    return {
        "plan_correlation_id_exact": "true" if cid == CORR_ID else "false",
        "plan_header_name_exact": "true" if hn == HEADER_NAME else "false",
        "plan_with_header_present": "true" if wh_ok else "false",
        "plan_no_header_absent": "true" if nh_ok else "false",
        "plan_assertions_complete": "true" if set(assertions) >= set(RUNTIME_LABELS) else "false",
    }


def evaluate_runtime(obs: dict) -> dict:
    """RUNTIME observed tokens from the harness's real run.

    obs = {
      "with_header": {"sent_id": str, "resp_corr_value": str|None,
                      "api_log_hits_exact": int, "api_log_hits_modified": int},
      "no_header":   {"resp_corr_value": str|None, "generated_is_uuidv4": bool,
                      "api_log_hits_generated": int},
      "downstream_services": [names...],
      "downstream_all_have_id": bool|None,
      "downstream_all_have_generated": bool|None,
    }
    """
    obs = obs if isinstance(obs, dict) else {}
    wh = obs.get("with_header", {}) or {}
    nh = obs.get("no_header", {}) or {}
    services = obs.get("downstream_services", []) or []
    n_services = len(services)
    out: dict[str, str] = {}

    # resp_header_echo_exact
    v = wh.get("resp_corr_value")
    sent = wh.get("sent_id")
    out["resp_header_echo_exact"] = "absent" if v is None else ("true" if v == sent else "modified")

    # api_log_present / api_log_unmodified
    ex = int(wh.get("api_log_hits_exact", 0) or 0)
    mod = int(wh.get("api_log_hits_modified", 0) or 0)
    out["api_log_present"] = "true" if (ex > 0 or mod > 0) else "false"
    out["api_log_unmodified"] = "true" if ex > 0 else ("modified" if mod > 0 else "absent")

    # downstream
    out["downstream_services_count"] = str(n_services)
    out["downstream_log_present"] = (
        "n/a" if n_services == 0 else ("true" if obs.get("downstream_all_have_id") else "false")
    )

    # no-header auto-UUID
    nv = nh.get("resp_corr_value")
    if nv is None:
        out["no_header_uuid_generated"] = "absent"
    else:
        out["no_header_uuid_generated"] = "true" if nh.get("generated_is_uuidv4") else "non_uuid"
    out["no_header_uuid_in_api_log"] = (
        "n/a" if nv is None else ("true" if int(nh.get("api_log_hits_generated", 0) or 0) > 0 else "false")
    )
    out["no_header_uuid_in_downstream"] = (
        "n/a" if (n_services == 0 or nv is None)
        else ("true" if obs.get("downstream_all_have_generated") else "false")
    )
    return out


def evaluate(plan: dict, endpoint: dict, obs: dict) -> dict:
    """Full observed-token map for every scenario (plan + runtime)."""
    merged = dict(evaluate_plan(plan, endpoint))
    merged.update(evaluate_runtime(obs))
    for label in SCENARIO_LABELS:
        merged.setdefault(label, "missing")
    return merged


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API/test satisfy the IDEAL propagation contract for this scenario?
    Used only for the headline Header-Propagation-Rate finding, NOT for fidelity."""
    ideal = IDEAL[scenario]
    if scenario == "downstream_services_count":
        try:
            return int(observed_token) >= 2
        except Exception:  # noqa
            return False
    return observed_token == ideal
