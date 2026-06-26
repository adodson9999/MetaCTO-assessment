"""Canonical scenario structure for the API soft-delete-behavior task.

ONE definition of the soft-delete test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-soft-delete-behavior/build_gold.py), and
  - the harness (agents/common/softdelete.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold set on the same
scenario-key scheme so the judge can compare them field-for-field.

Target reality (Phase-2 owner decision: DummyJSON is left untouched and is NOT used
here): the soft-delete contract (DELETE keeps the DB row with a non-null deleted_at +
is_deleted=true, GET-by-id returns 404, the row disappears from the collection but
reappears under ?include_deleted=true) is exercised against a separate, purpose-built,
local, air-gapped SQLite-backed endpoint (tools/softdelete_target/app.py), because
DummyJSON never persists and exposes no queryable DB.

`ideal` is the token a correct soft-delete system produces. The gold records the REAL
observed token. Where they differ is a genuine QA finding about the target, not an
agent bug. (Empirically the local target is contract-correct, so gold == ideal here —
itself a valid QA result: every soft delete leaves a queryable tombstone within 10s.)

The harness runs the plan over `case_count` independent resource lifecycles (POST ->
appears -> record T_DELETE -> DELETE -> GET-by-id 404 -> absent-from-collection ->
direct DB query -> include_deleted) and aggregates the per-case outcomes into the
tokens below.

A plan for one run (the agent's output, and the reference) looks like:
  {
    "case_count": 5,
    "create":  {"method":"POST","endpoint":"/resources","fields":{"name":"...","sku":"...","color":"..."}},
    "delete":  {"method":"DELETE","path_template":"/resources/{RESOURCE_ID}","expected_status":[200,204]},
    "get_deleted": {"method":"GET","path_template":"/resources/{RESOURCE_ID}","expected_status":404,"assert_no_field_values":true},
    "collection":  {"method":"GET","endpoint":"/resources","expected_status":200,"assert_absent":true},
    "db_query": {"table":"resources","id_column":"id","deleted_at_column":"deleted_at",
                 "is_deleted_column":"is_deleted","assert_row_exists":true,
                 "assert_deleted_at_not_null":true,"assert_is_deleted_true":true,
                 "deleted_at_within_seconds":10},
    "include_deleted": {"method":"GET","endpoint":"/resources","query":"include_deleted=true",
                        "expected_status":200,"assert_present_with_deleted_at":true}
  }
"""
from __future__ import annotations

# Default number of independent soft-delete lifecycles exercised per run (the metric's
# "total soft delete test cases" denominator). Fixed by the spec config.
CASE_COUNT = 5

# Seconds within which deleted_at must be set relative to T_DELETE.
DELETED_AT_TOLERANCE_S = 10

# The full, ordered scenario set scored per run (the fidelity metric denominator).
# Each scenario's `ideal` is what a correct soft-delete target produces over all cases.
SCENARIOS = [
    ("all_create_201",             "true"),  # every POST returned 201
    ("create_success_count",       "5"),     # count of 201 creates (== case_count)
    ("all_appear_before_delete",   "true"),  # each resource is in the collection pre-delete
    ("all_delete_2xx",             "true"),  # every DELETE returned 200 or 204
    ("all_get_by_id_404",          "true"),  # GET-by-id of each deleted resource == 404
    ("all_get_by_id_no_field_leak","true"),  # the 404 body carries no posted field values
    ("all_absent_from_collection", "true"),  # deleted id absent from GET /resources
    ("all_db_row_exists",          "true"),  # exactly one DB row survives per deleted id
    ("all_db_deleted_at_not_null", "true"),  # deleted_at IS NOT NULL for each
    ("all_db_deleted_at_within_10s","true"), # |deleted_at - T_DELETE| <= 10s for each
    ("all_db_is_deleted_true",     "true"),  # is_deleted = true for each
    ("all_include_deleted_shows",  "true"),  # ?include_deleted=true shows it w/ non-null deleted_at
    ("soft_delete_correct_count",  "5"),     # cases meeting the FULL combined condition (== case_count)
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# Scenario tokens whose ideal is the literal case_count (recomputed when case_count
# differs from the default, e.g. on the held-out variant).
_COUNT_SCENARIOS = ("create_success_count", "soft_delete_correct_count")


def ideal_for(case_count: int) -> dict:
    """IDEAL map specialized to a given case_count (the two count tokens scale)."""
    d = dict(IDEAL)
    for k in _COUNT_SCENARIOS:
        d[k] = str(case_count)
    return d


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan, derived deterministically from the spec config.
    Used by the gold builder; an agent that constructs the same plan reproduces the
    gold observations."""
    return {
        "case_count": cfg.get("case_count", CASE_COUNT),
        "create": {
            "method": "POST",
            "endpoint": cfg["resource_endpoint"],
            "fields": dict(cfg.get("create_fields", {})),
        },
        "delete": {
            "method": "DELETE",
            "path_template": cfg["resource_endpoint"].rstrip("/") + "/{RESOURCE_ID}",
            "expected_status": list(cfg.get("delete_expected_status", [200, 204])),
        },
        "get_deleted": {
            "method": "GET",
            "path_template": cfg["resource_endpoint"].rstrip("/") + "/{RESOURCE_ID}",
            "expected_status": cfg.get("get_deleted_expected_status", 404),
            "assert_no_field_values": True,
        },
        "collection": {
            "method": "GET",
            "endpoint": cfg["resource_endpoint"],
            "expected_status": cfg.get("collection_expected_status", 200),
            "assert_absent": True,
        },
        "db_query": {
            "table": cfg["db_table"],
            "id_column": cfg.get("db_id_column", "id"),
            "deleted_at_column": cfg.get("db_deleted_at_column", "deleted_at"),
            "is_deleted_column": cfg.get("db_is_deleted_column", "is_deleted"),
            "assert_row_exists": True,
            "assert_deleted_at_not_null": True,
            "assert_is_deleted_true": True,
            "deleted_at_within_seconds": cfg.get("deleted_at_tolerance_s",
                                                 DELETED_AT_TOLERANCE_S),
        },
        "include_deleted": {
            "method": "GET",
            "endpoint": cfg["resource_endpoint"],
            "query": cfg.get("include_deleted_param", "include_deleted=true"),
            "expected_status": cfg.get("include_deleted_expected_status", 200),
            "assert_present_with_deleted_at": True,
        },
    }


def evaluate(case_results: list, case_count: int) -> dict:
    """Compute the observed token for every scenario from the per-case outcomes.

    case_results: list of per-case dicts produced by the harness. Each may contain:
        create_status:int, appears_before:bool, delete_status:int,
        get_by_id_status:int, get_by_id_no_leak:bool, absent_from_collection:bool,
        db_row_count:int, db_deleted_at:str|None, db_within_10s:bool,
        db_is_deleted:bool, include_deleted_status:int, include_deleted_present:bool
    A token of "missing" marks a step the agent's plan never produced (counts as a
    mismatch vs gold).
    """
    obs: dict[str, str] = {}
    cr = case_results if isinstance(case_results, list) else []

    def _all(key, pred) -> str:
        present = [c for c in cr if key in c]
        if not present or len(present) != case_count:
            return "missing"
        return "true" if all(pred(c) for c in present) else "false"

    # CREATE
    obs["all_create_201"] = _all("create_status", lambda c: c.get("create_status") == 201)
    creates = [c for c in cr if "create_status" in c]
    obs["create_success_count"] = (str(sum(1 for c in creates if c.get("create_status") == 201))
                                    if creates else "missing")

    obs["all_appear_before_delete"] = _all("appears_before", lambda c: c.get("appears_before") is True)

    # DELETE
    obs["all_delete_2xx"] = _all("delete_status", lambda c: c.get("delete_status") in (200, 204))

    # GET-by-id of the deleted resource
    obs["all_get_by_id_404"] = _all("get_by_id_status", lambda c: c.get("get_by_id_status") == 404)
    obs["all_get_by_id_no_field_leak"] = _all("get_by_id_no_leak", lambda c: c.get("get_by_id_no_leak") is True)

    # Collection exclusion
    obs["all_absent_from_collection"] = _all("absent_from_collection", lambda c: c.get("absent_from_collection") is True)

    # Direct DB query
    obs["all_db_row_exists"] = _all("db_row_count", lambda c: c.get("db_row_count") == 1)
    obs["all_db_deleted_at_not_null"] = _all("db_deleted_at", lambda c: c.get("db_deleted_at") not in (None, "", "NULL"))
    obs["all_db_deleted_at_within_10s"] = _all("db_within_10s", lambda c: c.get("db_within_10s") is True)
    obs["all_db_is_deleted_true"] = _all("db_is_deleted", lambda c: c.get("db_is_deleted") is True)

    # Include-deleted
    obs["all_include_deleted_shows"] = _all("include_deleted_present", lambda c: c.get("include_deleted_present") is True)

    # FULL combined-condition pass count (the metric's headline definition):
    # GET-by-id 404 AND absent from collection AND DB row exists with non-null
    # deleted_at within 10s.
    scored = [c for c in cr if "get_by_id_status" in c]
    if not scored:
        obs["soft_delete_correct_count"] = "missing"
    else:
        obs["soft_delete_correct_count"] = str(sum(1 for c in scored if _case_fully_correct(c)))

    return obs


def _case_fully_correct(c: dict) -> bool:
    """The metric's PASS definition for a single soft-delete test case."""
    return (
        c.get("get_by_id_status") == 404
        and c.get("absent_from_collection") is True
        and c.get("db_row_count") == 1
        and c.get("db_deleted_at") not in (None, "", "NULL")
        and c.get("db_within_10s") is True
    )


def correct(scenario: str, observed_token: str, ideal: dict) -> bool:
    """Did the target behave per the idealized soft-delete contract for this scenario?"""
    return observed_token == ideal[scenario]


def success_rate(case_results: list, case_count: int) -> dict:
    """Headline Soft Delete Correctness Rate over the test cases.

    rate = (cases passing the FULL combined condition / total cases) * 100.
    Returns {rate_pct, correct_cases, total_cases}.
    """
    cr = [c for c in (case_results or []) if "get_by_id_status" in c]
    correct_cases = sum(1 for c in cr if _case_fully_correct(c))
    total = case_count if case_count else len(cr)
    rate = round(100.0 * correct_cases / total, 2) if total else 0.0
    return {"rate_pct": rate, "correct_cases": correct_cases, "total_cases": total}
