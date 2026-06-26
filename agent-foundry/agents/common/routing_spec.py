"""Canonical scenario structure for the API-gateway-routing testing task.

ONE definition of the routing test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-api-gateway-routing/build_gold.py), and
  - the harness (agents/common/routing.py) — which executes whatever plan an agent
    emitted against the local gateway and scores it on the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no sockets. Keeps agent output and the gold set on the
same (route, scenario) key scheme so the judge compares them field-for-field.

Target reality (the local routing-gateway fixture, tested as-is):
  - An API gateway fronts one WireMock-equivalent mock backend per service. Each
    documented route must be forwarded to EXACTLY one backend with method, path,
    headers, and body unchanged, and the backend's response returned unchanged.
  - Two routes carry seeded defects (one misroute, one in-transit body mutation) and
    one route is the service-down probe (expects 503). Those gaps are real QA findings
    the suite must surface — exactly like DummyJSON's lenient pagination.

A plan for one route (the agent's output, and the reference) looks like:
  {
    "route": "/api/users/42",
    "method": "GET",
    "headers": {"Authorization": "Bearer routing-test-token-abc123"},
    "body": null,
    "expected_backend": "users-mock",
    "other_backends": ["orders-mock", "payments-mock"],
    "down_test": false
  }
"""
from __future__ import annotations

# ----- plan scenarios (framework-attributable: derived from the agent's emitted plan)
PLAN_SCENARIOS = [
    "plan_method",            # the request method the plan will send
    "plan_path",              # the gateway path the plan will hit
    "plan_auth_present",      # plan headers carry the documented Authorization token
    "plan_body_match",        # plan body equals the documented body
    "plan_expected_backend",  # the backend the plan expects to receive it
    "plan_other_backends",    # the "every other backend must be zero" set is correct
    "plan_down_test",         # the down-test flag is copied correctly
]

# ----- exec scenarios for a NORMAL route (API property: from executing the plan)
EXEC_SCENARIOS_NORMAL = [
    "exec_correct_backend",     # the expected backend logged exactly one request, right method+path
    "exec_only_expected",       # every OTHER backend logged zero for this call
    "exec_body_verbatim",       # the backend's logged body == the body sent (byte-for-byte)
    "exec_auth_forwarded",      # the backend's logged headers include Authorization
    "exec_response_unchanged",  # gateway response body == expected backend's configured body
    "exec_status_2xx",          # gateway returned a 2xx
]

# ----- exec scenarios for the SERVICE-DOWN route
EXEC_SCENARIOS_DOWN = [
    "exec_status_503",          # gateway returned exactly 503
    "exec_no_backend_received",  # no backend (incl. expected) logged the request
]


def exec_scenarios_for(down_test: bool) -> list[str]:
    return list(EXEC_SCENARIOS_DOWN if down_test else EXEC_SCENARIOS_NORMAL)


def scenarios_for(route_cfg: dict) -> list[str]:
    """The full ordered scenario set scored for one route."""
    return list(PLAN_SCENARIOS) + exec_scenarios_for(bool(route_cfg.get("down_test")))


def ideal_tokens(route_cfg: dict) -> dict:
    """The token a perfectly-routing gateway + a perfectly-constructed plan produce
    for every scenario of this route. Gold records the REAL token; where it differs
    from this ideal is a genuine QA finding about the gateway, not an agent bug."""
    ideal = {
        "plan_method": route_cfg["method"].upper(),
        "plan_path": route_cfg["path"],
        "plan_auth_present": "true",
        "plan_body_match": "true",
        "plan_expected_backend": route_cfg["expected_backend"],
        "plan_other_backends": "true",
        "plan_down_test": "true" if route_cfg.get("down_test") else "false",
    }
    for s in exec_scenarios_for(bool(route_cfg.get("down_test"))):
        ideal[s] = "true"
    return ideal


def build_reference_plan(route_cfg: dict) -> dict:
    """The canonical CORRECT plan for one route, derived deterministically: echo the
    documented request, name the expected backend, and compute other_backends as the
    documented service list minus the expected backend, in the documented order."""
    others = [s for s in route_cfg["services"] if s != route_cfg["expected_backend"]]
    body = route_cfg.get("body")
    return {
        "route": route_cfg["path"],
        "method": route_cfg["method"].upper(),
        "headers": dict(route_cfg["headers"]),
        "body": (dict(body) if isinstance(body, dict) else body),
        "expected_backend": route_cfg["expected_backend"],
        "other_backends": others,
        "down_test": bool(route_cfg.get("down_test")),
    }


# --------------------------------------------------------------------------- #
# Plan evaluation (compare an emitted plan to the documented route contract)
# --------------------------------------------------------------------------- #
def _auth_value(headers) -> str | None:
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == "authorization":
            return v
    return None


def evaluate_plan(route_cfg: dict, plan: dict | None) -> dict:
    """Observed token per plan scenario, computed by comparing the plan's fields to
    the documented route contract. Missing/garbled fields score 'missing'/'false'."""
    obs: dict[str, str] = {}
    if not isinstance(plan, dict):
        return {s: "missing" for s in PLAN_SCENARIOS}

    m = plan.get("method")
    obs["plan_method"] = m.upper() if isinstance(m, str) else "missing"

    p = plan.get("route")
    obs["plan_path"] = p if isinstance(p, str) else "missing"

    auth = _auth_value(plan.get("headers"))
    expected_auth = _auth_value(route_cfg["headers"])
    if auth is None:
        obs["plan_auth_present"] = "missing"
    else:
        obs["plan_auth_present"] = "true" if auth == expected_auth else "false"

    if "body" not in plan:
        obs["plan_body_match"] = "missing"
    else:
        obs["plan_body_match"] = "true" if plan.get("body") == route_cfg.get("body") else "false"

    eb = plan.get("expected_backend")
    obs["plan_expected_backend"] = eb if isinstance(eb, str) else "missing"

    ob = plan.get("other_backends")
    if not isinstance(ob, list):
        obs["plan_other_backends"] = "missing"
    else:
        expected_others = {s for s in route_cfg["services"] if s != route_cfg["expected_backend"]}
        obs["plan_other_backends"] = "true" if set(ob) == expected_others else "false"

    dt = plan.get("down_test")
    obs["plan_down_test"] = ("true" if dt else "false") if isinstance(dt, bool) else "missing"
    return obs


# --------------------------------------------------------------------------- #
# Exec evaluation (from the real fixture observation of one executed call)
# --------------------------------------------------------------------------- #
def evaluate_exec(route_cfg: dict, obs: dict | None) -> dict:
    """Observed token per exec scenario from one executed call.

    obs (normal route): {
        "gateway_status": int|None,
        "gateway_body": str|None,                 # raw gateway response body
        "sent_body": str|None,                    # the body string the harness sent
        "journals": {service: [ {method, path, headers, body} ... ]},  # per-backend log
    }
    obs (down route): same shape; journals should all be empty and status == 503.
    A None obs (the plan never produced a sendable request) scores every scenario 'missing'.
    """
    down = bool(route_cfg.get("down_test"))
    labels = exec_scenarios_for(down)
    if obs is None:
        return {s: "missing" for s in labels}

    journals = obs.get("journals") or {}
    expected = route_cfg["expected_backend"]
    method = route_cfg["method"].upper()
    path = route_cfg["path"]

    if down:
        out = {}
        out["exec_status_503"] = "true" if obs.get("gateway_status") == 503 else "false"
        total = sum(len(v) for v in journals.values())
        out["exec_no_backend_received"] = "true" if total == 0 else "false"
        return out

    exp_log = journals.get(expected, [])
    # the expected backend got exactly one request, with the right method+path
    matching = [r for r in exp_log
                if r.get("method", "").upper() == method
                and (r.get("path", "").split("?", 1)[0] == path)]
    out: dict[str, str] = {}
    out["exec_correct_backend"] = "true" if len(matching) == 1 else "false"

    others_total = sum(len(v) for k, v in journals.items() if k != expected)
    out["exec_only_expected"] = "true" if others_total == 0 else "false"

    sent = obs.get("sent_body")
    if matching:
        logged_body = matching[0].get("body", "")
        out["exec_body_verbatim"] = "true" if logged_body == (sent or "") else "false"
        has_auth = any(isinstance(k, str) and k.lower() == "authorization"
                       for k in (matching[0].get("headers") or {}))
        out["exec_auth_forwarded"] = "true" if has_auth else "false"
    else:
        out["exec_body_verbatim"] = "false"
        out["exec_auth_forwarded"] = "false"

    import json
    configured = json.dumps({"service": expected}).encode().decode()
    gw_body = obs.get("gateway_body")
    out["exec_response_unchanged"] = "true" if gw_body == configured else "false"

    st = obs.get("gateway_status")
    out["exec_status_2xx"] = "true" if isinstance(st, int) and 200 <= st < 300 else "false"
    return out


def forwarding_pass(route_cfg: dict, exec_obs_tokens: dict) -> bool:
    """Headline Route-Forwarding test: a route's request was forwarded to exactly the
    correct single backend with unmodified body AND unmodified response returned (or,
    for the down route, the gateway returned exactly 503 and no backend received it).
    Every exec scenario for the route must be 'true'."""
    labels = exec_scenarios_for(bool(route_cfg.get("down_test")))
    return all(exec_obs_tokens.get(s) == "true" for s in labels)


def correct(route_cfg: dict, scenario: str, observed_token: str) -> bool:
    """Did the gateway + plan behave per the idealized routing contract for this
    scenario (token equals the ideal)?"""
    return observed_token == ideal_tokens(route_cfg).get(scenario)
