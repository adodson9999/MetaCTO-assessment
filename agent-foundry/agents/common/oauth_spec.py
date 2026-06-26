"""Canonical structure for the Verify-Third-Party-OAuth-Integration testing task.

ONE definition of the OAuth2 authorization-code flow test plan + the per-stage,
per-assertion evaluation, shared by:
  - the deterministic gold reference (data/verify-third-party-oauth-integration/build_gold.py), and
  - the harness (agents/common/oauth.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same (flow, assertion-label) key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same key
scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested AS-IS — never modified, per the Phase-2 owner decision):
  - DummyJSON ships NO OAuth2 authorization-code flow: there is no /auth/oauth/<provider>
    redirect, no /auth/callback, no authorization-code /auth/token exchange, and the
    /auth/refresh it does ship is JWT-session refresh, not an OAuth refresh-token grant.
  - The idealized OAuth contract (Stage 1 redirect -> Stage 2 code receipt -> Stage 3
    token exchange -> Stage 4 access-token use -> Stage 5 token refresh) is what each
    assertion's `ideal` token encodes; the gold records the API's REAL token. Where they
    differ is a genuine QA finding about DummyJSON (no third-party OAuth integration
    exists), not an agent bug. The headline OAuth Flow Completion Rate is therefore 0%.

The five documented stages and their per-stage assertions (the metric denominator
per flow). Assertion keys are unprefixed under a stage; the canonical scenario LABEL
is f"s{stage}_{key}" so labels stay unique across stages (status_200 recurs in 3/4/5).
"""
from __future__ import annotations

# The five stages, each pinned to its method, the endpoint it targets (a reference
# key into the brief, never a guessed literal path), and its ordered assertion keys.
STAGE_DEFS = [
    {"stage": 1, "name": "redirect", "method": "GET", "target": "authorize_endpoint",
     "asserts": ["status_302", "location_present", "has_client_id", "has_redirect_uri",
                 "has_scope", "state_present_min8", "location_https"]},
    {"stage": 2, "name": "code_receipt", "method": "GET", "target": "callback_endpoint",
     "asserts": ["callback_code_present", "state_csrf_match"]},
    {"stage": 3, "name": "token_exchange", "method": "POST", "target": "token_endpoint",
     "asserts": ["status_200", "access_token_nonempty", "token_type_bearer",
                 "refresh_token_nonempty", "expires_in_positive"]},
    {"stage": 4, "name": "access_token_use", "method": "GET", "target": "userinfo_endpoint",
     "asserts": ["status_200", "profile_field_nonempty"]},
    {"stage": 5, "name": "token_refresh", "method": "POST", "target": "refresh_endpoint",
     "asserts": ["status_200", "new_access_token_diff", "me_200"]},
]

STAGE_NAMES = [s["name"] for s in STAGE_DEFS]
STAGE_BY_NAME = {s["name"]: s for s in STAGE_DEFS}

# The idealized token a fully-correct OAuth integration would produce, per assertion
# label. A status assertion's ideal is the exact expected code; everything else is
# the boolean "true".
_IDEAL = {
    "s1_status_302": "302",
    "s1_location_present": "true",
    "s1_has_client_id": "true",
    "s1_has_redirect_uri": "true",
    "s1_has_scope": "true",
    "s1_state_present_min8": "true",
    "s1_location_https": "true",
    "s2_callback_code_present": "true",
    "s2_state_csrf_match": "true",
    "s3_status_200": "200",
    "s3_access_token_nonempty": "true",
    "s3_token_type_bearer": "true",
    "s3_refresh_token_nonempty": "true",
    "s3_expires_in_positive": "true",
    "s4_status_200": "200",
    "s4_profile_field_nonempty": "true",
    "s5_status_200": "200",
    "s5_new_access_token_diff": "true",
    "s5_me_200": "200",
}

# Canonical ordered label list = the per-flow metric denominator (19 assertions).
SCENARIO_LABELS = [f"s{s['stage']}_{k}" for s in STAGE_DEFS for k in s["asserts"]]
IDEAL = dict(_IDEAL)

MIN_STATE_LENGTH = 8


def label_for(stage: int, assert_key: str) -> str:
    """The unique scenario label for an assertion under a stage."""
    return f"s{stage}_{assert_key}"


def ideal_for(label: str) -> str:
    """The idealized token a correct OAuth integration would produce for this label."""
    return IDEAL[label]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT 5-stage plan for one flow, derived deterministically from
    its config. Eight context fields are copied unchanged; `stages` is the fixed
    5-stage structure (each stage's method, target reference, and ordered asserts)."""
    return {
        "provider": cfg["provider"],
        "authorize_endpoint": cfg["authorize_endpoint"],
        "callback_endpoint": cfg["callback_endpoint"],
        "token_endpoint": cfg["token_endpoint"],
        "userinfo_endpoint": cfg["userinfo_endpoint"],
        "refresh_endpoint": cfg["refresh_endpoint"],
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg["scope"],
        "state_min_length": cfg.get("state_min_length", MIN_STATE_LENGTH),
        "stages": [
            {"stage": s["stage"], "name": s["name"], "method": s["method"],
             "target": s["target"], "asserts": list(s["asserts"])}
            for s in STAGE_DEFS
        ],
    }


def _status_class(code) -> str:
    """Collapse a status code to the comparison token. 302 and 200 are exact (the
    documented outcomes the task asserts); other 2xx -> '2xx'; None -> 'none';
    else 'other_<n>'."""
    if code is None:
        return "none"
    if code == 302:
        return "302"
    if code == 200:
        return "200"
    if 200 <= code < 300:
        return "2xx"
    return f"other_{code}"


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and len(v) > 0


def _positive_int(v) -> bool:
    """expires_in must be a positive integer > 0. Accept an int or an integer-valued
    numeric string; reject None, zero, negatives, floats-with-fraction, and non-numeric."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return v > 0
    try:
        return int(str(v).strip()) > 0
    except (TypeError, ValueError):
        return False


def evaluate(obs: dict) -> dict:
    """Compute the observed token for every assertion label from raw observations.

    obs is the harness's raw measurement for one flow:
      {
        # Stage 1
        "s1_status": int|None, "s1_location": str|None,
        "s1_client_id_match": bool, "s1_redirect_uri_match": bool, "s1_scope_match": bool,
        "s1_state": str|None,
        # Stage 2
        "s2_code": str|None, "s2_state": str|None, "s1_state_for_csrf": str|None,
        # Stage 3
        "s3_status": int|None, "s3_access_token": str|None, "s3_token_type": str|None,
        "s3_refresh_token": str|None, "s3_expires_in": object,
        # Stage 4
        "s4_status": int|None, "s4_profile_value": str|None,
        # Stage 5
        "s5_status": int|None, "s5_new_access_token": str|None, "s5_old_access_token": str|None,
        "s5_me_status": int|None,
        # which stages actually executed (a stage not reached -> its asserts score 'missing')
        "stages_run": {"redirect": bool, "code_receipt": bool, "token_exchange": bool,
                       "access_token_use": bool, "token_refresh": bool},
      }
    Returns {label: observed_token}. "missing" marks an assertion whose stage the agent
    never planned (so the harness never ran it), counting as a mismatch vs gold.
    """
    run = obs.get("stages_run", {}) or {}
    out: dict[str, str] = {}

    # ---- Stage 1: redirect ----
    if run.get("redirect"):
        out["s1_status_302"] = _status_class(obs.get("s1_status"))
        loc = obs.get("s1_location")
        out["s1_location_present"] = "true" if _nonempty_str(loc) else "false"
        out["s1_has_client_id"] = "true" if obs.get("s1_client_id_match") else "false"
        out["s1_has_redirect_uri"] = "true" if obs.get("s1_redirect_uri_match") else "false"
        out["s1_has_scope"] = "true" if obs.get("s1_scope_match") else "false"
        st = obs.get("s1_state")
        out["s1_state_present_min8"] = (
            "true" if (_nonempty_str(st) and len(st) >= MIN_STATE_LENGTH) else "false")
        out["s1_location_https"] = (
            "true" if (_nonempty_str(loc) and loc.lower().startswith("https://")) else "false")
    else:
        for k in STAGE_BY_NAME["redirect"]["asserts"]:
            out[label_for(1, k)] = "missing"

    # ---- Stage 2: code receipt ----
    if run.get("code_receipt"):
        code = obs.get("s2_code")
        out["s2_callback_code_present"] = "true" if _nonempty_str(code) else "false"
        s1_state = obs.get("s1_state_for_csrf")
        s2_state = obs.get("s2_state")
        out["s2_state_csrf_match"] = (
            "true" if (_nonempty_str(s1_state) and s1_state == s2_state) else "false")
    else:
        for k in STAGE_BY_NAME["code_receipt"]["asserts"]:
            out[label_for(2, k)] = "missing"

    # ---- Stage 3: token exchange ----
    if run.get("token_exchange"):
        out["s3_status_200"] = _status_class(obs.get("s3_status"))
        out["s3_access_token_nonempty"] = "true" if _nonempty_str(obs.get("s3_access_token")) else "false"
        out["s3_token_type_bearer"] = "true" if obs.get("s3_token_type") == "Bearer" else "false"
        out["s3_refresh_token_nonempty"] = "true" if _nonempty_str(obs.get("s3_refresh_token")) else "false"
        out["s3_expires_in_positive"] = "true" if _positive_int(obs.get("s3_expires_in")) else "false"
    else:
        for k in STAGE_BY_NAME["token_exchange"]["asserts"]:
            out[label_for(3, k)] = "missing"

    # ---- Stage 4: access-token use ----
    if run.get("access_token_use"):
        out["s4_status_200"] = _status_class(obs.get("s4_status"))
        out["s4_profile_field_nonempty"] = "true" if _nonempty_str(obs.get("s4_profile_value")) else "false"
    else:
        for k in STAGE_BY_NAME["access_token_use"]["asserts"]:
            out[label_for(4, k)] = "missing"

    # ---- Stage 5: token refresh ----
    if run.get("token_refresh"):
        out["s5_status_200"] = _status_class(obs.get("s5_status"))
        new = obs.get("s5_new_access_token")
        old = obs.get("s5_old_access_token")
        out["s5_new_access_token_diff"] = (
            "true" if (_nonempty_str(new) and new != old) else "false")
        out["s5_me_200"] = _status_class(obs.get("s5_me_status"))
    else:
        for k in STAGE_BY_NAME["token_refresh"]["asserts"]:
            out[label_for(5, k)] = "missing"

    return out


def correct(label: str, observed_token: str) -> bool:
    """Did the API produce the idealized documented outcome for this assertion?"""
    return observed_token == ideal_for(label)


def stage_correct(stage: int, observed: dict) -> bool:
    """A stage 'produces the correct documented outcome' iff EVERY assertion under it
    matches its ideal token. Used for the headline OAuth Flow Completion Rate."""
    sdef = next(s for s in STAGE_DEFS if s["stage"] == stage)
    return all(correct(label_for(stage, k), observed.get(label_for(stage, k), "missing"))
               for k in sdef["asserts"])


def flow_complete(observed: dict) -> bool:
    """OAuth flow completion = all 5 stages produce the correct documented outcome."""
    return all(stage_correct(s["stage"], observed) for s in STAGE_DEFS)
