"""Canonical scenario structure for the API query-parameter-handling testing task.

ONE definition of the query-parameter test plan + the per-scenario evaluation,
shared by:
  - the deterministic gold reference (data/validate-query-parameter-handling/build_gold.py), and
  - the harness (agents/common/queryparam.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested READ-ONLY as-is — never modified). The documented
query-parameter contract for each list collection (from src/middleware/clean-request.js):
  - limit   : integer, optional (default 30). Non-numeric -> 400.
  - skip    : integer, optional (default 0).  Non-numeric -> 400.
  - select  : string  (csv field list), optional. Projection filter (always adds 'id').
  - sortBy  : string, optional.
  - order   : string, enum {asc, desc}, optional. Validated ONLY when sortBy is also
              present; an out-of-enum value then -> 400. order alone is ignored.
  - q       : string. On the `<collection>/search` route it is the search query. The
              IDEALIZED contract declares q REQUIRED on /search; DummyJSON treats it
              as optional (absent q -> 200 over the whole collection). That divergence
              is the genuine QA finding this task surfaces.
  - Undocumented params (e.g. unexpected_param) are silently ignored -> 200. The
    documented policy for this API is therefore "ignore unknown params" (ideal 200).

The idealized query-parameter contract (a strict API: required-absent -> 400,
wrong-type -> 400, valid -> 200 + the parameter's filter effect realized) is what
each scenario's `ideal` token encodes; the gold records the API's REAL token. Where
they differ is a genuine QA finding about DummyJSON, not an agent bug.

A plan for one collection (the agent's output, and the reference) looks like:
  {
    "collection": "/products", "list_field": "products", "id_field": "id",
    "search_path": "/products/search",
    "cases": [
      {"label": "missing_required_q",         "route": "search", "type": "missing",      "params": {}},
      {"label": "wrongtype_limit_nonnumeric", "route": "list",   "type": "wrong_type",   "params": {"limit": "abc"}},
      {"label": "wrongtype_skip_nonnumeric",  "route": "list",   "type": "wrong_type",   "params": {"skip": "abc"}},
      {"label": "wrongtype_order_badenum",    "route": "list",   "type": "wrong_type",   "params": {"sortBy": "id", "order": "NOT_A_VALID_VALUE"}},
      {"label": "valid_limit",  "route": "list",   "type": "valid", "filter": "limit",  "filter_value": "5",  "params": {"limit": "5"}},
      {"label": "valid_select", "route": "list",   "type": "valid", "filter": "select", "filter_value": "id", "params": {"select": "id"}},
      {"label": "valid_order",  "route": "list",   "type": "valid", "filter": "order",  "filter_value": "desc","params": {"sortBy": "id", "order": "desc"}},
      {"label": "valid_q",      "route": "search", "type": "valid", "params": {"q": "e"}},
      {"label": "undocumented_ignored", "route": "list", "type": "undocumented", "params": {"unexpected_param": "test123"}}
    ]
  }

The agent emits these 9 cases; the harness derives the 12 scored scenarios below
from them (each of the three valid-filter cases yields a status scenario AND a
filter scenario).
"""
from __future__ import annotations

# The exact nine executable cases the agent must emit, by label.
CASE_LABELS = [
    "missing_required_q",
    "wrongtype_limit_nonnumeric",
    "wrongtype_skip_nonnumeric",
    "wrongtype_order_badenum",
    "valid_limit",
    "valid_select",
    "valid_order",
    "valid_q",
    "undocumented_ignored",
]

# The full, ordered scenario set scored per collection (the metric denominator).
# Each scenario carries the idealized expectation under a strict query-parameter
# contract. `ideal` is the token a perfectly behaving API would produce; gold
# records the REAL token DummyJSON produces.
SCENARIOS = [
    ("missing_required_q",          "400"),   # /search with q absent -> ideal 400
    ("wrongtype_limit_nonnumeric",  "400"),
    ("wrongtype_skip_nonnumeric",   "400"),
    ("wrongtype_order_badenum",     "400"),
    ("valid_limit_status",          "200"),
    ("valid_limit_filter",          "true"),  # returned count <= limit
    ("valid_select_status",         "200"),
    ("valid_select_filter",         "true"),  # every record's keys subset of {id}
    ("valid_order_status",          "200"),
    ("valid_order_filter",          "true"),  # records sorted by id descending
    ("valid_q_status",              "200"),
    ("undocumented_ignored",        "200"),   # documented policy: unknown params ignored
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# The single, fixed documented query-parameter catalogue every list collection
# exposes (used to brief the agent). Each entry: name, type, required, enum.
DOCUMENTED_PARAMS = [
    {"name": "limit",  "type": "integer", "required": False, "enum": None},
    {"name": "skip",   "type": "integer", "required": False, "enum": None},
    {"name": "select", "type": "string",  "required": False, "enum": None},
    {"name": "sortBy", "type": "string",  "required": False, "enum": None},
    {"name": "order",  "type": "string",  "required": False, "enum": ["asc", "desc"]},
    {"name": "q",      "type": "string",  "required": True,  "enum": None,
     "route": "search", "note": "search query on <collection>/search; idealized contract requires it"},
]

# The documented policy for unknown/undocumented parameters on this API.
UNDOCUMENTED_POLICY = "ignore"   # unknown params are silently ignored -> ideal 200


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT 9-case query-parameter test plan for one collection,
    derived deterministically from its config. This is what the gold reference
    executes; the agents must reproduce the same nine cases from their brief."""
    col = cfg["collection"]
    lf = cfg["list_field"]
    idf = cfg.get("id_field", "id")
    sp = cfg.get("search_path", col + "/search")
    cases = [
        {"label": "missing_required_q",         "route": "search", "type": "missing",
         "params": {}},
        {"label": "wrongtype_limit_nonnumeric", "route": "list",   "type": "wrong_type",
         "params": {"limit": "abc"}},
        {"label": "wrongtype_skip_nonnumeric",  "route": "list",   "type": "wrong_type",
         "params": {"skip": "abc"}},
        {"label": "wrongtype_order_badenum",    "route": "list",   "type": "wrong_type",
         "params": {"sortBy": "id", "order": "NOT_A_VALID_VALUE"}},
        {"label": "valid_limit",  "route": "list", "type": "valid", "filter": "limit",
         "filter_value": "5",  "params": {"limit": "5"}},
        {"label": "valid_select", "route": "list", "type": "valid", "filter": "select",
         "filter_value": "id", "params": {"select": "id"}},
        {"label": "valid_order",  "route": "list", "type": "valid", "filter": "order",
         "filter_value": "desc", "params": {"sortBy": "id", "order": "desc"}},
        {"label": "valid_q",      "route": "search", "type": "valid",
         "params": {"q": "e"}},
        {"label": "undocumented_ignored", "route": "list", "type": "undocumented",
         "params": {"unexpected_param": "test123"}},
    ]
    return {
        "collection": col,
        "list_field": lf,
        "id_field": idf,
        "search_path": sp,
        "cases": cases,
    }


def _status_class(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "200"
    if code == 400:
        return "400"
    if code == 422:
        return "422"
    if code == 404:
        return "404"
    return f"other_{code}"


def _filter_holds(case_rec: dict, filt: str, filter_value: str, id_field: str) -> str:
    """Return 'true'/'false'/'missing' for whether the parameter's filter effect is
    realized in the response records. Deterministic, per filter kind."""
    if not case_rec or case_rec.get("status") != 200:
        return "missing"
    records = case_rec.get("records")
    if not isinstance(records, list):
        return "missing"
    if filt == "limit":
        try:
            cap = int(filter_value)
        except Exception:  # noqa
            return "missing"
        # limit=0 means "return all" in DummyJSON; we only use limit=5 here (cap>0).
        return "true" if len(records) <= cap else "false"
    if filt == "select":
        selected = {s.strip() for s in str(filter_value).split(",") if s.strip()}
        selected.add(id_field)  # DummyJSON always includes id in a projection
        for r in records:
            if not isinstance(r, dict):
                return "false"
            if not set(r.keys()).issubset(selected):
                return "false"
        return "true"
    if filt == "order":
        ids = [r.get(id_field) for r in records if isinstance(r, dict)]
        ids = [i for i in ids if isinstance(i, (int, float))]
        if len(ids) < 2:
            return "missing"
        descending = all(ids[i] >= ids[i + 1] for i in range(len(ids) - 1))
        return "true" if descending else "false"
    return "missing"


def evaluate(case_obs: dict, id_field: str = "id") -> dict:
    """Compute the observed token for every scenario from raw per-case observations.

    case_obs : {case_label: {"status": int, "records": [...]|None, "total": int|None,
                             "filter": str|None, "filter_value": str|None}}
               A missing case label => the agent never emitted that case.

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}

    def status_tok(label):
        rec = case_obs.get(label)
        return _status_class(rec["status"]) if rec and "status" in rec else "missing"

    # direct status scenarios
    obs["missing_required_q"] = status_tok("missing_required_q")
    obs["wrongtype_limit_nonnumeric"] = status_tok("wrongtype_limit_nonnumeric")
    obs["wrongtype_skip_nonnumeric"] = status_tok("wrongtype_skip_nonnumeric")
    obs["wrongtype_order_badenum"] = status_tok("wrongtype_order_badenum")
    obs["valid_q_status"] = status_tok("valid_q")
    obs["undocumented_ignored"] = status_tok("undocumented_ignored")

    # valid-filter cases: each yields a status scenario AND a filter scenario
    for case_label, status_key, filter_key, filt in (
        ("valid_limit",  "valid_limit_status",  "valid_limit_filter",  "limit"),
        ("valid_select", "valid_select_status", "valid_select_filter", "select"),
        ("valid_order",  "valid_order_status",  "valid_order_filter",  "order"),
    ):
        rec = case_obs.get(case_label)
        obs[status_key] = _status_class(rec["status"]) if rec and "status" in rec else "missing"
        fv = (rec or {}).get("filter_value")
        obs[filter_key] = _filter_holds(rec, filt, fv, id_field) if rec else "missing"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized query-parameter contract for this scenario?"""
    return observed_token == IDEAL[scenario]


# --------------------------------------------------------------------------- #
# Discriminator layer — Plan Conformance
# --------------------------------------------------------------------------- #
# Fidelity (correctness) saturates: the harness is deliberately tolerant — it
# normalises a sloppy plan (missing params key, extra keys, a number where a string
# was required) before executing it, so two agents can both reproduce the gold while
# one emitted a far less disciplined plan. Plan Conformance measures that discipline
# DETERMINISTICALLY by diffing the agent's RAW emitted plan against the canonical
# debate-gated reference plan, BEFORE any normalisation. It is the construction-quality
# discriminator that breaks fidelity ties without any framework-specific plumbing.

def _conf_point(cond: bool, label: str, issues: list, weight: int = 1) -> int:
    if cond:
        return weight
    if len(issues) < 40:
        issues.append(label)
    return 0


def plan_conformance(emitted: dict, reference: dict) -> dict:
    """Deterministic structural exactness of one collection's emitted plan vs the
    canonical reference plan. Returns {earned, total, issues}. Every value-literal
    check also requires the JSON type to be a string, so emitting 5 instead of "5"
    (which the harness would silently accept) costs a point here."""
    issues: list[str] = []
    earned = total = 0

    def score(cond, label, weight=1):
        nonlocal earned, total
        total += weight
        earned += _conf_point(bool(cond), label, issues, weight)

    if not isinstance(emitted, dict):
        return {"earned": 0, "total": 1, "issues": ["plan is not a JSON object"]}

    # --- top-level shape ---
    ref_keys = set(reference.keys())
    score(set(emitted.keys()) == ref_keys, "top-level keys differ from reference")
    for k in ("collection", "list_field", "id_field", "search_path"):
        score(emitted.get(k) == reference.get(k), f"top-level '{k}' not copied unchanged")

    ref_cases = reference.get("cases", [])
    em_cases = emitted.get("cases")
    score(isinstance(em_cases, list), "'cases' is not a list")
    em_cases = em_cases if isinstance(em_cases, list) else []
    score(len(em_cases) == len(ref_cases), f"'cases' length {len(em_cases)} != {len(ref_cases)}")

    ref_labels = [c["label"] for c in ref_cases]
    em_labels = [c.get("label") for c in em_cases if isinstance(c, dict)]
    score(em_labels == ref_labels, "case labels/order differ from reference")

    by_label = {c.get("label"): c for c in em_cases if isinstance(c, dict)}

    for rc in ref_cases:
        lab = rc["label"]
        ec = by_label.get(lab)
        score(ec is not None, f"case '{lab}' missing")
        if not isinstance(ec, dict):
            # still count the remaining checks for this case as misses
            total += 4
            for chk in ("keys", "route", "type", "params"):
                issues.append(f"case '{lab}': {chk} (case absent)") if len(issues) < 40 else None
            if rc.get("filter") is not None:
                total += 1
                issues.append(f"case '{lab}': filter (case absent)") if len(issues) < 40 else None
            continue
        score(set(ec.keys()) == set(rc.keys()), f"case '{lab}' keys differ from reference")
        score(ec.get("route") == rc.get("route"), f"case '{lab}' route wrong")
        score(ec.get("type") == rc.get("type"), f"case '{lab}' type wrong")
        # params: identical keys, identical STRING values
        rp = rc.get("params", {})
        ep = ec.get("params", {})
        params_ok = (
            isinstance(ep, dict)
            and set(ep.keys()) == set(rp.keys())
            and all(ep.get(k) == v and isinstance(ep.get(k), str) for k, v in rp.items())
        )
        score(params_ok, f"case '{lab}' params keys/values/type wrong")
        # filter + filter_value on the three valid-filter cases
        if rc.get("filter") is not None:
            filt_ok = (ec.get("filter") == rc.get("filter")
                       and ec.get("filter_value") == rc.get("filter_value")
                       and isinstance(ec.get("filter_value"), str))
            score(filt_ok, f"case '{lab}' filter/filter_value wrong")

    return {"earned": earned, "total": total, "issues": issues}
