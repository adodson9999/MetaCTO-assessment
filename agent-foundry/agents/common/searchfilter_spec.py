"""Canonical scenario structure for the API search-and-filter-query testing task.

ONE definition of the filter test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/validate-search-and-filter-queries/build_gold.py), and
  - the harness (agents/common/searchfilter.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (the LOCAL seeded /resources SUT — see tools/filter-resource-server;
DummyJSON is never used or modified). The documented strict filter contract is:
  - status   : enum filter {active, inactive}; out-of-enum -> 400 referencing "status".
  - category : free-form exact-match string filter; an unmatched value -> 200 + empty.
  - AND across recognized filters; unknown params -> 400 referencing the param name.
  - body: {"<list_field>": [...records...], "total": N}.

A plan for one collection (the agent's output, and the reference) looks like:
  {
    "collection": "/resources", "list_field": "resources", "id_field": "id",
    "cases": [
      {"label": "single_filter",  "type": "single", "params": {"status": "active"}},
      {"label": "multi_filter",   "type": "multi",  "params": {"status": "active", "category": "A"}},
      {"label": "invalid_value",  "type": "invalid","params": {"status": "unknown_value"}},
      {"label": "unknown_param",  "type": "unknown","params": {"bogus_filter": "x"}},
      {"label": "empty_result",   "type": "empty",  "params": {"status": "active", "category": "C"}}
    ]
  }

The agent emits these 5 cases; the harness derives the 14 scored scenarios below from
them. The expected count for each count scenario is the KNOWN count of matching records
in the seeded database (passed per-collection via `expected_counts`).
"""
from __future__ import annotations

# The exact five executable cases the agent must emit, by label.
CASE_LABELS = [
    "single_filter",
    "multi_filter",
    "invalid_value",
    "unknown_param",
    "empty_result",
]

# The full, ordered scenario set scored per collection (the metric denominator).
# Each tuple is (scenario_label, universal_ideal_token). For the three count
# scenarios the ideal is the seed-derived expected count, so it is marked "<count>"
# and resolved per-collection from `expected_counts` (see ideal_for / correct).
SCENARIOS = [
    ("single_filter_status",     "200"),
    ("single_filter_count",      "<count>"),   # == known active count (15 for /resources)
    ("single_filter_match",      "true"),      # every record's status == "active"
    ("single_filter_exclusion",  "true"),      # no inactive id present
    ("multi_filter_status",      "200"),
    ("multi_filter_count",       "<count>"),   # == known active&A count (8 for /resources)
    ("multi_filter_match",       "true"),      # every record status==active AND category==A
    ("multi_filter_exclusion",   "true"),      # no category-B id present
    ("invalid_value_status",     "400"),
    ("invalid_value_message",    "true"),      # message references the "status" parameter
    ("unknown_param_status",     "400"),       # documented STRICT policy: unknown param -> 400
    ("unknown_param_message",    "true"),      # message references the unknown param name
    ("empty_result_status",      "200"),
    ("empty_result_count",       "<count>"),   # == 0 (no record matches category=C)
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
_IDEAL_RAW = dict(SCENARIOS)

# Which count scenario draws its expected count from which expected_counts key.
COUNT_SCENARIO_SOURCE = {
    "single_filter_count": "single_filter",
    "multi_filter_count": "multi_filter",
    "empty_result_count": "empty_result",
}

# The single documented filter catalogue every collection exposes (to brief the agent).
DOCUMENTED_FILTERS = [
    {"name": "status", "type": "enum", "required": False,
     "enum": ["active", "inactive"],
     "note": "out-of-enum value -> 400 referencing 'status'"},
    {"name": "category", "type": "string", "required": False, "enum": None,
     "note": "free-form exact match; unmatched value -> 200 with an empty result list"},
]

# Documented policy for unknown/unrecognized query parameters on this endpoint.
UNKNOWN_PARAM_POLICY = "reject_400"   # strict: unknown param -> 400 referencing the param

# The status value used by the invalid-value probe (must be out-of-enum).
INVALID_STATUS_VALUE = "unknown_value"
# The empty-result category value (a syntactically valid category that matches nothing).
EMPTY_CATEGORY_VALUE = "C"
# The unknown parameter name used by the unknown-param probe.
UNKNOWN_PARAM_NAME = "bogus_filter"


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT 5-case filter test plan for one collection, derived
    deterministically. This is what the gold reference executes; the agents must
    reproduce the same five cases from their brief."""
    return {
        "collection": cfg["collection"],
        "list_field": cfg["list_field"],
        "id_field": cfg.get("id_field", "id"),
        "cases": [
            {"label": "single_filter", "type": "single",
             "params": {"status": "active"}},
            {"label": "multi_filter", "type": "multi",
             "params": {"status": "active", "category": "A"}},
            {"label": "invalid_value", "type": "invalid",
             "params": {"status": INVALID_STATUS_VALUE}},
            {"label": "unknown_param", "type": "unknown",
             "params": {UNKNOWN_PARAM_NAME: "x"}},
            {"label": "empty_result", "type": "empty",
             "params": {"status": "active", "category": EMPTY_CATEGORY_VALUE}},
        ],
    }


def ideal_for(scenario: str, expected_counts: dict) -> str:
    """The idealized expected token for a scenario, resolving count scenarios from
    the per-collection seed-derived expected_counts."""
    raw = _IDEAL_RAW[scenario]
    if raw == "<count>":
        return str(expected_counts[COUNT_SCENARIO_SOURCE[scenario]])
    return raw


def _status_class(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "200"
    if code == 400:
        return "400"
    if code == 404:
        return "404"
    if code == 422:
        return "422"
    return f"other_{code}"


def _all_match(records, field: str, value: str) -> str:
    if not isinstance(records, list):
        return "missing"
    if not records:
        return "true"   # vacuously: no record violates the filter
    for r in records:
        if not isinstance(r, dict) or r.get(field) != value:
            return "false"
    return "true"


def _none_present(records, forbidden_ids) -> str:
    if not isinstance(records, list):
        return "missing"
    present = {r.get("id") for r in records if isinstance(r, dict)}
    return "true" if not (present & set(forbidden_ids)) else "false"


def evaluate(case_obs: dict, forbidden: dict) -> dict:
    """Compute the observed token for every scenario from raw per-case observations.

    case_obs : {case_label: {"status": int, "records": [...]|None, "total": int|None,
                             "message": str|None}}
               A missing case label => the agent never emitted that case.
    forbidden : {"inactive_ids": [...], "category_b_ids": [...]} for this collection,
                used by the exclusion scenarios.

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}

    def rec(label):
        return case_obs.get(label)

    def status_tok(label):
        r = rec(label)
        return _status_class(r["status"]) if r and "status" in r else "missing"

    def count_tok(label):
        r = rec(label)
        if not r or r.get("status") != 200:
            return "missing"
        recs = r.get("records")
        return str(len(recs)) if isinstance(recs, list) else "missing"

    def message_refs(label, needle):
        r = rec(label)
        if not r:
            return "missing"
        msg = r.get("message")
        if not isinstance(msg, str):
            return "false"
        return "true" if needle.lower() in msg.lower() else "false"

    # single_filter
    obs["single_filter_status"] = status_tok("single_filter")
    obs["single_filter_count"] = count_tok("single_filter")
    r = rec("single_filter")
    obs["single_filter_match"] = (_all_match(r.get("records"), "status", "active")
                                  if r and r.get("status") == 200 else "missing")
    obs["single_filter_exclusion"] = (_none_present(r.get("records"), forbidden.get("inactive_ids", []))
                                       if r and r.get("status") == 200 else "missing")

    # multi_filter
    obs["multi_filter_status"] = status_tok("multi_filter")
    obs["multi_filter_count"] = count_tok("multi_filter")
    r = rec("multi_filter")
    if r and r.get("status") == 200:
        st = _all_match(r.get("records"), "status", "active")
        cat = _all_match(r.get("records"), "category", "A")
        obs["multi_filter_match"] = "true" if st == "true" and cat == "true" else (
            "false" if "false" in (st, cat) else "missing")
        obs["multi_filter_exclusion"] = _none_present(r.get("records"),
                                                      forbidden.get("category_b_ids", []))
    else:
        obs["multi_filter_match"] = "missing"
        obs["multi_filter_exclusion"] = "missing"

    # invalid_value
    obs["invalid_value_status"] = status_tok("invalid_value")
    obs["invalid_value_message"] = message_refs("invalid_value", "status")

    # unknown_param
    obs["unknown_param_status"] = status_tok("unknown_param")
    obs["unknown_param_message"] = message_refs("unknown_param", UNKNOWN_PARAM_NAME)

    # empty_result
    obs["empty_result_status"] = status_tok("empty_result")
    obs["empty_result_count"] = count_tok("empty_result")

    return obs


def correct(scenario: str, observed_token: str, expected_counts: dict) -> bool:
    """Did the API behave per the idealized strict filter contract for this scenario?"""
    return observed_token == ideal_for(scenario, expected_counts)
