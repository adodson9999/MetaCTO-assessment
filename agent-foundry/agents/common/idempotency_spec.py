"""Canonical scenario structure for the API idempotency-of-endpoints testing task.

ONE definition of the idempotency test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-idempotency-of-endpoints/build_gold.py), and
  - the harness (agents/common/idempotency.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, write endpoints exercised as-is — verified NON-PERSISTENT):
  - The in-memory dataset is deepFrozen; PUT / PATCH / DELETE / POST controllers
    RETURN a computed object and never mutate or persist anything. So issuing real
    writes does not modify the target (confirmed in src/controllers/*.js and live).
  - PUT /<col>/<id>   -> 200, deterministic merge of body over the frozen record.
                        Replaying with one Idempotency-Key => BYTE-IDENTICAL bodies.
  - DELETE /<col>/<id> -> 200, body carries `deletedOn: new Date().toISOString()`,
                        a FRESH timestamp each call => bodies DIFFER byte-for-byte.
  - POST /<col>/add   -> 201, id = frozenData.<col>.length + 1 (constant), so a
                        replay AND a fresh-key request return the SAME id => the
                        Idempotency-Key header has NO effect (it is ignored).
  - There is NO SQL database and writes do not persist, so the literal "SELECT
    COUNT(*) ... = 1" check is mapped onto a read-only state-effect probe:
    GET the target record (exists exactly once) / read the collection `total`
    (unchanged => no duplicate record was created).

  The idealized idempotency contract (consistent status + byte-identical body on
  replay, exactly one record, a fresh key creating a distinct record) is what each
  scenario's `ideal` token encodes; the gold records the API's REAL token. Where
  they differ is a genuine QA finding about DummyJSON, not an agent bug.

A plan for one collection (the agent's output, and the reference) looks like:
  {
    "collection": "/products", "id_field": "id", "target_id": 1,
    "idempotent_requests": [
      {"label": "put",    "method": "PUT",    "path": "/products/1",
       "body": {"title": "idempotency-probe"}, "idempotency_key": "<KEY_A>", "replays": 3},
      {"label": "delete", "method": "DELETE", "path": "/products/1",
       "body": null,                           "idempotency_key": "<KEY_B>", "replays": 3}
    ],
    "create_request": {
      "label": "post", "method": "POST", "path": "/products/add",
      "body": {"title": "idempotency-probe"},
      "idempotency_key": "<KEY_C>", "second_key": "<KEY_D>", "replays": 3
    }
  }
"""
from __future__ import annotations

# Fixed literal idempotency keys (UUID-v4 shaped). The target ignores the header,
# so the value never perturbs an observed token; they are pinned literals purely so
# the debate-gated plan is byte-stable and reproducible across agents and the gold.
KEY_PUT = "a1111111-1111-4111-8111-111111111111"
KEY_DELETE = "b2222222-2222-4222-8222-222222222222"
KEY_POST = "c3333333-3333-4333-8333-333333333333"
KEY_POST_SECOND = "d4444444-4444-4444-8444-444444444444"

PROBE_BODY = {"title": "idempotency-probe"}
REPLAYS = 3
HEADER_NAME = "Idempotency-Key"

# Small delay between the replays of one request. A byte-for-byte idempotent endpoint
# returns identical bytes regardless of spacing; an endpoint that embeds wall-clock time
# (DummyJSON DELETE -> `deletedOn: new Date().toISOString()`, millisecond precision) only
# reveals that non-idempotency when consecutive replays land in different milliseconds.
# Without this spacing, three sub-millisecond replays can share a timestamp and a
# non-idempotent DELETE masquerades as idempotent. 6ms guarantees the ms tick advances,
# so the latent non-idempotency surfaces deterministically. PUT/POST carry no time field
# and stay byte-identical regardless. Keeps the gold token stable run-to-run.
INTER_REPLAY_DELAY_S = 0.006

# The full, ordered scenario set scored per collection (the fidelity denominator).
# `ideal` is the token a perfectly idempotent API would produce; gold records the
# REAL token DummyJSON produces. 9 scenarios x N collections = fidelity denominator.
SCENARIOS = [
    ("put_status_consistent",      "true"),   # CODE_1 == CODE_2 == CODE_3 on PUT replay
    ("put_body_byte_identical",    "true"),   # BODY_1 == BODY_2 == BODY_3 byte-for-byte
    ("put_single_record",          "true"),   # exactly one record at target_id (no triplication)
    ("delete_status_consistent",   "true"),   # CODE consistent on DELETE replay
    ("delete_body_byte_identical", "true"),   # BODY byte-identical on DELETE replay
    ("delete_single_record",       "true"),   # exactly one record at target_id (not three effects)
    ("post_status_consistent",     "true"),   # CODE consistent on POST replay (same key)
    ("post_body_byte_identical",   "true"),   # BODY byte-identical on POST replay (same key)
    ("post_new_key_distinct",      "true"),   # a FRESH key creates a DISTINCT record (real idem-create)
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# The endpoint test cases that count toward the headline Idempotency Compliance Rate.
# Per the task's own selection rule, idempotent endpoints = PUT and DELETE (POST is
# included only if it documents Idempotency-Key support; DummyJSON does not, so POST
# scenarios are informational and excluded from the compliance denominator).
COMPLIANCE_CASES = {
    "put": ["put_status_consistent", "put_body_byte_identical", "put_single_record"],
    "delete": ["delete_status_consistent", "delete_body_byte_identical", "delete_single_record"],
}


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one collection, derived deterministically
    from its config (collection, id_field, target_id). Identical structure to what
    a faithful agent must emit."""
    col = cfg["collection"]
    tid = cfg["target_id"]
    path = f"{col}/{tid}"
    return {
        "collection": col,
        "id_field": cfg.get("id_field", "id"),
        "target_id": tid,
        "idempotent_requests": [
            {"label": "put", "method": "PUT", "path": path,
             "body": dict(PROBE_BODY), "idempotency_key": KEY_PUT, "replays": REPLAYS},
            {"label": "delete", "method": "DELETE", "path": path,
             "body": None, "idempotency_key": KEY_DELETE, "replays": REPLAYS},
        ],
        "create_request": {
            "label": "post", "method": "POST", "path": f"{col}/add",
            "body": dict(PROBE_BODY), "idempotency_key": KEY_POST,
            "second_key": KEY_POST_SECOND, "replays": REPLAYS},
    }


def _all_equal(xs: list) -> bool:
    return len(xs) >= 1 and all(x == xs[0] for x in xs)


def evaluate(write_obs: dict, create_obs: dict, state: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    write_obs   : {"put":  {"codes":[c1,c2,c3], "bodies":[b1,b2,b3]},
                   "delete":{"codes":[...],      "bodies":[...]}}      (missing => not exercised)
    create_obs  : {"codes":[c1,c2,c3], "bodies":[b1,b2,b3],
                   "second": {"code": c, "body": b}}                  (missing => not exercised)
    state       : {"put_record_count": int|None, "delete_record_count": int|None}
                  record_count is how many records match target_id after the replays
                  (1 = exactly one, the idempotent expectation; >1 would be duplication).

    `bodies` are RAW response strings; equality is byte-for-byte string comparison,
    NOT semantic JSON equality (per the task). Returns {scenario: observed_token};
    "missing" marks a scenario whose request the agent never emitted.
    """
    obs: dict[str, str] = {}

    def status_tok(rec):
        if not rec:
            return "missing"
        codes = rec.get("codes") or []
        if not codes or any(c is None or c < 0 for c in codes):
            return "missing" if not codes else "false"
        return "true" if _all_equal(codes) else "false"

    def body_tok(rec):
        if not rec:
            return "missing"
        bodies = rec.get("bodies")
        if not bodies or any(b is None for b in bodies):
            return "missing" if not bodies else "false"
        return "true" if _all_equal(bodies) else "false"

    def single_tok(count):
        if count is None:
            return "missing"
        return "true" if count == 1 else "false"

    put, dele = write_obs.get("put"), write_obs.get("delete")
    obs["put_status_consistent"] = status_tok(put)
    obs["put_body_byte_identical"] = body_tok(put)
    obs["put_single_record"] = single_tok(state.get("put_record_count"))
    obs["delete_status_consistent"] = status_tok(dele)
    obs["delete_body_byte_identical"] = body_tok(dele)
    obs["delete_single_record"] = single_tok(state.get("delete_record_count"))

    obs["post_status_consistent"] = status_tok(create_obs)
    obs["post_body_byte_identical"] = body_tok(create_obs)

    # post_new_key_distinct: a fresh Idempotency-Key must create a DISTINCT record,
    # i.e. the second-key response differs from the first-key response. On an API with
    # no idempotency-key layer the two are identical => "false".
    if not create_obs or "second" not in create_obs or not create_obs.get("bodies"):
        obs["post_new_key_distinct"] = "missing"
    else:
        first = create_obs["bodies"][0]
        second = create_obs["second"].get("body")
        if first is None or second is None:
            obs["post_new_key_distinct"] = "missing"
        else:
            obs["post_new_key_distinct"] = "true" if second != first else "false"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized idempotency contract for this scenario?"""
    return observed_token == IDEAL[scenario]


def compliance(observed_by_collection: dict) -> dict:
    """The headline Idempotency Compliance Rate over idempotent endpoint cases
    (PUT, DELETE) across all collections. A case PASSES iff all of its compliance
    sub-scenarios observed "true" (status consistent AND body byte-identical AND
    single record).

    observed_by_collection: {collection: {scenario: observed_token}}
    Returns {passing, total, rate_pct, cases:[...]}.
    """
    cases = []
    passing = total = 0
    for col, obs in observed_by_collection.items():
        for case, subs in COMPLIANCE_CASES.items():
            toks = [obs.get(s, "missing") for s in subs]
            ok = all(t == "true" for t in toks)
            cases.append({"collection": col, "endpoint_case": case,
                          "sub_tokens": dict(zip(subs, toks)), "pass": ok})
            total += 1
            passing += 1 if ok else 0
    rate = round(100.0 * passing / total, 2) if total else 0.0
    return {"passing": passing, "total": total, "rate_pct": rate, "cases": cases}
