"""Canonical scenario structure for the API webhook-delivery testing task.

ONE definition of the webhook test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-webhook-delivery/build_gold.py), and
  - the harness (agents/common/webhook.py) — which starts a local receiver, executes
    whatever plan an agent emitted (register webhook -> create resource -> poll the
    receiver -> verify the delivered payload + HMAC), and scores it on exactly the
    same scenario-key scheme.

Pure: no env, no I/O, no LLM, no sockets. Keeps agent output and the gold set on the
same (subject, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested as-is — its source is NEVER modified):
  - DummyJSON ships NO webhook subsystem: there is no POST /webhooks registration
    endpoint (it 404s) and it never delivers an outbound webhook. Its POST /<x>/add
    endpoints are SIMULATED — they echo back a created object with an id and persist
    nothing, so issuing them does not mutate the running target.
  - The idealized webhook contract (register a receiver -> creating a resource fires a
    `resource.created` event delivered to the receiver within 10s, carrying the exact
    event_type, the created resource_id, an ISO-8601 timestamp, and an HMAC-SHA256
    signature over the raw body keyed by the registered secret; a 500 from the receiver
    is retried) is what each scenario's `ideal` token encodes. The gold records the
    API's REAL token. Where they differ is a genuine QA finding (DummyJSON does not
    implement webhooks), not an agent bug.

A plan for one subject (the agent's output, and the reference) looks like:
  {
    "resource": "products",
    "webhooks_path": "/webhooks",
    "resource_path": "/products/add",
    "event_type": "resource.created",
    "register": {"method": "POST", "path": "/webhooks",
                 "body": {"url": "<receiver_url>", "events": ["resource.created"]},
                 "expect_status": 201, "capture": "webhook_secret"},
    "trigger":  {"method": "POST", "path": "/products/add",
                 "body": {"title": "Forge Test Product"},
                 "expect_status": 201, "capture": "resource_id"},
    "poll":     {"interval_ms": 500, "timeout_seconds": 10, "match_field": "resource_id"},
    "assertions": {"event_type": "resource.created", "resource_id_matches": true,
                   "timestamp_regex": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}",
                   "signature_headers": ["X-Webhook-Signature", "X-Hub-Signature"],
                   "signature_algorithm": "sha256",
                   "signature_format": "sha256=<hexdigest>"},
    "retry":    {"trigger_status": 500, "wait_seconds": 60, "expect_redelivery": true,
                 "expect_identical_payload": true, "expect_valid_signature": true}
  }
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Fixed constants of the documented webhook contract (the idealized world).
# These are what the agent must copy / fill exactly; gold uses the same.
# --------------------------------------------------------------------------- #
EVENT_TYPE = "resource.created"
EVENTS = ["resource.created"]
EXPECT_REGISTER_STATUS = 201
EXPECT_RESOURCE_STATUS = 201
POLL_INTERVAL_MS = 500
DELIVERY_DEADLINE_SECONDS = 10
TIMESTAMP_REGEX = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
SIGNATURE_HEADERS = ["X-Webhook-Signature", "X-Hub-Signature"]
SIGNATURE_ALGORITHM = "sha256"
SIGNATURE_FORMAT = "sha256=<hexdigest>"
RETRY_TRIGGER_STATUS = 500
RETRY_WAIT_SECONDS = 60

# The full, ordered scenario set scored per subject (the metric denominator).
# Two families:
#   plan_*   tokens are computed from the agent's EMITTED PLAN vs the contract — these
#            are framework-attributable (a mis-built plan diverges here).
#   exec_*   tokens are computed from EXECUTING the plan against the live target — these
#            are properties of the API (uniform across agents; the QA finding lives here).
# `ideal` is the token a fully webhook-compliant API + a perfect plan would produce.
SCENARIOS = [
    # --- plan structure (framework-differentiating) ---
    ("plan_register_method_post",    "true"),
    ("plan_register_path_correct",   "true"),
    ("plan_register_events_correct", "true"),
    ("plan_register_url_is_receiver","true"),
    ("plan_register_expect_201",     "true"),
    ("plan_trigger_method_post",     "true"),
    ("plan_trigger_path_correct",    "true"),
    ("plan_trigger_expect_201",      "true"),
    ("plan_poll_interval_500",       "true"),
    ("plan_poll_timeout_10",         "true"),
    ("plan_assert_event_type",       "true"),
    ("plan_assert_resource_id_match","true"),
    ("plan_assert_timestamp_regex",  "true"),
    ("plan_assert_signature_headers","true"),
    ("plan_assert_signature_algo",   "true"),
    ("plan_assert_signature_format", "true"),
    ("plan_retry_trigger_500",       "true"),
    ("plan_retry_wait_present",      "true"),
    ("plan_retry_expect_redelivery", "true"),
    ("plan_retry_expect_identical",  "true"),
    # --- execution (API property; the genuine QA finding) ---
    ("exec_registration_accepted",      "true"),   # POST /webhooks -> 201
    ("exec_resource_created",           "true"),   # POST /<x>/add  -> 2xx with an id
    ("exec_delivered_within_deadline",  "true"),   # receiver got a matching delivery <=10s
    ("exec_delivered_event_type_match", "true"),   # delivered payload event_type == resource.created
    ("exec_delivered_resource_id_match","true"),   # delivered payload resource_id == created id
    ("exec_delivered_timestamp_iso8601","true"),   # delivered timestamp matches ISO-8601 regex
    ("exec_signature_valid",            "true"),   # header == sha256=hmac_sha256(secret, raw_body)
    ("exec_retry_redelivered",          "true"),   # after a 500, the same event is redelivered
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)
PLAN_SCENARIOS = [s for s in SCENARIO_LABELS if s.startswith("plan_")]
EXEC_SCENARIOS = [s for s in SCENARIO_LABELS if s.startswith("exec_")]


def ideal_for(scenario: str) -> str:
    return IDEAL[scenario]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT webhook test plan for one subject, derived
    deterministically from its config (the brief). This is the gold 'answer'."""
    return {
        "resource": cfg["resource"],
        "webhooks_path": cfg["webhooks_path"],
        "resource_path": cfg["resource_path"],
        "event_type": EVENT_TYPE,
        "register": {
            "method": "POST",
            "path": cfg["webhooks_path"],
            "body": {"url": cfg["receiver_url"], "events": list(EVENTS)},
            "expect_status": EXPECT_REGISTER_STATUS,
            "capture": "webhook_secret",
        },
        "trigger": {
            "method": "POST",
            "path": cfg["resource_path"],
            "body": dict(cfg["resource_body"]),
            "expect_status": EXPECT_RESOURCE_STATUS,
            "capture": "resource_id",
        },
        "poll": {
            "interval_ms": POLL_INTERVAL_MS,
            "timeout_seconds": DELIVERY_DEADLINE_SECONDS,
            "match_field": "resource_id",
        },
        "assertions": {
            "event_type": EVENT_TYPE,
            "resource_id_matches": True,
            "timestamp_regex": TIMESTAMP_REGEX,
            "signature_headers": list(SIGNATURE_HEADERS),
            "signature_algorithm": SIGNATURE_ALGORITHM,
            "signature_format": SIGNATURE_FORMAT,
        },
        "retry": {
            "trigger_status": RETRY_TRIGGER_STATUS,
            "wait_seconds": RETRY_WAIT_SECONDS,
            "expect_redelivery": True,
            "expect_identical_payload": True,
            "expect_valid_signature": True,
        },
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _b(value: bool) -> str:
    return "true" if value else "false"


def _is_pos_int(v) -> bool:
    try:
        return int(v) > 0
    except (TypeError, ValueError):
        return False


def evaluate(cfg: dict, plan: dict, exec_obs: dict) -> dict:
    """Compute the observed token for every scenario.

    `cfg`      the brief (carries the expected/contract values for this subject).
    `plan`     the agent's emitted plan (may be partial/malformed; missing keys
               score 'missing', which is a mismatch vs gold).
    `exec_obs` the harness's raw measurement from executing the plan, with keys:
               register_status:int|None, resource_status:int|None, resource_id:str|None,
               delivered:bool, delivery_seconds:float|None, delivered_event_type:str|None,
               delivered_resource_id:str|None, delivered_timestamp_ok:bool,
               signature_valid:bool, retry_attempted:bool, retry_redelivered:bool.
    """
    import re

    if not isinstance(plan, dict):
        plan = {}
    out: dict[str, str] = {}

    # ----- plan-structure scenarios -----
    out["plan_register_method_post"]    = _b(_get(plan, "register", "method") == "POST")
    out["plan_register_path_correct"]   = _b(_get(plan, "register", "path") == cfg["webhooks_path"])
    out["plan_register_events_correct"] = _b(_get(plan, "register", "body", "events") == EVENTS)
    out["plan_register_url_is_receiver"]= _b(_get(plan, "register", "body", "url") == cfg["receiver_url"])
    out["plan_register_expect_201"]     = _b(_get(plan, "register", "expect_status") == EXPECT_REGISTER_STATUS)
    out["plan_trigger_method_post"]     = _b(_get(plan, "trigger", "method") == "POST")
    out["plan_trigger_path_correct"]    = _b(_get(plan, "trigger", "path") == cfg["resource_path"])
    out["plan_trigger_expect_201"]      = _b(_get(plan, "trigger", "expect_status") == EXPECT_RESOURCE_STATUS)
    out["plan_poll_interval_500"]       = _b(_get(plan, "poll", "interval_ms") == POLL_INTERVAL_MS)
    out["plan_poll_timeout_10"]         = _b(_get(plan, "poll", "timeout_seconds") == DELIVERY_DEADLINE_SECONDS)
    out["plan_assert_event_type"]       = _b(_get(plan, "assertions", "event_type") == EVENT_TYPE)
    out["plan_assert_resource_id_match"]= _b(_get(plan, "assertions", "resource_id_matches") is True)
    out["plan_assert_timestamp_regex"]  = _b(_get(plan, "assertions", "timestamp_regex") == TIMESTAMP_REGEX)
    out["plan_assert_signature_headers"]= _b(_get(plan, "assertions", "signature_headers") == SIGNATURE_HEADERS)
    out["plan_assert_signature_algo"]   = _b(_get(plan, "assertions", "signature_algorithm") == SIGNATURE_ALGORITHM)
    out["plan_assert_signature_format"] = _b(_get(plan, "assertions", "signature_format") == SIGNATURE_FORMAT)
    out["plan_retry_trigger_500"]       = _b(_get(plan, "retry", "trigger_status") == RETRY_TRIGGER_STATUS)
    out["plan_retry_wait_present"]      = _b(_is_pos_int(_get(plan, "retry", "wait_seconds")))
    out["plan_retry_expect_redelivery"] = _b(_get(plan, "retry", "expect_redelivery") is True)
    out["plan_retry_expect_identical"]  = _b(_get(plan, "retry", "expect_identical_payload") is True)

    # any plan key the agent omitted entirely -> "missing" (distinct from a wrong value)
    for label in PLAN_SCENARIOS:
        if out[label] == "false" and _plan_key_absent(plan, label):
            out[label] = "missing"

    # ----- execution scenarios (API property) -----
    reg = exec_obs.get("register_status")
    res = exec_obs.get("resource_status")
    out["exec_registration_accepted"]       = _status_token(reg, EXPECT_REGISTER_STATUS)
    out["exec_resource_created"]            = _b(isinstance(res, int) and 200 <= res < 300
                                                  and exec_obs.get("resource_id") not in (None, ""))
    out["exec_delivered_within_deadline"]    = _b(bool(exec_obs.get("delivered")))
    out["exec_delivered_event_type_match"]   = _delivered_token(exec_obs,
                                                  exec_obs.get("delivered_event_type") == EVENT_TYPE)
    out["exec_delivered_resource_id_match"]  = _delivered_token(exec_obs,
                                                  str(exec_obs.get("delivered_resource_id")) ==
                                                  str(exec_obs.get("resource_id")) and
                                                  exec_obs.get("resource_id") not in (None, ""))
    out["exec_delivered_timestamp_iso8601"]  = _delivered_token(exec_obs,
                                                  bool(exec_obs.get("delivered_timestamp_ok")))
    out["exec_signature_valid"]              = _delivered_token(exec_obs,
                                                  bool(exec_obs.get("signature_valid")))
    out["exec_retry_redelivered"]            = ("true" if exec_obs.get("retry_redelivered")
                                                 else ("false" if exec_obs.get("retry_attempted")
                                                       else "missing"))
    return out


# keys whose total absence in the plan should read as "missing" rather than "false"
_PLAN_KEY_GROUP = {
    "plan_register_method_post": ("register",), "plan_register_path_correct": ("register",),
    "plan_register_events_correct": ("register",), "plan_register_url_is_receiver": ("register",),
    "plan_register_expect_201": ("register",),
    "plan_trigger_method_post": ("trigger",), "plan_trigger_path_correct": ("trigger",),
    "plan_trigger_expect_201": ("trigger",),
    "plan_poll_interval_500": ("poll",), "plan_poll_timeout_10": ("poll",),
    "plan_assert_event_type": ("assertions",), "plan_assert_resource_id_match": ("assertions",),
    "plan_assert_timestamp_regex": ("assertions",), "plan_assert_signature_headers": ("assertions",),
    "plan_assert_signature_algo": ("assertions",), "plan_assert_signature_format": ("assertions",),
    "plan_retry_trigger_500": ("retry",), "plan_retry_wait_present": ("retry",),
    "plan_retry_expect_redelivery": ("retry",), "plan_retry_expect_identical": ("retry",),
}


def _plan_key_absent(plan: dict, label: str) -> bool:
    group = _PLAN_KEY_GROUP.get(label)
    return bool(group) and not isinstance(_get(plan, *group), dict)


def _status_token(code, expected: int) -> str:
    if code is None:
        return "missing"
    return "true" if code == expected else (f"http_{code}" if isinstance(code, int) else "false")


def _delivered_token(exec_obs: dict, condition: bool) -> str:
    """For payload-level checks: if nothing was delivered there is nothing to check
    -> 'missing'; otherwise the boolean check result."""
    if not exec_obs.get("delivered"):
        return "missing"
    return "true" if condition else "false"


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API + plan behave per the idealized webhook contract for this scenario?"""
    return observed_token == ideal_for(scenario)
