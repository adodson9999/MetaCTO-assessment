"""Canonical scenario structure for the API caching-headers testing task.

ONE definition of the caching test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/verify-caching-headers/build_gold.py), and
  - the harness (agents/common/caching.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, exercised as-is — verified live + in src/controllers/*.js):
  - GET /<col>/<id> -> 200; Express auto-adds a WEAK ETag (W/"...") hashed from the
    body, and does NOT add any Cache-Control header.
  - A conditional GET carrying If-None-Match: <that ETag> -> 304 with an EMPTY body
    (Express `fresh()` handles it).
  - PUT/PATCH/DELETE/POST controllers RETURN a computed object and never persist
    (the dataset is deepFrozen), so after a PUT the resource is UNCHANGED -> a fresh
    GET hashes the SAME body -> the SAME ETag (ETAG_2 == ETAG_1), and the "stale"
    ETAG_1 still matches -> the conditional GET still returns 304, not 200.
  - Mutation responses (POST/PUT/PATCH/DELETE) carry no Cache-Control header at all,
    so none declares `no-store`.

  The idealized caching contract (positive max-age Cache-Control on cacheable GETs,
  a non-empty ETag, a 304-with-empty-body conditional GET, an ETag that CHANGES after
  an update, a stale ETag that no longer matches, and `no-store` on mutations) is what
  each scenario's `ideal` token encodes; the gold records the API's REAL token. Where
  they differ is a genuine QA finding about DummyJSON, not an agent bug.

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "collection": "/products", "id_field": "id", "target_id": 1,
    "cacheable_get":  {"label": "get",    "method": "GET", "path": "/products/1"},
    "update_request": {"label": "update", "method": "PUT", "path": "/products/1",
                       "body": {"title": "caching-probe-changed"}},
    "mutation_requests": [
      {"label": "post",   "method": "POST",   "path": "/products/add", "body": {"title": "caching-probe"}},
      {"label": "put",    "method": "PUT",    "path": "/products/1",   "body": {"title": "caching-probe"}},
      {"label": "patch",  "method": "PATCH",  "path": "/products/1",   "body": {"title": "caching-probe"}},
      {"label": "delete", "method": "DELETE", "path": "/products/1",   "body": null}
    ]
  }
"""
from __future__ import annotations

import re

# The changed field the update request sends (a different title forces a different
# body — and so a different ETag — on any API that actually persists the write).
UPDATE_BODY = {"title": "caching-probe-changed"}
# A neutral body for the mutation no-store probes (value is irrelevant to the header check).
MUTATION_BODY = {"title": "caching-probe"}

# Cache-Control must contain a POSITIVE-integer max-age to count as cacheable.
MAXAGE_RE = re.compile(r"max-age=([1-9][0-9]*)")
# A mutation endpoint is compliant if Cache-Control is exactly "no-store" or the
# canonical "no-cache, no-store" form (case-insensitive, whitespace-normalized).
NO_STORE_VALUES = {"no-store", "no-cache, no-store"}

# The four mutation methods every cacheable resource is paired with for the no-store check.
MUTATION_LABELS = ["post", "put", "patch", "delete"]

# The full, ordered scenario set scored per endpoint (the fidelity denominator).
# `ideal` is the token a perfectly caching-correct API would produce; gold records the
# REAL token DummyJSON produces. 11 scenarios x N endpoints = fidelity denominator.
SCENARIOS = [
    ("cache_control_positive_maxage", "true"),   # GET Cache-Control has max-age=[1-9][0-9]*
    ("etag_present_nonempty",         "true"),   # GET ETag header present and non-empty
    ("conditional_get_returns_304",   "true"),   # If-None-Match: ETAG_1 -> exactly 304
    ("conditional_get_body_empty",    "true"),   # that 304's body byte length == 0
    ("update_returns_200",            "true"),   # PUT changed field -> 200
    ("etag_changes_after_update",     "true"),   # ETAG_2 != ETAG_1 after the update
    ("stale_etag_returns_200",        "true"),   # old ETAG_1 after update -> 200 (not 304)
    ("post_no_store",                 "true"),   # POST   response Cache-Control no-store
    ("put_no_store",                  "true"),   # PUT    response Cache-Control no-store
    ("patch_no_store",                "true"),   # PATCH  response Cache-Control no-store
    ("delete_no_store",               "true"),   # DELETE response Cache-Control no-store
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# The sub-scenarios whose conjunction defines a PASS for the headline
# Caching Header Compliance Rate (per the task's own pass rule): a cacheable endpoint
# passes iff Cache-Control has a valid positive max-age AND ETag is non-empty AND the
# conditional GET returns 304 with an empty body AND the post-update ETag changes.
COMPLIANCE_SUBSCENARIOS = [
    "cache_control_positive_maxage",
    "etag_present_nonempty",
    "conditional_get_returns_304",
    "conditional_get_body_empty",
    "etag_changes_after_update",
]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one endpoint, derived deterministically from its
    config (collection, id_field, target_id). Identical structure to what a faithful
    agent must emit."""
    col = cfg["collection"]
    tid = cfg["target_id"]
    item = f"{col}/{tid}"
    return {
        "collection": col,
        "id_field": cfg.get("id_field", "id"),
        "target_id": tid,
        "cacheable_get": {"label": "get", "method": "GET", "path": item},
        "update_request": {"label": "update", "method": "PUT", "path": item,
                           "body": dict(UPDATE_BODY)},
        "mutation_requests": [
            {"label": "post", "method": "POST", "path": f"{col}/add", "body": dict(MUTATION_BODY)},
            {"label": "put", "method": "PUT", "path": item, "body": dict(MUTATION_BODY)},
            {"label": "patch", "method": "PATCH", "path": item, "body": dict(MUTATION_BODY)},
            {"label": "delete", "method": "DELETE", "path": item, "body": None},
        ],
    }


def _has_positive_maxage(cache_control: str | None) -> bool:
    if not cache_control:
        return False
    return MAXAGE_RE.search(cache_control) is not None


def _is_no_store(cache_control: str | None) -> bool:
    if not cache_control:
        return False
    normalized = ", ".join(p.strip() for p in cache_control.lower().split(",") if p.strip())
    return normalized in NO_STORE_VALUES


def evaluate(get_obs: dict, conditional_obs: dict, update_obs: dict,
             reget_obs: dict, stale_obs: dict, mutation_obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    get_obs        : {"status": int|None, "cache_control": str|None, "etag": str|None}
    conditional_obs: {"status": int|None, "body_len": int|None}     (If-None-Match: ETAG_1)
    update_obs     : {"status": int|None}                            (PUT changed field)
    reget_obs      : {"status": int|None, "etag": str|None}          (fresh GET -> ETAG_2)
    stale_obs      : {"status": int|None}                            (If-None-Match: ETAG_1, now stale)
    mutation_obs   : {label: {"status": int|None, "cache_control": str|None}}

    A scenario whose required observation is missing/None scores the token "missing".
    Returns {scenario: observed_token}. Tokens are "true"/"false"/"missing".
    """
    obs: dict[str, str] = {}
    etag1 = get_obs.get("etag")
    etag2 = reget_obs.get("etag")

    # GET Cache-Control / ETag
    if get_obs.get("status") is None:
        obs["cache_control_positive_maxage"] = "missing"
        obs["etag_present_nonempty"] = "missing"
    else:
        obs["cache_control_positive_maxage"] = "true" if _has_positive_maxage(get_obs.get("cache_control")) else "false"
        obs["etag_present_nonempty"] = "true" if (etag1 is not None and etag1 != "") else "false"

    # Conditional GET (304 + empty body)
    cstatus = conditional_obs.get("status")
    obs["conditional_get_returns_304"] = "missing" if cstatus is None else ("true" if cstatus == 304 else "false")
    blen = conditional_obs.get("body_len")
    if cstatus is None or blen is None:
        obs["conditional_get_body_empty"] = "missing"
    else:
        obs["conditional_get_body_empty"] = "true" if blen == 0 else "false"

    # Update -> 200
    ustatus = update_obs.get("status")
    obs["update_returns_200"] = "missing" if ustatus is None else ("true" if ustatus == 200 else "false")

    # ETag changes after update (requires both ETags observed)
    if reget_obs.get("status") is None or etag1 is None or etag2 is None:
        obs["etag_changes_after_update"] = "missing"
    else:
        obs["etag_changes_after_update"] = "true" if etag2 != etag1 else "false"

    # Stale ETag -> 200 (not 304)
    sstatus = stale_obs.get("status")
    obs["stale_etag_returns_200"] = "missing" if sstatus is None else ("true" if sstatus == 200 else "false")

    # Mutation no-store
    for label in MUTATION_LABELS:
        rec = mutation_obs.get(label)
        key = f"{label}_no_store"
        if not rec or rec.get("status") is None:
            obs[key] = "missing"
        else:
            obs[key] = "true" if _is_no_store(rec.get("cache_control")) else "false"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized caching contract for this scenario?"""
    return observed_token == IDEAL[scenario]


def compliance(observed_by_collection: dict) -> dict:
    """The headline Caching Header Compliance Rate over cacheable endpoints. An endpoint
    PASSES iff all of its COMPLIANCE_SUBSCENARIOS observed "true" (valid positive max-age
    Cache-Control AND non-empty ETag AND conditional GET 304-with-empty-body AND a
    post-update ETag change).

    observed_by_collection: {collection: {scenario: observed_token}}
    Returns {passing, total, rate_pct, cases:[...]}.
    """
    cases = []
    passing = total = 0
    for col, obs in observed_by_collection.items():
        toks = {s: obs.get(s, "missing") for s in COMPLIANCE_SUBSCENARIOS}
        ok = all(t == "true" for t in toks.values())
        cases.append({"collection": col, "sub_tokens": toks, "pass": ok})
        total += 1
        passing += 1 if ok else 0
    rate = round(100.0 * passing / total, 2) if total else 0.0
    return {"passing": passing, "total": total, "rate_pct": rate, "cases": cases}
