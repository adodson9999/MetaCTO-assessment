"""Canonical structure for the API authorization-rules testing task.

ONE definition of the authorization sub-test matrix, shared by:
  - the deterministic gold reference (data/authz/build_gold.py) — derives the
    reference matrix and executes it against the live target, and
  - the harness (agents/common/authz_contract.py) — iterates whatever matrix an
    agent emitted and executes each case against the same live target.

Pure: no env, no I/O, no LLM. Keeps the agent output and the gold set on exactly
the same case-key scheme (keyed by `sub_test`) so the judge can compare them
field-for-field.

The six canonical sub-tests (the security contract the agent asserts):
  VIEWER_GET             viewer GETs owner B's resource    -> contract: 403, no data
  VIEWER_PUT             viewer PUTs  owner B's resource    -> contract: 403, no data
  VIEWER_DELETE          viewer DELETEs owner B's resource  -> contract: 403, no data
  ADMIN_GET              admin  GETs  owner B's resource    -> contract: 200, data present
  VIEWER_ADMIN_ENDPOINT  viewer GETs the admin-only listing -> contract: 403, no data
  VIEWER_LIST            viewer GETs the collection         -> contract: 200, owner res absent

Two negative auth controls (authentication, not authorization) are appended so the
report also records the access surface the API *does* defend:
  NO_TOKEN_GET           no credentials -> contract: 401
  BAD_TOKEN_GET          malformed token -> contract: 401

Each sub-test carries leakage assertions (the LLM-driven part the frameworks
differ on): for every case whose contract code is NOT 2xx, the response body must
(a) carry a non-empty "error" or "message" field and (b) contain none of the
forbidden substrings, and for the unauthorized-resource cases the body must expose
none of the owner resource's field names.
"""
from __future__ import annotations

# Canonical sub-test order. Each name is the unique case key for the judge.
SUB_TESTS = [
    "VIEWER_GET", "VIEWER_PUT", "VIEWER_DELETE", "ADMIN_GET",
    "VIEWER_ADMIN_ENDPOINT", "VIEWER_LIST", "NO_TOKEN_GET", "BAD_TOKEN_GET",
]

# Substrings that must never appear in any error body (info-leak guards).
FORBIDDEN_SUBSTRINGS = ["stack", "Error:", ".js:", ".ts:", "/src/", "/Users/",
                        "node_modules", "SELECT ", "INSERT ", "UPDATE ", "WHERE ",
                        "Traceback", "at Object.", "at async"]


def classify(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "2xx"
    if code == 401:
        return "401"
    if code == 403:
        return "403"
    return f"other_{code}"


def reference_matrix(resource_field_names: list[str], resource_path: str,
                     collection_path: str, admin_listing_path: str,
                     resource_id: str) -> list[dict]:
    """Produce the canonical eight-case authorization matrix deterministically.

    Inputs describe the access surface in the abstract; the harness binds the
    requesting_role to a concrete token and {id} to the real owned resource id.

    Each case object (the same shape an agent emits):
        sub_test, requesting_role, method, endpoint, resource_owner,
        expected_code, leakage{forbidden_fields, forbidden_substrings},
        expect_resource_data (bool), list_must_exclude (resource id | null)
    """
    leak = {"forbidden_fields": list(resource_field_names),
            "forbidden_substrings": list(FORBIDDEN_SUBSTRINGS)}
    res = resource_path  # e.g. "/auth/posts/{id}"

    return [
        {"sub_test": "VIEWER_GET", "requesting_role": "viewer", "method": "GET",
         "endpoint": res, "resource_owner": "owner", "expected_code": 403,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
        {"sub_test": "VIEWER_PUT", "requesting_role": "viewer", "method": "PUT",
         "endpoint": res, "resource_owner": "owner", "expected_code": 403,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
        {"sub_test": "VIEWER_DELETE", "requesting_role": "viewer", "method": "DELETE",
         "endpoint": res, "resource_owner": "owner", "expected_code": 403,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
        {"sub_test": "ADMIN_GET", "requesting_role": "admin", "method": "GET",
         "endpoint": res, "resource_owner": "owner", "expected_code": 200,
         "leakage": leak, "expect_resource_data": True, "list_must_exclude": None},
        {"sub_test": "VIEWER_ADMIN_ENDPOINT", "requesting_role": "viewer", "method": "GET",
         "endpoint": admin_listing_path, "resource_owner": "none", "expected_code": 403,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
        {"sub_test": "VIEWER_LIST", "requesting_role": "viewer", "method": "GET",
         "endpoint": collection_path, "resource_owner": "none", "expected_code": 200,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": resource_id},
        {"sub_test": "NO_TOKEN_GET", "requesting_role": "none", "method": "GET",
         "endpoint": res, "resource_owner": "owner", "expected_code": 401,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
        {"sub_test": "BAD_TOKEN_GET", "requesting_role": "malformed", "method": "GET",
         "endpoint": res, "resource_owner": "owner", "expected_code": 401,
         "leakage": leak, "expect_resource_data": False, "list_must_exclude": None},
    ]


def iter_cases(out: dict):
    """Yield each well-formed case from an agent's (or gold's) emitted matrix.

    Tolerant of missing/malformed entries (an agent may omit some). Yields the
    case dict directly; the harness binds + executes it. A case missing a
    `sub_test` or `endpoint` is skipped (cannot be executed or keyed)."""
    if not isinstance(out, dict):
        return
    seen = set()
    for case in _as_list(out.get("cases")):
        if not isinstance(case, dict):
            continue
        st = case.get("sub_test")
        if not st or st in seen or not case.get("endpoint") or not case.get("method"):
            continue
        seen.add(st)
        yield case


def _as_list(v):
    return v if isinstance(v, list) else []
