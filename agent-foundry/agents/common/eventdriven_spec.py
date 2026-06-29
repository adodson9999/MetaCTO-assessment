"""Canonical scenario structure for the Test-Event-Driven-API-Triggers task.

ONE definition of the topic catalogue + the event-trigger test plan + the per-scenario
evaluation, shared by:
  - the local event-driven substrate config (data/.../topics.json), written from TOPICS,
  - the deterministic gold reference (data/.../build_gold.py), and
  - the harness (agents/common/eventdriven.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same (topic, scenario) key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same key scheme
so the judge can compare them field-for-field.

Target reality:
  - DummyJSON consumes NO message topics, ships NO consumer, NO dead-letter queue, and NO
    consumer-liveness signal (its only AWS usage is S3 object storage). An event published
    nowhere changes nothing, so against DummyJSON-as-the-system every scenario is a
    no-op: Event Processing Success Rate = 0% and Dead-Letter Queue Delivery Rate = 0%.
    That is a genuine QA finding (the documented event-driven behavior is not present),
    recorded as the contrast.
  - To exercise the IDEAL contract the agents are briefed from, a local air-gapped
    substrate (tools/eventbus_target/app.py) implements a correct consumer. Against that
    substrate a correct test plan yields 100% on both rates. The four agents are ranked on
    fidelity-to-gold (did they construct the right events + assertions), which is
    substrate-independent.

The idealized contract per topic (the world the agents are told about):
  - Each topic carries a typed event whose payload must contain every `required_fields`
    entry. A well-formed event drives `resource/<resource_id>.<state_field>` from
    `pre_state` to `expected_state`, observable within 5 seconds.
  - A malformed event (exactly one required field dropped, the `drop_field`) must be
    logged as an ERROR naming its message id + a parse error, routed to the DLQ within
    30 seconds, leave the resource state unchanged, and never crash the consumer (health
    stays 200).

A plan for one topic (the agent's output, and the reference) looks like:
  {
    "topic": "order.payment.completed",
    "resource": "orders", "resource_id": "order-1001",
    "state_field": "status", "expected_state": "paid",
    "event_type": "order.payment.completed",
    "required_fields": ["event_id","event_type","resource_id","occurred_at","amount"],
    "wellformed_event": { ...all required fields populated... },
    "malformed_event":  { ...wellformed_event minus the one drop_field... },
    "poll": {"interval_ms": 500, "timeout_seconds": 5},
    "assertions": {"health_after_seconds": 60, "dlq_within_seconds": 30,
                   "error_log_within_seconds": 30, "expect_state_unchanged": true}
  }
"""
from __future__ import annotations

# Fixed plan constants (the documented SLA / contract values).
POLL_INTERVAL_MS = 500
POLL_TIMEOUT_SECONDS = 5
HEALTH_AFTER_SECONDS = 60          # documented; harness uses a settable settle window
DLQ_WITHIN_SECONDS = 30
ERROR_LOG_WITHIN_SECONDS = 30

# The topic catalogue: one source of truth for the substrate consumer, the gold, and
# the agent brief. Each topic maps one typed event to one documented state transition,
# with a designated `drop_field` whose omission makes the event malformed.
TOPICS = [
    {
        "topic": "order.payment.completed",
        "event_type": "order.payment.completed",
        "resource": "orders", "resource_id": "order-1001",
        "state_field": "status", "pre_state": "pending", "expected_state": "paid",
        "required_fields": ["event_id", "event_type", "resource_id", "occurred_at", "amount"],
        "drop_field": "amount",
        "field_values": {
            "event_id": "evt-pay-0001", "event_type": "order.payment.completed",
            "resource_id": "order-1001", "occurred_at": "2026-06-25T12:00:00Z",
            "amount": 49.99,
        },
    },
    {
        "topic": "account.email.verified",
        "event_type": "account.email.verified",
        "resource": "accounts", "resource_id": "acct-2002",
        "state_field": "status", "pre_state": "unverified", "expected_state": "verified",
        "required_fields": ["event_id", "event_type", "resource_id", "occurred_at", "email"],
        "drop_field": "email",
        "field_values": {
            "event_id": "evt-acct-0002", "event_type": "account.email.verified",
            "resource_id": "acct-2002", "occurred_at": "2026-06-25T12:01:00Z",
            "email": "user@example.com",
        },
    },
    {
        "topic": "inventory.item.depleted",
        "event_type": "inventory.item.depleted",
        "resource": "inventory", "resource_id": "sku-3003",
        "state_field": "stock_state", "pre_state": "in_stock", "expected_state": "out_of_stock",
        "required_fields": ["event_id", "event_type", "resource_id", "occurred_at", "quantity"],
        "drop_field": "quantity",
        "field_values": {
            "event_id": "evt-inv-0003", "event_type": "inventory.item.depleted",
            "resource_id": "sku-3003", "occurred_at": "2026-06-25T12:02:00Z",
            "quantity": 0,
        },
    },
    {
        "topic": "ticket.issue.resolved",
        "event_type": "ticket.issue.resolved",
        "resource": "tickets", "resource_id": "tkt-4004",
        "state_field": "status", "pre_state": "open", "expected_state": "resolved",
        "required_fields": ["event_id", "event_type", "resource_id", "occurred_at", "resolution"],
        "drop_field": "resolution",
        "field_values": {
            "event_id": "evt-tkt-0004", "event_type": "ticket.issue.resolved",
            "resource_id": "tkt-4004", "occurred_at": "2026-06-25T12:03:00Z",
            "resolution": "fixed",
        },
    },
]

# The full, ordered scenario set scored per topic (the metric denominator). `ideal` is
# the token a perfectly-behaving event-driven service produces.
SCENARIOS = [
    # ---- well-formed event => Event Processing Success Rate components ----
    ("wellformed_state_changed",     "true"),   # resource reached SOME new state
    ("wellformed_correct_value",     "true"),   # ...and it equals expected_state
    ("wellformed_within_5s",         "true"),   # ...within the 5s SLA
    ("wellformed_no_consumer_errors","true"),   # no ERROR/WARN for this event
    # ---- malformed event => DLQ Delivery Rate + robustness components ----
    ("malformed_no_crash",           "true"),   # health 200 after the malformed event
    ("malformed_error_logged",       "true"),   # ERROR within 30s naming msg id + parse error
    ("malformed_in_dlq",             "true"),   # malformed message in DLQ within 30s
    ("malformed_no_state_change",    "true"),   # resource still at pre_state
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)
WELLFORMED_LABELS = [s for s, _ in SCENARIOS if s.startswith("wellformed_")]


def ideal_for(scenario: str) -> str:
    return IDEAL[scenario]


def build_reference_plan(topic: dict) -> dict:
    """The canonical CORRECT event-trigger plan for one topic, derived deterministically:
    a well-formed event carrying every required field, a malformed event identical except
    the one drop_field is omitted, the 500ms/5s poll, and the fixed malformed assertions."""
    wellformed = dict(topic["field_values"])
    malformed = {k: v for k, v in topic["field_values"].items() if k != topic["drop_field"]}
    return {
        "topic": topic["topic"],
        "resource": topic["resource"],
        "resource_id": topic["resource_id"],
        "state_field": topic["state_field"],
        "expected_state": topic["expected_state"],
        "event_type": topic["event_type"],
        "required_fields": list(topic["required_fields"]),
        "wellformed_event": wellformed,
        "malformed_event": malformed,
        "poll": {"interval_ms": POLL_INTERVAL_MS, "timeout_seconds": POLL_TIMEOUT_SECONDS},
        "assertions": {
            "health_after_seconds": HEALTH_AFTER_SECONDS,
            "dlq_within_seconds": DLQ_WITHIN_SECONDS,
            "error_log_within_seconds": ERROR_LOG_WITHIN_SECONDS,
            "expect_state_unchanged": True,
        },
    }


def evaluate(topic: dict, obs: dict) -> dict:
    """Compute the observed token for every scenario from the harness's raw measurement.

    obs is the harness's raw measurement for one topic:
      {
        "wf_state_after": str|None,     # resource state after the well-formed event
        "wf_elapsed_s": float|None,     # T_MATCH - T_PUBLISH (None if never matched)
        "wf_consumer_errors": int,      # ERROR/WARN lines for the well-formed event
        "wf_published": bool,           # was the well-formed event published at all
        "mf_health_ok": bool|None,      # health 200 after the malformed event
        "mf_error_logged": bool,        # ERROR line naming the malformed msg id + parse err
        "mf_in_dlq": bool,              # malformed message found in DLQ within bound
        "mf_state_after": str|None,     # resource state after the malformed event
        "mf_published": bool,           # was the malformed event published at all
      }

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose required
    step the agent never emitted (counts as a mismatch vs gold).
    """
    pre = topic["pre_state"]
    expected = topic["expected_state"]
    out: dict[str, str] = {}

    wf_published = bool(obs.get("wf_published"))
    state_after = obs.get("wf_state_after")
    elapsed = obs.get("wf_elapsed_s")

    out["wellformed_state_changed"] = (
        "true" if (state_after is not None and state_after != pre) else "false"
    ) if wf_published else "missing"

    out["wellformed_correct_value"] = (
        "true" if state_after == expected else "false"
    ) if wf_published else "missing"

    out["wellformed_within_5s"] = (
        "true" if (elapsed is not None and elapsed <= POLL_TIMEOUT_SECONDS) else "false"
    ) if wf_published else "missing"

    out["wellformed_no_consumer_errors"] = (
        "true" if int(obs.get("wf_consumer_errors", 0)) == 0 else "false"
    ) if wf_published else "missing"

    mf_published = bool(obs.get("mf_published"))
    health = obs.get("mf_health_ok")
    out["malformed_no_crash"] = (
        "true" if health else "false"
    ) if mf_published else "missing"

    out["malformed_error_logged"] = (
        "true" if obs.get("mf_error_logged") else "false"
    ) if mf_published else "missing"

    out["malformed_in_dlq"] = (
        "true" if obs.get("mf_in_dlq") else "false"
    ) if mf_published else "missing"

    mf_state = obs.get("mf_state_after")
    out["malformed_no_state_change"] = (
        "true" if (mf_state is None or mf_state == pre) else "false"
    ) if mf_published else "missing"

    return out


def correct(scenario: str, observed_token: str) -> bool:
    """Did the event-driven service behave per the idealized contract for this scenario?"""
    return observed_token == ideal_for(scenario)


def event_processing_success(observed: dict) -> bool:
    """A well-formed event 'succeeds' iff it drove the resource to the correct value
    within the 5s SLA with no consumer errors — all well-formed scenarios pass."""
    return all(observed.get(lbl) == "true" for lbl in WELLFORMED_LABELS)


def dlq_delivered(observed: dict) -> bool:
    """The malformed event was delivered to the DLQ within the bound."""
    return observed.get("malformed_in_dlq") == "true"
