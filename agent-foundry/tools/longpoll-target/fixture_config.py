"""Single source of truth for the local longpoll-target fixture topology.

This is the air-gapped Python stand-in for a real long-poll / hanging-GET backend
(the documented toolchain: a server that holds an event-less GET open until POLL_TIMEOUT
then closes 204, and closes 200 with the event the moment one is published). It declares
the channels, each channel's documented poll/trigger paths, the documented event_type,
and each channel's INTRINSIC compliance behavior — exactly the way DummyJSON's real
(lenient) behavior is the ground truth for the pagination build.

Two consumers import this:
  - server.py             — serves these channels with this behavior.
  - data/.../build_gold.py — authors the agent-facing input spec (compliance flags
                             stripped) and discovers the gold tokens by PROBING the
                             running fixture (never by reading the flags here).

The agents are NEVER shown the `compliant` flags; they only see the documented contract
(channel, poll_path, trigger_path, poll_timeout_s, expected_event_type). Whether a channel
actually honors the long-poll contract is discovered by the harness.
"""
from __future__ import annotations

# Canonical contract for this build: documented poll timeout = 5 whole seconds.
# (The task's example is 30 s; 5 s is used here so every real-time no-event poll
# resolves in ~5 s, keeping gold-building and the four live agent runs feasible. The
# fixed +/-2 s tolerance from the task is the contract regardless of the value.)
POLL_TIMEOUT_S = 5

# How long after a poll opens the harness waits before triggering the event (well within
# both POLL_TIMEOUT_S and the task's 10 s trigger bound).
TRIGGER_DELAY_S = 1.5

# The non-compliant channel's extra post-publish stall (seconds) — pushes the event
# response past the 2 s bound. A real, catchable defect.
NONCOMPLIANT_EVENT_STALL_S = 3.0

CHANNELS = [
    {
        "channel": "orders",
        "poll_path": "/poll/orders",
        "trigger_path": "/publish/orders",
        "poll_timeout_s": POLL_TIMEOUT_S,
        "expected_event_type": "order.created",
        "secondary_field": "order_id",     # the non-empty secondary field the event carries
        "compliant": True,
    },
    {
        "channel": "inventory",
        "poll_path": "/poll/inventory",
        "trigger_path": "/publish/inventory",
        "poll_timeout_s": POLL_TIMEOUT_S,
        "expected_event_type": "inventory.updated",
        "secondary_field": "sku",
        # Deliberately NON-COMPLIANT: on an event-less poll it returns 200 with a
        # non-empty body (never 204 empty); on an event it stalls ~3 s after the publish
        # (breaking the 2 s bound) and emits the WRONG event_type ("message"). A real,
        # catchable defect — the long-poll equivalent of DummyJSON's lenient pagination.
        "compliant": False,
    },
    {
        "channel": "profile",
        "poll_path": "/poll/profile",
        "trigger_path": "/publish/profile",
        "poll_timeout_s": POLL_TIMEOUT_S,
        "expected_event_type": "profile.updated",
        "secondary_field": "user_id",
        "compliant": True,
    },
]


def by_channel() -> dict:
    """channel-name -> its full config (for the server router)."""
    return {c["channel"]: c for c in CHANNELS}


def poll_route_map() -> dict:
    """poll_path -> channel config (paths are globally unique by construction)."""
    return {c["poll_path"]: c for c in CHANNELS}


def trigger_route_map() -> dict:
    """trigger_path -> channel config."""
    return {c["trigger_path"]: c for c in CHANNELS}


def agent_facing_spec(target: str) -> dict:
    """The INPUT the four agents are briefed from. Compliance flags + the server's
    secondary-field name are REMOVED — the agent is told only the documented contract,
    never the answer."""
    return {
        "title": "Local longpoll-target contract (authored for the long-polling task)",
        "description": (
            "Each channel exposes a long-poll GET (poll_path) that is documented to hold an "
            "event-less connection open for poll_timeout_s seconds and then close with 204 and "
            "an empty body, and to close with 200 and the event the moment one is published via "
            "a separate POST to trigger_path. Agents construct the long-poll test plan from this; "
            "ground truth is the fixture's real observed behavior when the harness opens the "
            "connections and triggers events at real wall-clock timing. The fixture is the "
            "air-gapped local stand-in for a real long-poll/hanging-GET backend; DummyJSON has no "
            "long-poll endpoint and is not used or modified."
        ),
        "target": target,
        "poll_timeout_s": POLL_TIMEOUT_S,
        "channels": [
            {
                "channel": c["channel"],
                "poll_path": c["poll_path"],
                "trigger_path": c["trigger_path"],
                "poll_timeout_s": c["poll_timeout_s"],
                "expected_event_type": c["expected_event_type"],
            }
            for c in CHANNELS
        ],
    }
