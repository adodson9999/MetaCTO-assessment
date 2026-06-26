"""Canonical scenario structure for the API audit-log-generation verification task.

ONE definition of the audit-verification test plan + the per-scenario evaluation,
shared by:
  - the deterministic gold reference (data/verify-audit-log-generation/build_gold.py), and
  - the harness (agents/common/auditlog.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested AS-IS — verified in src/ + a live probe):
  - There is NO audit-log system. The only logging is request-logger.js, which emits
    one winston "HTTP Request" JSON line per request to stdout when LOG_ENABLED=true:
    {timestamp, level, message, method, status, meta:{total_time_ms, response_time_ms,
     ip, url, referrer, user_agent}}. It carries `timestamp` + `ip` (::1) but NO
    `user_id`, NO `action_type`, NO `resource_id`, is not user-scoped, off by default.
  - POST /<col>/add -> 201 with a phantom id (length+1) that does not persist, so the
    literal follow-on PUT/DELETE on that id -> 404 (a genuine finding, not an agent bug).
  - There is no queryable audit store, so "exactly 3 audit entries, each with all
    required fields non-null and timestamp within 5s" has no analog: capturing the
    request-log yields lines with timestamp + ip_address present but user_id /
    action_type / resource_id NULL => 0 correctly-populated audit entries =>
    Audit Log Coverage Rate = 0%.

  The idealized audit contract (3 valid entries, each with all required fields
  non-null and timestamp within 5s, scoped to the test user) is what each scenario's
  `ideal` token encodes; the gold records the API's REAL token. Where they differ is
  the QA finding about DummyJSON, not an agent bug.

A plan for one collection (the agent's output, and the reference) looks like:
  {
    "collection": "/products", "id_field": "id", "test_user_id": "user-test-001",
    "operations": [
      {"label":"create","action_type":"CREATE","method":"POST","path":"/products/add",
       "body":{"title":"audit-probe"},"expect_status":[201]},
      {"label":"update","action_type":"UPDATE","method":"PUT","path":"/products/{resource_id}",
       "body":{"title":"audit-probe-updated"},"expect_status":[200]},
      {"label":"delete","action_type":"DELETE","method":"DELETE","path":"/products/{resource_id}",
       "body":null,"expect_status":[200,204]}
    ],
    "audit_query": {
      "filter_user_id":"user-test-001","window_before_seconds":5,
      "window_after_seconds":10,"expected_entry_count":3,
      "required_fields":["user_id","action_type","resource_id","timestamp","ip_address"],
      "timestamp_tolerance_seconds":5,"action_types":["CREATE","UPDATE","DELETE"]
    }
  }
The literal token "{resource_id}" in the update/delete path is replaced by the
executor with the id the create operation returned.
"""
from __future__ import annotations

# Fixed literal plan values. Pinned so the debate-gated plan is byte-stable and
# reproducible across all four agents and the gold reference.
CREATE_BODY = {"title": "audit-probe"}
UPDATE_BODY = {"title": "audit-probe-updated"}
RESOURCE_PLACEHOLDER = "{resource_id}"

REQUIRED_FIELDS = ["user_id", "action_type", "resource_id", "timestamp", "ip_address"]
ACTION_TYPES = ["CREATE", "UPDATE", "DELETE"]
WINDOW_BEFORE_S = 5
WINDOW_AFTER_S = 10
EXPECTED_ENTRY_COUNT = 3
TIMESTAMP_TOLERANCE_S = 5

# Expected status per operation (idealized audit contract).
EXPECT_STATUS = {"create": [201], "update": [200], "delete": [200, 204]}

# The full, ordered scenario set scored per collection (the fidelity denominator).
# `ideal` is the token a correct audit-logging API would produce; gold records the
# REAL token DummyJSON produces. 9 scenarios x N collections = fidelity denominator.
SCENARIOS = [
    ("create_status_ok",            "true"),  # CREATE returned an expected status (201)
    ("update_status_ok",            "true"),  # UPDATE returned 200
    ("delete_status_ok",            "true"),  # DELETE returned 200 or 204
    ("create_audit_entry_complete", "true"),  # valid CREATE audit entry (all fields, ids, ts<=5s)
    ("update_audit_entry_complete", "true"),  # valid UPDATE audit entry
    ("delete_audit_entry_complete", "true"),  # valid DELETE audit entry
    ("audit_entry_count_exactly_3", "true"),  # exactly 3 valid audit entries in the window
    ("audit_all_fields_nonnull",    "true"),  # the 3 entries carry zero null required fields
    ("audit_user_scoped",           "true"),  # every valid entry user_id == test_user_id
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# Operation labels whose audit coverage counts toward the headline Coverage Rate.
COVERAGE_OPS = ["create", "update", "delete"]
OP_COMPLETE_SCENARIO = {
    "create": "create_audit_entry_complete",
    "update": "update_audit_entry_complete",
    "delete": "delete_audit_entry_complete",
}


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one collection, derived deterministically from
    its config (collection, id_field, test_user_id). Identical structure to what a
    faithful agent must emit."""
    col = cfg["collection"]
    uid = cfg["test_user_id"]
    return {
        "collection": col,
        "id_field": cfg.get("id_field", "id"),
        "test_user_id": uid,
        "operations": [
            {"label": "create", "action_type": "CREATE", "method": "POST",
             "path": f"{col}/add", "body": dict(CREATE_BODY), "expect_status": [201]},
            {"label": "update", "action_type": "UPDATE", "method": "PUT",
             "path": f"{col}/{RESOURCE_PLACEHOLDER}", "body": dict(UPDATE_BODY),
             "expect_status": [200]},
            {"label": "delete", "action_type": "DELETE", "method": "DELETE",
             "path": f"{col}/{RESOURCE_PLACEHOLDER}", "body": None,
             "expect_status": [200, 204]},
        ],
        "audit_query": {
            "filter_user_id": uid,
            "window_before_seconds": WINDOW_BEFORE_S,
            "window_after_seconds": WINDOW_AFTER_S,
            "expected_entry_count": EXPECTED_ENTRY_COUNT,
            "required_fields": list(REQUIRED_FIELDS),
            "timestamp_tolerance_seconds": TIMESTAMP_TOLERANCE_S,
            "action_types": list(ACTION_TYPES),
        },
    }


def evaluate(op_obs: dict, audit_obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    op_obs[label] = {"status": int|None, "expect_status": [..]}   (missing => not exercised)
    audit_obs = {
        "by_op": {label: {"present": bool, "fields_complete": bool,
                          "ts_within": bool, "user_match": bool}},
        "count_valid": int,           # number of VALID audit entries (all required fields non-null)
        "all_fields_nonnull": bool,   # exactly EXPECTED_ENTRY_COUNT valid entries, each zero-null
        "user_scoped": bool,          # >=1 valid entry AND all valid entries user_id == filter
        "queried": bool,              # audit_query was present in the plan
    }
    Returns {scenario: observed_token}; "missing" marks a scenario the agent never set up.
    """
    obs: dict[str, str] = {}

    def status_tok(label):
        rec = op_obs.get(label)
        if not rec or rec.get("status") is None:
            return "missing"
        exp = rec.get("expect_status") or EXPECT_STATUS.get(label, [])
        if not exp:
            return "missing"
        return "true" if rec["status"] in exp else "false"

    obs["create_status_ok"] = status_tok("create")
    obs["update_status_ok"] = status_tok("update")
    obs["delete_status_ok"] = status_tok("delete")

    by_op = (audit_obs or {}).get("by_op", {})
    queried = bool((audit_obs or {}).get("queried"))

    def complete_tok(label):
        # If the agent never planned this op at all, it's 'missing'; if it planned the
        # op but no audit_query, the audit side is 'missing' too.
        if label not in op_obs:
            return "missing"
        if not queried:
            return "missing"
        rec = by_op.get(label, {})
        ok = (rec.get("present") and rec.get("fields_complete")
              and rec.get("ts_within") and rec.get("user_match"))
        return "true" if ok else "false"

    obs["create_audit_entry_complete"] = complete_tok("create")
    obs["update_audit_entry_complete"] = complete_tok("update")
    obs["delete_audit_entry_complete"] = complete_tok("delete")

    if not queried:
        obs["audit_entry_count_exactly_3"] = "missing"
        obs["audit_all_fields_nonnull"] = "missing"
        obs["audit_user_scoped"] = "missing"
    else:
        obs["audit_entry_count_exactly_3"] = (
            "true" if (audit_obs or {}).get("count_valid") == EXPECTED_ENTRY_COUNT else "false")
        obs["audit_all_fields_nonnull"] = (
            "true" if (audit_obs or {}).get("all_fields_nonnull") else "false")
        obs["audit_user_scoped"] = (
            "true" if (audit_obs or {}).get("user_scoped") else "false")

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized audit contract for this scenario?"""
    return observed_token == IDEAL[scenario]


def coverage(observed_by_collection: dict) -> dict:
    """The headline Audit Log Coverage Rate over auditable operations (create, update,
    delete) across all collections. An operation is COVERED iff its
    `<op>_audit_entry_complete` token observed "true".

    observed_by_collection: {collection: {scenario: observed_token}}
    Returns {covered, total, rate_pct, cases:[...]}.
    """
    cases = []
    covered = total = 0
    for col, obs in observed_by_collection.items():
        for op in COVERAGE_OPS:
            tok = obs.get(OP_COMPLETE_SCENARIO[op], "missing")
            ok = (tok == "true")
            cases.append({"collection": col, "operation": op,
                          "complete_token": tok, "covered": ok})
            total += 1
            covered += 1 if ok else 0
    rate = round(100.0 * covered / total, 2) if total else 0.0
    return {"covered": covered, "total": total, "rate_pct": rate, "cases": cases}
