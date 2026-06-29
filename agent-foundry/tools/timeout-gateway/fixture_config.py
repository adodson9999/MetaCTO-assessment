"""Single source of truth for the local timeout-gateway fixture topology.

This is the air-gapped Python stand-in for the documented real-world toolchain
(WireMock upstream stub + Toxiproxy latency toxic). It declares the services, the
documented upstream-dependent endpoints, the documented upstream timeout, and each
endpoint's INTRINSIC compliance behavior — exactly the way DummyJSON's real (lenient)
behavior is the ground truth for the pagination build.

Two consumers import this:
  - gateway.py            — serves these endpoints with this behavior.
  - data/.../build_gold.py — authors the agent-facing input spec (compliance flags
                             stripped) and discovers the gold tokens by PROBING the
                             running gateway (never by reading the flags here).

The agents are NEVER shown the `compliant` flags; they only see the documented
contract (service, upstream_timeout_s, buffer_s, restore_max_ms, endpoint list).
Whether an endpoint actually enforces the timeout is discovered by the harness.
"""
from __future__ import annotations

# Canonical contract per the user's Phase-2 sign-off: documented upstream timeout
# = 10s, fixed grace buffer = 2s (=> max_wait 12s), post-recovery budget = 500ms.
UPSTREAM_TIMEOUT_S = 10
BUFFER_S = 2
RESTORE_MAX_MS = 500

# The latency the harness injects (Toxiproxy "latency" toxic) — far above the
# timeout, so a correct gateway must give up at ~UPSTREAM_TIMEOUT_S, never wait it out.
INJECTED_DELAY_S = 60

SERVICES = [
    {
        "service": "orders-api",
        "upstream_timeout_s": UPSTREAM_TIMEOUT_S,
        "buffer_s": BUFFER_S,
        "restore_max_ms": RESTORE_MAX_MS,
        "endpoints": [
            {"method": "GET", "path": "/orders", "compliant": True},
            {"method": "GET", "path": "/orders/recent", "compliant": True},
        ],
    },
    {
        "service": "inventory-api",
        "upstream_timeout_s": UPSTREAM_TIMEOUT_S,
        "buffer_s": BUFFER_S,
        "restore_max_ms": RESTORE_MAX_MS,
        "endpoints": [
            {"method": "GET", "path": "/inventory", "compliant": True},
            # Deliberately NON-COMPLIANT: on upstream timeout it returns 500 (not
            # 504/408), leaks the upstream URL + a stack frame in the body, and keeps
            # the TCP connection open (no Connection: close). A real, catchable defect.
            {"method": "GET", "path": "/inventory/low-stock", "compliant": False},
        ],
    },
    {
        "service": "profile-api",
        "upstream_timeout_s": UPSTREAM_TIMEOUT_S,
        "buffer_s": BUFFER_S,
        "restore_max_ms": RESTORE_MAX_MS,
        "endpoints": [
            {"method": "GET", "path": "/profile", "compliant": True},
            {"method": "GET", "path": "/profile/preferences", "compliant": True},
        ],
    },
]


def path_map() -> dict:
    """path -> {service, upstream_timeout_s, compliant} for the gateway router.
    Paths are globally unique across services by construction."""
    out = {}
    for svc in SERVICES:
        for ep in svc["endpoints"]:
            out[ep["path"]] = {
                "service": svc["service"],
                "upstream_timeout_s": svc["upstream_timeout_s"],
                "compliant": ep["compliant"],
            }
    return out


def agent_facing_spec(target: str) -> dict:
    """The INPUT the four agents are briefed from. Compliance flags are REMOVED —
    the agent is told only the documented contract, never the answer."""
    return {
        "title": "Local timeout-gateway contract (authored for the timeout-handling task)",
        "description": (
            "Each service calls an upstream service and is documented to enforce an "
            "upstream timeout of upstream_timeout_s seconds, returning 504/408 (not "
            "hanging) when the upstream is slow, then recovering to <restore_max_ms once "
            "the upstream is healthy. Agents construct the timeout test plan from this; "
            "ground truth is the gateway's real observed behavior under an injected "
            "60-second upstream delay. The gateway is the air-gapped local stand-in for "
            "a WireMock upstream stub fronted by a Toxiproxy latency toxic."
        ),
        "target": target,
        "injected_delay_s": INJECTED_DELAY_S,
        "services": [
            {
                "service": svc["service"],
                "upstream_timeout_s": svc["upstream_timeout_s"],
                "buffer_s": svc["buffer_s"],
                "restore_max_ms": svc["restore_max_ms"],
                "endpoints": [
                    {"method": ep["method"], "path": ep["path"]}
                    for ep in svc["endpoints"]
                ],
            }
            for svc in SERVICES
        ],
    }
