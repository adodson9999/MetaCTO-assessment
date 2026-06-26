"""Canonical scenario structure for the API versioning-behavior testing task.

ONE definition of the versioning test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/validate-api-versioning-behavior/build_gold.py), and
  - the harness (agents/common/versioning.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested READ-ONLY as-is — never modified). DummyJSON has
NO API versioning: there is no /v1, /v2, ... router and no Deprecation header anywhere
(confirmed in src/routes/index.js and a grep of src/). Every version-prefixed URL —
current, deprecated, OR unsupported — therefore falls through to the catch-all
`app.get('*')` handler and returns 404 with an HTML body and no Deprecation header.

The IDEALIZED versioning contract this task encodes (what a correctly-versioned API
would do) is:
  - the CURRENT version (v2): 200, body conforms to the v2 response schema, and NO
    Deprecation header.
  - a DEPRECATED version (v1): 200, body conforms to the v1 response schema, AND a
    Deprecation header whose value is a valid ISO-8601 date in the future.
  - the v2 schema declares one field (`schema_diff_field`) the v1 schema omits, so
    that field must be PRESENT in the v2 body and ABSENT from the v1 body, while every
    field common to both schemas is present in both.
  - an UNSUPPORTED numeric version (v0, v99): exactly 404. A non-numeric version token
    (vbeta): 400 or 404.

Each scenario's `ideal` token encodes that idealized behavior; the gold records the
API's REAL token. Where they differ is a genuine QA finding about DummyJSON (here: it
implements no versioning at all, so the documented current/deprecated versions wrongly
404 and never carry a Deprecation header), not an agent bug — mirroring the
validate-request-payloads / pagination / query-parameter philosophy.

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/products", "list_field": "products", "schema_diff_field": "apiVersion",
    "cases": [
      {"label": "current_v2",       "path": "/v2/products",    "version": "v2",    "version_status": "current"},
      {"label": "deprecated_v1",    "path": "/v1/products",    "version": "v1",    "version_status": "deprecated"},
      {"label": "unsupported_v0",   "path": "/v0/products",    "version": "v0",    "version_status": "unsupported"},
      {"label": "unsupported_v99",  "path": "/v99/products",   "version": "v99",   "version_status": "unsupported"},
      {"label": "unsupported_vbeta","path": "/vbeta/products", "version": "vbeta", "version_status": "unsupported"}
    ]
  }

The agent emits these 5 cases; the harness derives the 13 scored scenarios below from
them (the current case yields a status + schema + no-deprecation scenario; the
deprecated case yields a status + schema + deprecation-present + deprecation-ISO +
deprecation-future scenario; the two bodies together yield the two schema-diff
scenarios; each unsupported case yields one routing scenario).
"""
from __future__ import annotations

import re

# The exact five executable cases the agent must emit, by label.
CASE_LABELS = [
    "current_v2",
    "deprecated_v1",
    "unsupported_v0",
    "unsupported_v99",
    "unsupported_vbeta",
]

# --------------------------------------------------------------------------- #
# Documented versioning contract (the INPUT the agents are briefed from).
# Synthetic but reasonable: DummyJSON ships no versioning, so the documented
# contract is authored here exactly as the idealized strict versioning behavior,
# and the gold then records how the real (unversioned) API diverges from it.
# --------------------------------------------------------------------------- #
SUPPORTED_VERSIONS = [
    {"version": "v2", "status": "current"},
    {"version": "v1", "status": "deprecated"},
]
UNSUPPORTED_VERSIONS = ["v0", "v99", "vbeta"]

# The field the v2 response schema declares but the v1 schema omits. Top-level so
# presence/absence is checkable without descending into the item array.
SCHEMA_DIFF_FIELD = "apiVersion"

# A future ISO-8601 date the documented contract states the deprecated version's
# Deprecation header should carry. Informational for the brief only — the harness
# asserts the LIVE response header, never this value.
DOCUMENTED_DEPRECATION_DATE = "2099-01-01"

# Per-version JSON Schemas (draft-07) for a DummyJSON list response. v2 adds the
# schema_diff_field; both share the collection list, total, skip, limit. Used by the
# harness's ajv step (only when a version actually answers 200) and by build_gold.
def schema_for(version: str, list_field: str, schema_diff_field: str = SCHEMA_DIFF_FIELD) -> dict:
    """Return the documented draft-07 response schema for `version` of a list endpoint."""
    base_props = {
        list_field: {"type": "array", "items": {"type": "object"}},
        "total": {"type": "integer"},
        "skip": {"type": "integer"},
        "limit": {"type": "integer"},
    }
    required = [list_field, "total", "skip", "limit"]
    if version == "v2":
        props = dict(base_props)
        props[schema_diff_field] = {"type": "string"}
        return {"type": "object", "properties": props,
                "required": required + [schema_diff_field]}
    # v1: the same response WITHOUT the schema_diff_field.
    return {"type": "object", "properties": dict(base_props), "required": required}


# --------------------------------------------------------------------------- #
# The full, ordered scenario set scored per endpoint (the metric denominator).
# Each scenario carries the idealized expectation under a strict versioning
# contract. `ideal` is the token a perfectly versioned API would produce; gold
# records the REAL token DummyJSON produces.
# --------------------------------------------------------------------------- #
SCENARIOS = [
    ("current_v2_status",                 "200"),      # current version answers 200
    ("current_v2_schema_valid",           "true"),     # body conforms to v2 schema (0 ajv errors)
    ("current_v2_no_deprecation",         "absent"),   # current version carries NO Deprecation header
    ("deprecated_v1_status",              "200"),       # deprecated version still answers 200
    ("deprecated_v1_schema_valid",        "true"),     # body conforms to v1 schema (0 ajv errors)
    ("deprecated_v1_deprecation_present", "present"),  # deprecated version DOES carry a Deprecation header
    ("deprecated_v1_deprecation_iso",     "true"),     # header value is a valid ISO-8601 date
    ("deprecated_v1_deprecation_future",  "true"),     # that date is in the future vs today
    ("schema_diff_field_present_in_v2",   "true"),     # v2-only field present in the v2 body
    ("schema_diff_field_absent_in_v1",    "true"),     # v2-only field absent from the v1 body
    ("unsupported_v0_404",                "404"),       # unsupported numeric version -> 404
    ("unsupported_v99_404",               "404"),       # unsupported numeric version -> 404
    ("unsupported_vbeta_4xx",             "true"),      # non-numeric version -> 400 or 404
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# A future ISO-8601 date string per the task: ^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?")


def build_reference_plan(cfg: dict) -> dict:
    """The canonical correct five-case versioning test plan for one endpoint.
    cfg: {endpoint, list_field, schema_diff_field}."""
    ep = cfg["endpoint"]
    cases = [
        {"label": "current_v2",    "path": f"/v2{ep}",    "version": "v2",    "version_status": "current"},
        {"label": "deprecated_v1", "path": f"/v1{ep}",    "version": "v1",    "version_status": "deprecated"},
        {"label": "unsupported_v0",    "path": f"/v0{ep}",    "version": "v0",    "version_status": "unsupported"},
        {"label": "unsupported_v99",   "path": f"/v99{ep}",   "version": "v99",   "version_status": "unsupported"},
        {"label": "unsupported_vbeta", "path": f"/vbeta{ep}", "version": "vbeta", "version_status": "unsupported"},
    ]
    return {
        "endpoint": ep,
        "list_field": cfg["list_field"],
        "schema_diff_field": cfg.get("schema_diff_field", SCHEMA_DIFF_FIELD),
        "cases": cases,
    }


# --------------------------------------------------------------------------- #
# Evaluation — turn raw per-case observations into the 13 scenario tokens.
# --------------------------------------------------------------------------- #
def _status_class(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "200"
    if code == 400:
        return "400"
    if code == 404:
        return "404"
    if 400 <= code < 500:
        return f"4xx_{code}"
    if 500 <= code < 600:
        return f"5xx_{code}"
    return f"other_{code}"


def _deprecation_present(rec: dict) -> str:
    """'present'/'absent'/'missing'. 'missing' when the case was never run or the
    target never produced a real response (transport error / status None)."""
    if not rec or rec.get("status") is None:
        return "missing"
    val = rec.get("deprecation")
    return "present" if val not in (None, "") else "absent"


def _deprecation_iso(rec: dict) -> str:
    val = (rec or {}).get("deprecation")
    if val in (None, ""):
        return "missing"
    return "true" if ISO_DATE_RE.match(str(val)) else "false"


def _deprecation_future(rec: dict, today: str | None) -> str:
    """today: ISO date string 'YYYY-MM-DD' supplied by the caller (deterministic)."""
    val = (rec or {}).get("deprecation")
    if val in (None, ""):
        return "missing"
    m = ISO_DATE_RE.match(str(val))
    if not m:
        return "missing"
    date_part = str(val)[:10]
    if not today:
        return "missing"
    return "true" if date_part > today else "false"


def _schema_valid(rec: dict) -> str:
    """'true' if the case got a 200 with a documented schema and 0 ajv errors,
    'false' if 200 but the schema did not validate, 'missing' otherwise."""
    if not rec or rec.get("status") != 200:
        return "missing"
    if rec.get("schema_documented") is not True:
        return "missing"
    errs = rec.get("ajv_error_count")
    if errs is None:
        return "missing"
    return "true" if errs == 0 else "false"


def _field_in_body(rec: dict, field: str) -> str | None:
    """True/False whether `field` is a key of the case's 200 JSON body, else None."""
    if not rec or rec.get("status") != 200:
        return None
    body = rec.get("body")
    if not isinstance(body, dict):
        return None
    return field in body


def evaluate(case_obs: dict, schema_diff_field: str, today: str | None) -> dict:
    """Compute the observed token for every scenario from raw per-case observations.

    case_obs : {case_label: {"status": int|None, "body": <json|None>,
                             "deprecation": <header value|None>,
                             "schema_documented": bool, "ajv_error_count": int|None}}
               A missing case label => the agent never emitted that case.
    today    : 'YYYY-MM-DD' for the future-date comparison (deterministic, caller-fixed).

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}
    cur = case_obs.get("current_v2")
    dep = case_obs.get("deprecated_v1")

    def status_tok(label):
        rec = case_obs.get(label)
        return _status_class(rec["status"]) if rec and "status" in rec else "missing"

    # current (v2)
    obs["current_v2_status"] = status_tok("current_v2")
    obs["current_v2_schema_valid"] = _schema_valid(cur) if cur else "missing"
    obs["current_v2_no_deprecation"] = _deprecation_present(cur) if cur else "missing"

    # deprecated (v1)
    obs["deprecated_v1_status"] = status_tok("deprecated_v1")
    obs["deprecated_v1_schema_valid"] = _schema_valid(dep) if dep else "missing"
    obs["deprecated_v1_deprecation_present"] = _deprecation_present(dep) if dep else "missing"
    obs["deprecated_v1_deprecation_iso"] = _deprecation_iso(dep) if dep else "missing"
    obs["deprecated_v1_deprecation_future"] = _deprecation_future(dep, today) if dep else "missing"

    # schema difference between v2 and v1 bodies
    in_v2 = _field_in_body(cur, schema_diff_field)
    in_v1 = _field_in_body(dep, schema_diff_field)
    obs["schema_diff_field_present_in_v2"] = ("true" if in_v2 else "false") if in_v2 is not None else "missing"
    obs["schema_diff_field_absent_in_v1"] = ("true" if in_v1 is False else "false") if in_v1 is not None else "missing"

    # unsupported versions
    obs["unsupported_v0_404"] = status_tok("unsupported_v0")
    obs["unsupported_v99_404"] = status_tok("unsupported_v99")
    beta = case_obs.get("unsupported_vbeta")
    if beta and "status" in beta and beta["status"] is not None:
        obs["unsupported_vbeta_4xx"] = "true" if beta["status"] in (400, 404) else "false"
    else:
        obs["unsupported_vbeta_4xx"] = "missing"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized versioning contract for this scenario?"""
    return observed_token == IDEAL[scenario]


# --------------------------------------------------------------------------- #
# Plan conformance — deterministic structural exactness of an emitted plan vs the
# canonical reference plan. The judge's discriminator that separates frameworks when
# fidelity ties (a plan the tolerant harness silently fixed up loses points here).
# --------------------------------------------------------------------------- #
def _conf_point(cond: bool, label: str, issues: list, weight: int = 1) -> int:
    if cond:
        return weight
    if len(issues) < 40:
        issues.append(label)
    return 0


def plan_conformance(emitted: dict, reference: dict) -> dict:
    """Deterministic structural exactness of one endpoint's emitted plan vs the
    canonical reference plan. Returns {earned, total, issues}. Every value check also
    requires the JSON type to be a string, so a normalised/retyped value costs a point
    here even though the tolerant harness would still route it."""
    issues: list[str] = []
    earned = total = 0

    def score(cond, label, weight=1):
        nonlocal earned, total
        total += weight
        earned += _conf_point(bool(cond), label, issues, weight)

    if not isinstance(emitted, dict):
        return {"earned": 0, "total": 1, "issues": ["plan is not a JSON object"]}

    # --- top-level shape ---
    score(set(emitted.keys()) == set(reference.keys()), "top-level keys differ from reference")
    for k in ("endpoint", "list_field", "schema_diff_field"):
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
            total += 4
            for chk in ("keys", "path", "version", "version_status"):
                if len(issues) < 40:
                    issues.append(f"case '{lab}': {chk} (case absent)")
            continue
        score(set(ec.keys()) == set(rc.keys()), f"case '{lab}' keys differ from reference")
        score(ec.get("path") == rc.get("path") and isinstance(ec.get("path"), str),
              f"case '{lab}' path wrong (must be exactly '/'+version+endpoint_path as a string)")
        score(ec.get("version") == rc.get("version") and isinstance(ec.get("version"), str),
              f"case '{lab}' version wrong")
        score(ec.get("version_status") == rc.get("version_status")
              and isinstance(ec.get("version_status"), str),
              f"case '{lab}' version_status wrong")

    return {"earned": earned, "total": total, "issues": issues}
