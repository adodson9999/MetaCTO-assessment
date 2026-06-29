"""Canonical scenario structure for the API concurrent-request-handling task.

ONE definition of the concurrency test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-concurrent-request-handling/build_gold.py), and
  - the harness (agents/common/concurrency.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold set on the
same scenario-key scheme so the judge can compare them field-for-field.

Target reality (Phase-2 owner decision: DummyJSON is left untouched):
  - READ test  -> DummyJSON GET /products/1 (read-only). A correct, concurrency-safe
    server returns 50x HTTP 200 with 50 byte-identical bodies and zero 500s.
  - WRITE test -> a separate, purpose-built, local, air-gapped SQLite-backed endpoint
    (tools/concurrency_target/app.py). DummyJSON cannot persist (addNewProduct echoes
    a constant id and writes nothing), so the count-delta / dedup assertions are run
    against this real persistence layer instead.

`ideal` is the token a correct, concurrency-safe system produces. The gold records
the REAL observed token. Where they differ is a genuine QA finding about the target,
not an agent bug. (Empirically, both targets handle 50-way concurrency correctly, so
the gold equals the ideal here — itself a valid QA result: no lost/duplicate writes,
no partial reads.)

A plan for one run (the agent's output, and the reference) looks like:
  {
    "read": {
      "label": "concurrent_read", "method": "GET", "endpoint": "/products/1",
      "concurrency": 50, "expected_status": 200, "assert_identical_bodies": true
    },
    "write": {
      "label": "concurrent_write", "method": "POST", "endpoint": "/records",
      "concurrency": 50, "expected_status": 201,
      "test_id_field": "test_id", "test_id_template": "concurrent-test-[VU_ID]",
      "vu_start": 1, "vu_end": 50,
      "payload_fields": {"source": "concurrent-handling-test"},
      "assert_count_delta": 50, "assert_zero_duplicates": true, "assert_zero_missing": true
    },
    "assert_zero_500": true
  }
"""
from __future__ import annotations

# Concurrency level for both tests (the task fixes this at 50).
CONCURRENCY = 50

# The full, ordered scenario set scored per run (the fidelity metric denominator).
# Each scenario's `ideal` is what a correct, concurrency-safe target produces.
SCENARIOS = [
    ("read_all_status_200",      "true"),   # all 50 GETs returned 200
    ("read_all_bodies_identical", "true"),   # all 50 response bodies JSON-equal
    ("read_zero_500",            "true"),   # no 500 in the read test
    ("read_success_count",       "50"),     # count of 200 responses
    ("write_all_status_201",     "true"),   # all 50 POSTs returned 201
    ("write_count_delta",        "50"),     # COUNT_AFTER - COUNT_BEFORE
    ("write_zero_duplicates",    "true"),   # each test_id present exactly once
    ("write_zero_missing",       "true"),   # all 50 expected test_ids present
    ("write_zero_500",           "true"),   # no 500 in the write test
    ("write_success_count",      "50"),     # count of 201 responses
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan, derived deterministically from the spec config.
    Used by the gold builder; an agent that constructs the same plan reproduces
    the gold observations."""
    n = cfg.get("concurrency", CONCURRENCY)
    return {
        "read": {
            "label": "concurrent_read",
            "method": "GET",
            "endpoint": cfg["read_endpoint"],
            "concurrency": n,
            "expected_status": cfg.get("read_expected_status", 200),
            "assert_identical_bodies": True,
        },
        "write": {
            "label": "concurrent_write",
            "method": "POST",
            "endpoint": cfg["write_endpoint"],
            "concurrency": n,
            "expected_status": cfg.get("write_expected_status", 201),
            "test_id_field": cfg.get("test_id_field", "test_id"),
            "test_id_template": cfg.get("test_id_template", "concurrent-test-[VU_ID]"),
            "vu_start": 1,
            "vu_end": n,
            "payload_fields": {"source": "concurrent-handling-test"},
            "assert_count_delta": n,
            "assert_zero_duplicates": True,
            "assert_zero_missing": True,
        },
        "assert_zero_500": True,
    }


def materialize_test_ids(template: str, vu_start: int, vu_end: int) -> list[str]:
    """Expand a test_id template ('concurrent-test-[VU_ID]') into one id per VU.
    The literal token '[VU_ID]' is replaced by the VU number 1..N."""
    return [template.replace("[VU_ID]", str(vu)) for vu in range(vu_start, vu_end + 1)]


def evaluate(read_obs: dict, write_obs: dict, db_obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    read_obs : {"statuses": [int,...], "bodies": [json|None,...], "n": int}
    write_obs: {"statuses": [int,...], "n": int}
    db_obs   : {"count_before": int, "count_after": int,
                "expected_test_ids": [str,...], "present_test_ids": [str,...],
                "duplicate_test_ids": [str,...]}

    Returns {scenario_label: observed_token}. A token of "missing" marks an
    observation the agent's plan never produced (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}

    # ---- READ ----
    r_status = read_obs.get("statuses") if isinstance(read_obs, dict) else None
    r_bodies = read_obs.get("bodies") if isinstance(read_obs, dict) else None
    r_n = read_obs.get("n") if isinstance(read_obs, dict) else 0
    if r_status is None:
        obs["read_all_status_200"] = "missing"
        obs["read_success_count"] = "missing"
        obs["read_zero_500"] = "missing"
    else:
        obs["read_all_status_200"] = (
            "true" if r_n and len(r_status) == r_n and all(s == 200 for s in r_status) else "false"
        )
        obs["read_success_count"] = str(sum(1 for s in r_status if s == 200))
        obs["read_zero_500"] = "true" if all(s != 500 for s in r_status) else "false"
    if r_bodies is None:
        obs["read_all_bodies_identical"] = "missing"
    else:
        norm = [None if b is None else _canon(b) for b in r_bodies]
        obs["read_all_bodies_identical"] = (
            "true"
            if r_n and len(norm) == r_n and all(b is not None for b in norm) and len(set(norm)) == 1
            else "false"
        )

    # ---- WRITE (HTTP layer) ----
    w_status = write_obs.get("statuses") if isinstance(write_obs, dict) else None
    w_n = write_obs.get("n") if isinstance(write_obs, dict) else 0
    if w_status is None:
        obs["write_all_status_201"] = "missing"
        obs["write_success_count"] = "missing"
        obs["write_zero_500"] = "missing"
    else:
        obs["write_all_status_201"] = (
            "true" if w_n and len(w_status) == w_n and all(s == 201 for s in w_status) else "false"
        )
        obs["write_success_count"] = str(sum(1 for s in w_status if s == 201))
        obs["write_zero_500"] = "true" if all(s != 500 for s in w_status) else "false"

    # ---- WRITE (DB layer, direct query) ----
    if not isinstance(db_obs, dict) or "count_after" not in db_obs:
        obs["write_count_delta"] = "missing"
        obs["write_zero_duplicates"] = "missing"
        obs["write_zero_missing"] = "missing"
    else:
        delta = db_obs.get("count_after", 0) - db_obs.get("count_before", 0)
        obs["write_count_delta"] = str(delta)
        dups = db_obs.get("duplicate_test_ids", [])
        obs["write_zero_duplicates"] = "true" if not dups else "false"
        expected = set(db_obs.get("expected_test_ids", []))
        present = set(db_obs.get("present_test_ids", []))
        obs["write_zero_missing"] = "true" if expected and expected.issubset(present) else "false"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the target behave per the idealized concurrency contract for this scenario?"""
    return observed_token == IDEAL[scenario]


def success_rate(read_obs: dict, write_obs: dict, db_obs: dict) -> dict:
    """Headline Concurrent Request Success Rate over the 100 sent requests.

    A READ request is correct when it returns 200 AND its body equals the modal
    (most common) body — a partial/torn read would diverge. A WRITE request is
    correct when it returns 201 AND its materialized test_id is present in the DB
    exactly once (not dropped, not duplicated). 500s are never correct.
    Returns {rate_pct, read_correct, write_correct, total}.
    """
    r_status = read_obs.get("statuses", []) or []
    r_bodies = read_obs.get("bodies", []) or []
    canon = [None if b is None else _canon(b) for b in r_bodies]
    modal = _modal(canon)
    read_correct = sum(
        1 for i, s in enumerate(r_status)
        if s == 200 and i < len(canon) and canon[i] is not None and canon[i] == modal
    )

    w_status = write_obs.get("statuses", []) or []
    present = list(db_obs.get("present_test_ids", []))
    dups = set(db_obs.get("duplicate_test_ids", []))
    present_counts: dict[str, int] = {}
    for t in present:
        present_counts[t] = present_counts.get(t, 0) + 1
    materialized = list(db_obs.get("materialized_test_ids", []))
    write_correct = 0
    for i, s in enumerate(w_status):
        tid = materialized[i] if i < len(materialized) else None
        if s == 201 and tid is not None and present_counts.get(tid, 0) == 1 and tid not in dups:
            write_correct += 1

    total = read_obs.get("n", 0) + write_obs.get("n", 0)
    rate = round(100.0 * (read_correct + write_correct) / total, 2) if total else 0.0
    return {"rate_pct": rate, "read_correct": read_correct,
            "write_correct": write_correct, "total": total}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _canon(body) -> str | None:
    """Canonical, order-independent JSON string for identity comparison."""
    import json
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"))
    except Exception:  # noqa
        return None


def _modal(items: list):
    counts: dict = {}
    for it in items:
        if it is None:
            continue
        counts[it] = counts.get(it, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]
