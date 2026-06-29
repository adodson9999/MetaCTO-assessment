"""Single source of truth for the local API-gateway-routing fixture topology.

This is the air-gapped Python stand-in for the documented real-world toolchain
(an API gateway — CloudFront/Kong/AWS API Gateway — fronting one WireMock instance
per downstream service, each WireMock logging received requests via its admin API).
It declares the downstream services, the documented gateway routes, and — hidden
from the agents — each route's INTRINSIC routing behavior (which backend the gateway
*really* forwards to, and whether it tampers with the body in transit). This mirrors
the way DummyJSON's real (lenient) behavior is the ground truth for the pagination
build and the timeout-gateway's one non-compliant endpoint is the ground truth there.

Two consumers import this:
  - gateway.py / mock_backend.py — serve these routes/backends with this behavior.
  - data/.../build_gold.py        — authors the agent-facing input spec (the hidden
                                     actual_backend / mutate_body / down flags stripped)
                                     and discovers the gold tokens by PROBING the running
                                     fixture (never by reading the hidden flags here).

The agents are NEVER shown the hidden flags; they only see the documented contract
(service names, and per route: method, path, headers, body, expected_backend,
down_test). Whether the gateway actually routes correctly is discovered by the harness
by querying each backend's /__admin/requests journal — exactly as the task prescribes.
"""
from __future__ import annotations

# Default ports (overridable by the launcher). The gateway is the only target the
# agents/harness send traffic to; the backends' admin APIs are queried by the harness
# (and gold builder) but are never disclosed to the agents.
GATEWAY_PORT = 8920
BACKEND_BASE_PORT = 8921  # users=8921, orders=8922, payments=8923

# The single documented bearer token every route carries. The harness asserts the
# Authorization header survives the hop to the backend byte-for-byte.
AUTH_TOKEN = "Bearer routing-test-token-abc123"

# Downstream services, in the canonical order used to compute "every other backend".
# port_offset is added to BACKEND_BASE_PORT. Each backend returns a uniquely
# identifiable body {"service": "<name>"} so a forwarded response is attributable.
SERVICES = [
    {"name": "users-mock", "port_offset": 0},
    {"name": "orders-mock", "port_offset": 1},
    {"name": "payments-mock", "port_offset": 2},
]

# Documented gateway routes. Each route's `expected_backend` is the contract; the
# gateway forwards method/path/headers/body UNCHANGED (path is not rewritten — the
# backend receives the same path the gateway received) and returns the backend's body
# unchanged. The hidden keys encode the seeded defects:
#   actual_backend : where the gateway REALLY forwards (== expected_backend unless a
#                    misroute defect is seeded).
#   mutate_body    : if True the gateway injects {"gateway_tampered": true} into the
#                    forwarded JSON body — an in-transit body-modification defect.
#   down_test      : if True this route is the service-down probe: during its test the
#                    expected backend is stopped and the gateway must return exactly 503
#                    while NO backend receives the request.
ROUTES = [
    {
        "method": "GET", "path": "/api/users/42",
        "headers": {"Authorization": AUTH_TOKEN},
        "body": None,
        "expected_backend": "users-mock",
        "actual_backend": "users-mock", "mutate_body": False, "down_test": False,
    },
    {
        "method": "POST", "path": "/api/users",
        "headers": {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"},
        "body": {"name": "Ada Lovelace", "role": "engineer"},
        "expected_backend": "users-mock",
        "actual_backend": "users-mock", "mutate_body": False, "down_test": False,
    },
    {
        # DEFECT (misroute): documented for orders-mock, gateway really forwards to
        # payments-mock. The harness must catch the wrong backend receiving it.
        "method": "GET", "path": "/api/orders/7",
        "headers": {"Authorization": AUTH_TOKEN},
        "body": None,
        "expected_backend": "orders-mock",
        "actual_backend": "payments-mock", "mutate_body": False, "down_test": False,
    },
    {
        "method": "POST", "path": "/api/orders",
        "headers": {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"},
        "body": {"item": "widget", "qty": 3},
        "expected_backend": "orders-mock",
        "actual_backend": "orders-mock", "mutate_body": False, "down_test": False,
    },
    {
        # DEFECT (in-transit body mutation): correct backend, but the gateway injects a
        # field so the body the backend logs is NOT byte-for-byte what the caller sent.
        "method": "PUT", "path": "/api/payments/9",
        "headers": {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"},
        "body": {"amount": 100, "currency": "USD"},
        "expected_backend": "payments-mock",
        "actual_backend": "payments-mock", "mutate_body": True, "down_test": False,
    },
    {
        # SERVICE-DOWN probe: payments-mock is stopped during this test; the gateway
        # must answer exactly 503 and no backend may log the request.
        "method": "GET", "path": "/api/payments/9",
        "headers": {"Authorization": AUTH_TOKEN},
        "body": None,
        "expected_backend": "payments-mock",
        "actual_backend": "payments-mock", "mutate_body": False, "down_test": True,
    },
]


def service_names() -> list[str]:
    return [s["name"] for s in SERVICES]


def backend_port(name: str) -> int:
    for s in SERVICES:
        if s["name"] == name:
            return BACKEND_BASE_PORT + s["port_offset"]
    raise KeyError(name)


def route_map() -> dict:
    """(method, path) -> the full route record for the gateway router."""
    return {(r["method"].upper(), r["path"]): r for r in ROUTES}


def agent_facing_spec(gateway_url: str, host: str = "127.0.0.1") -> dict:
    """The INPUT the four agents are briefed from. The hidden routing flags
    (actual_backend, mutate_body) are REMOVED — the agent is told only the documented
    contract. `down_test` is kept because the expected behavior of that route (a 503)
    is part of the documented contract the agent must encode.

    A harness-only `_services_admin` block (admin base URLs) is included for the
    harness/gold to query each backend's journal; it is stripped before briefing the
    agent (see routing.route_brief / build the per-route brief)."""
    return {
        "title": "Local API-gateway routing contract (authored for the gateway-routing task)",
        "description": (
            "An API gateway fronts one mock backend per downstream service (the "
            "air-gapped local stand-in for WireMock instances behind a Kong/AWS API "
            "Gateway). Each documented route must be forwarded to exactly one backend "
            "with method, path, headers, and body unchanged, and the backend's response "
            "returned to the caller unchanged. Agents construct the routing test plan "
            "from this contract; ground truth is each backend's real /__admin/requests "
            "journal after the gateway forwards the request."
        ),
        "target": gateway_url,
        "auth_token": AUTH_TOKEN,
        "services": service_names(),
        "routes": [
            {
                "method": r["method"],
                "path": r["path"],
                "headers": dict(r["headers"]),
                "body": (dict(r["body"]) if isinstance(r["body"], dict) else r["body"]),
                "expected_backend": r["expected_backend"],
                "down_test": r["down_test"],
            }
            for r in ROUTES
        ],
        "_services_admin": {
            s["name"]: f"http://{host}:{BACKEND_BASE_PORT + s['port_offset']}"
            for s in SERVICES
        },
    }
