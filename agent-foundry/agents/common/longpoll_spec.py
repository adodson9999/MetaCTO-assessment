"""Canonical scenario structure for the API long-polling testing task.

ONE definition of the long-poll test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-long-polling-support/build_gold.py), and
  - the harness (agents/common/longpoll.py) — which executes whatever plan an agent
    emitted against the local fixture and scores it on the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no sockets. Keeps agent output and the gold set on the
same (channel, scenario) key scheme so the judge compares field-for-field.

Target reality (the local longpoll-target fixture, tested as-is):
  - Documented contract: an event-less poll stays open ~poll_timeout_s and closes 204
    with an empty body; an event published within the window closes the poll within 2 s
    of the event with 200 and an event_type that matches plus a non-empty secondary field.
  - One channel (`inventory`) is non-compliant (200 + non-empty body on no-event; a
    ~3 s post-publish stall + wrong event_type on an event) — a real QA finding the suite
    must surface, exactly like DummyJSON's lenient pagination.

A plan for one channel (the agent's output, and the reference) looks like:
  {
    "channel": "orders", "poll_path": "/poll/orders", "trigger_path": "/publish/orders",
    "poll_timeout_s": 5, "expected_event_type": "order.created", "client_max_time_s": 10,
    "cases": [{"label": "no_event", "kind": "no_event"}, {"label": "event", "kind": "event"}]
  }
"""
from __future__ import annotations

# The fixed +/- tolerance (seconds) around poll_timeout_s for the no-event close, and the
# maximum allowed delay (seconds) between the event and the long-poll response. From the task.
WINDOW_TOLERANCE_S = 2.0
EVENT_RESPONSE_MAX_S = 2.0
# client_max_time_s = poll_timeout_s + this guard (the curl --max-time client cap).
CLIENT_GUARD_S = 5

# No-event-case scenarios (poll opened, no event published).
NO_EVENT_SCENARIOS = [
    ("ne_status",        "204"),   # closes with exactly 204
    ("ne_not_early",     "true"),  # did NOT respond before poll_timeout_s - 2
    ("ne_within_window", "true"),  # responded by poll_timeout_s + 2
    ("ne_body_empty",    "true"),  # Content-Length == 0
]
# Event-case scenarios (event published ~1.5 s into the poll).
EVENT_SCENARIOS = [
    ("ev_status",            "200"),   # closes with exactly 200
    ("ev_within_2s",         "true"),  # responded within 2 s of the event
    ("ev_valid_json",        "true"),  # body parses as a JSON object
    ("ev_event_type_match",  "true"),  # body.event_type == expected_event_type (exact)
    ("ev_secondary_nonempty","true"),  # >= 1 other body field non-null and non-empty
]
# Per-channel arithmetic scenario (the agent's one computation).
CHANNEL_SCENARIOS = [
    ("client_max_time_correct", "true"),  # client_max_time_s == poll_timeout_s + 5
]

NO_EVENT_SCENARIO_LABELS = [s for s, _ in NO_EVENT_SCENARIOS]
EVENT_SCENARIO_LABELS = [s for s, _ in EVENT_SCENARIOS]
CHANNEL_SCENARIO_LABELS = [s for s, _ in CHANNEL_SCENARIOS]
IDEAL = dict(NO_EVENT_SCENARIOS + EVENT_SCENARIOS + CHANNEL_SCENARIOS)


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one channel, derived deterministically: echo the
    documented contract, set client_max_time_s = poll_timeout_s + 5, and list the two
    cases (no_event first, event second)."""
    return {
        "channel": cfg["channel"],
        "poll_path": cfg["poll_path"],
        "trigger_path": cfg["trigger_path"],
        "poll_timeout_s": cfg["poll_timeout_s"],
        "expected_event_type": cfg["expected_event_type"],
        "client_max_time_s": cfg["poll_timeout_s"] + CLIENT_GUARD_S,
        "cases": [
            {"label": "no_event", "kind": "no_event"},
            {"label": "event", "kind": "event"},
        ],
    }


def _status_class(code) -> str:
    if code is None:
        return "none"
    if code in (200, 204, 408, 500):
        return str(code)
    return f"other_{code}"


def secondary_nonempty(body: dict | None, event_type_key: str = "event_type") -> bool:
    """True iff the body has >= 1 field besides event_type whose value is non-null and
    non-empty (non-empty string / non-empty collection / any number or True)."""
    if not isinstance(body, dict):
        return False
    for k, v in body.items():
        if k == event_type_key:
            continue
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        return True
    return False


def evaluate_no_event(obs: dict | None, poll_timeout_s: int) -> dict:
    """Observed token per no-event scenario.

    obs: {"status":int|None, "content_length":int|None, "elapsed_s":float|None} or None.
    """
    if obs is None:
        return {s: "missing" for s in NO_EVENT_SCENARIO_LABELS}
    out: dict[str, str] = {}
    out["ne_status"] = _status_class(obs.get("status"))
    el = obs.get("elapsed_s")
    if el is None:
        out["ne_not_early"] = "missing"
        out["ne_within_window"] = "missing"
    else:
        out["ne_not_early"] = "true" if el >= poll_timeout_s - WINDOW_TOLERANCE_S else "false"
        out["ne_within_window"] = "true" if el <= poll_timeout_s + WINDOW_TOLERANCE_S else "false"
    cl = obs.get("content_length")
    out["ne_body_empty"] = "missing" if cl is None else ("true" if cl == 0 else "false")
    return out


def evaluate_event(obs: dict | None, expected_event_type: str) -> dict:
    """Observed token per event scenario.

    obs: {"status":int|None, "response_after_event_s":float|None, "body":dict|None}.
    """
    if obs is None:
        return {s: "missing" for s in EVENT_SCENARIO_LABELS}
    out: dict[str, str] = {}
    out["ev_status"] = _status_class(obs.get("status"))
    ra = obs.get("response_after_event_s")
    out["ev_within_2s"] = "missing" if ra is None else (
        "true" if ra <= EVENT_RESPONSE_MAX_S else "false")
    body = obs.get("body")
    is_obj = isinstance(body, dict)
    out["ev_valid_json"] = "true" if is_obj else "false"
    if not is_obj:
        out["ev_event_type_match"] = "false"
        out["ev_secondary_nonempty"] = "false"
    else:
        out["ev_event_type_match"] = "true" if body.get("event_type") == expected_event_type else "false"
        out["ev_secondary_nonempty"] = "true" if secondary_nonempty(body) else "false"
    return out


def evaluate_channel(plan: dict | None, cfg: dict) -> dict:
    """Observed token for the per-channel arithmetic scenario."""
    expected = cfg["poll_timeout_s"] + CLIENT_GUARD_S
    if not isinstance(plan, dict) or "client_max_time_s" not in plan:
        return {"client_max_time_correct": "missing"}
    try:
        ok = int(plan["client_max_time_s"]) == expected
    except (TypeError, ValueError):
        return {"client_max_time_correct": "false"}
    return {"client_max_time_correct": "true" if ok else "false"}


def correct(scenario: str, observed_token: str) -> bool:
    """Did the target behave per the idealized long-poll contract for this scenario?"""
    return observed_token == IDEAL[scenario]


def no_event_case_pass(ne_obs: dict) -> bool:
    """Headline Long-Poll Response Accuracy, no-event leg: 204 returned within the
    [poll_timeout_s - 2, poll_timeout_s + 2] window."""
    return (ne_obs.get("ne_status") == "204"
            and ne_obs.get("ne_not_early") == "true"
            and ne_obs.get("ne_within_window") == "true")


def event_case_pass(ev_obs: dict) -> bool:
    """Headline Long-Poll Response Accuracy, event leg: 200 returned within 2 s of the
    event."""
    return ev_obs.get("ev_status") == "200" and ev_obs.get("ev_within_2s") == "true"
