"""Canonical scenario structure for the API test-bulk-operation-endpoints task.

ONE definition of the bulk test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-bulk-operation-endpoints/build_gold.py), and
  - the harness (agents/common/bulk.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold set on the
same scenario-key scheme so the judge can compare them field-for-field.

Target reality (standing owner decision: DummyJSON is left untouched):
  - DummyJSON exposes NO bulk/batch endpoints (no 207, no per-item array, no
    persistence), so the 207 + per-item-status + DB-count-delta assertions cannot
    run against it. The bulk test therefore targets a separate, purpose-built,
    local, air-gapped, spec-conformant bulk endpoint (tools/bulk_target/app.py).

`ideal` is the token a correct, spec-conformant bulk endpoint produces. The gold
records the REAL observed token. Where they differ is a genuine QA finding about the
target, not an agent bug. (Empirically the local target is spec-conformant, so the
gold equals the ideal — itself a valid QA result: 207, 8x2xx + 2x400 naming the
offending fields, DB delta exactly 8, all-invalid inserts 0, oversize rejected 413.)

A plan for one run (the agent's output, and the reference) looks like:
  {
    "endpoint": "/bulk/products",
    "max_batch_size": 100,
    "required_fields": [
      {"name": "title", "type": "string"},
      {"name": "price", "type": "number"},
      {"name": "category", "type": "string"}
    ],
    "valid_item_template": {"title": "Bulk Item [N]", "price": 9.99, "category": "test"},
    "valid_count": 8,
    "missing_field": "category",
    "wrongtype_field": "title",
    "wrongtype_value": 12345,
    "oversize_count": 101,
    "expected_batch_status": 207,
    "expected_valid_item_status": 201,
    "expected_invalid_item_status": 400,
    "expected_oversize_status": 413,
    "expected_db_delta": 8
  }
"""
from __future__ import annotations

import json

# The full, ordered scenario set scored per run (the fidelity metric denominator).
# Each scenario's `ideal` is what a correct, spec-conformant bulk endpoint produces.
SCENARIOS = [
    # ---- mixed batch: 8 valid + 1 missing-required + 1 wrong-type ----
    ("mixed_batch_status_207",   "true"),   # top-level response code == 207
    ("mixed_results_len_10",     "10"),     # per-item results array has 10 entries
    ("mixed_valid_2xx_count",    "8"),      # items 1..8 with per-item status in {200,201}
    ("mixed_invalid_400_count",  "2"),      # items 9,10 with per-item status 400
    ("mixed_missing_field_named", "true"),  # item 9 error names the missing field
    ("mixed_wrongtype_field_named", "true"),# item 10 error names the wrong-type field
    ("mixed_db_delta_8",         "8"),      # COUNT_AFTER - COUNT_BEFORE == 8
    # ---- all-invalid batch ----
    ("allinvalid_status_207",    "true"),   # response code == 207 (documented all-invalid behavior)
    ("allinvalid_all_400",       "true"),   # every one of the 10 per-item statuses == 400
    ("allinvalid_db_delta_0",    "0"),      # DB count does not increase
    # ---- oversize batch (> max_batch_size) ----
    ("oversize_rejected",        "413"),    # whole batch rejected with 413 (or 400)
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# Tokens accepted as "rejected" for the oversize scenario (documented behavior is
# 413 Payload Too Large; 400 Bad Request is the documented alternative).
OVERSIZE_OK_TOKENS = {"413", "400"}


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan, derived deterministically from the spec config.
    Used by the gold builder; an agent that constructs the same plan reproduces the
    gold observations."""
    return {
        "endpoint": cfg["endpoint"],
        "max_batch_size": cfg["max_batch_size"],
        "required_fields": [dict(f) for f in cfg["required_fields"]],
        "valid_item_template": dict(cfg["valid_item_template"]),
        "valid_count": cfg["valid_count"],
        "missing_field": cfg["missing_field"],
        "wrongtype_field": cfg["wrongtype_field"],
        "wrongtype_value": cfg["wrongtype_value"],
        "oversize_count": cfg["oversize_count"],
        "expected_batch_status": cfg.get("expected_batch_status", 207),
        "expected_valid_item_status": cfg.get("expected_valid_item_status", 201),
        "expected_invalid_item_status": cfg.get("expected_invalid_item_status", 400),
        "expected_oversize_status": cfg.get("expected_oversize_status", 413),
        "expected_db_delta": cfg.get("expected_db_delta", cfg["valid_count"]),
    }


def _materialize_valid(template: dict, n: int) -> list[dict]:
    """Expand the valid_item_template into n distinct valid items. The literal token
    [N] in any string value is replaced by the 1-based item number."""
    items = []
    for k in range(1, n + 1):
        item = {}
        for key, val in template.items():
            item[key] = val.replace("[N]", str(k)) if isinstance(val, str) else val
        items.append(item)
    return items


def build_mixed_batch(plan: dict) -> list[dict]:
    """The 10-item mixed batch: valid_count valid items, then one item missing the
    `missing_field`, then one item whose `wrongtype_field` is set to `wrongtype_value`
    (an integer where a string is expected)."""
    template = plan["valid_item_template"]
    n = int(plan["valid_count"])
    items = _materialize_valid(template, n)

    missing = _materialize_valid(template, n + 1)[-1]  # a fresh valid item, then break it
    missing.pop(plan["missing_field"], None)
    items.append(missing)

    wrong = _materialize_valid(template, n + 2)[-1]
    wrong[plan["wrongtype_field"]] = plan["wrongtype_value"]
    items.append(wrong)
    return items


def build_all_invalid_batch(plan: dict) -> list[dict]:
    """Ten items, every one missing the `missing_field` (each independently invalid)."""
    template = plan["valid_item_template"]
    out = _materialize_valid(template, 10)
    for it in out:
        it.pop(plan["missing_field"], None)
    return out


def build_oversize_batch(plan: dict) -> list[dict]:
    """oversize_count valid items — one more than the endpoint's max batch size."""
    return _materialize_valid(plan["valid_item_template"], int(plan["oversize_count"]))


def _is_2xx(status) -> bool:
    return isinstance(status, int) and 200 <= status < 300


def evaluate(mixed_obs: dict, allinvalid_obs: dict, oversize_obs: dict, plan: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    mixed_obs / allinvalid_obs: {"batch_status": int, "results": [peritem,...],
                                 "db_before": int, "db_after": int}
    oversize_obs              : {"batch_status": int, "db_before": int, "db_after": int}

    Returns {scenario_label: observed_token}. A token of "missing" marks an
    observation the agent's plan never produced (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}
    valid_count = int(plan.get("valid_count", 8)) if isinstance(plan, dict) else 8
    missing_field = plan.get("missing_field") if isinstance(plan, dict) else None
    wrongtype_field = plan.get("wrongtype_field") if isinstance(plan, dict) else None

    # ---- mixed ----
    if not isinstance(mixed_obs, dict) or "batch_status" not in mixed_obs:
        for lbl in ("mixed_batch_status_207", "mixed_results_len_10",
                    "mixed_valid_2xx_count", "mixed_invalid_400_count",
                    "mixed_missing_field_named", "mixed_wrongtype_field_named",
                    "mixed_db_delta_8"):
            obs[lbl] = "missing"
    else:
        results = mixed_obs.get("results") or []
        obs["mixed_batch_status_207"] = "true" if mixed_obs.get("batch_status") == 207 else "false"
        obs["mixed_results_len_10"] = str(len(results))
        valid_part = results[:valid_count]
        invalid_part = results[valid_count:valid_count + 2]
        obs["mixed_valid_2xx_count"] = str(sum(1 for r in valid_part if _is_2xx(_status_of(r))))
        obs["mixed_invalid_400_count"] = str(sum(1 for r in invalid_part if _status_of(r) == 400))
        obs["mixed_missing_field_named"] = _field_named(
            results, valid_count, missing_field)
        obs["mixed_wrongtype_field_named"] = _field_named(
            results, valid_count + 1, wrongtype_field)
        delta = mixed_obs.get("db_after", 0) - mixed_obs.get("db_before", 0)
        obs["mixed_db_delta_8"] = str(delta)

    # ---- all-invalid ----
    if not isinstance(allinvalid_obs, dict) or "batch_status" not in allinvalid_obs:
        obs["allinvalid_status_207"] = "missing"
        obs["allinvalid_all_400"] = "missing"
        obs["allinvalid_db_delta_0"] = "missing"
    else:
        results = allinvalid_obs.get("results") or []
        obs["allinvalid_status_207"] = "true" if allinvalid_obs.get("batch_status") == 207 else "false"
        obs["allinvalid_all_400"] = (
            "true" if results and len(results) == 10 and all(_status_of(r) == 400 for r in results)
            else "false"
        )
        d = allinvalid_obs.get("db_after", 0) - allinvalid_obs.get("db_before", 0)
        obs["allinvalid_db_delta_0"] = str(d)

    # ---- oversize ----
    if not isinstance(oversize_obs, dict) or "batch_status" not in oversize_obs:
        obs["oversize_rejected"] = "missing"
    else:
        obs["oversize_rejected"] = str(oversize_obs.get("batch_status"))

    return obs


def _status_of(result) -> int | None:
    if isinstance(result, dict):
        s = result.get("status")
        return s if isinstance(s, int) else None
    return None


def _field_named(results: list, index: int, field: str | None) -> str:
    """Did the per-item result at `index` carry status 400 AND name `field` in its
    error message or fields list?"""
    if field is None or index >= len(results):
        return "false"
    r = results[index]
    if not isinstance(r, dict) or r.get("status") != 400:
        return "false"
    if field in (r.get("fields") or []):
        return "true"
    err = r.get("error")
    return "true" if isinstance(err, str) and field in err else "false"


def correct(scenario: str, observed_token: str) -> bool:
    """Did the target behave per the idealized bulk contract for this scenario?"""
    if scenario == "oversize_rejected":
        return observed_token in OVERSIZE_OK_TOKENS
    return observed_token == IDEAL[scenario]


def bulk_operation_accuracy(mixed_obs: dict, allinvalid_obs: dict,
                            oversize_obs: dict, plan: dict) -> dict:
    """Headline Bulk Operation Accuracy over the three bulk test cases.

    A bulk test case PASSES when its valid items return 2xx per-item status AND its
    invalid items return 400 per-item status AND the DB count delta equals the valid
    item count. (For all-invalid: valid count 0, so pass = all 400 + delta 0. For
    oversize: the whole batch is rejected before any item is processed, so pass =
    rejected with 413/400 + delta 0.)
    Returns {accuracy_pct, cases_passed, cases_total, per_case}.
    """
    valid_count = int(plan.get("valid_count", 8)) if isinstance(plan, dict) else 8
    per_case = {}

    # TC1 mixed
    mok = False
    if isinstance(mixed_obs, dict) and "batch_status" in mixed_obs:
        results = mixed_obs.get("results") or []
        valid_part = results[:valid_count]
        invalid_part = results[valid_count:valid_count + 2]
        delta = mixed_obs.get("db_after", 0) - mixed_obs.get("db_before", 0)
        mok = (mixed_obs.get("batch_status") == 207
               and len(valid_part) == valid_count
               and all(_is_2xx(_status_of(r)) for r in valid_part)
               and len(invalid_part) == 2
               and all(_status_of(r) == 400 for r in invalid_part)
               and delta == valid_count)
    per_case["mixed"] = mok

    # TC2 all-invalid (valid count 0)
    aok = False
    if isinstance(allinvalid_obs, dict) and "batch_status" in allinvalid_obs:
        results = allinvalid_obs.get("results") or []
        d = allinvalid_obs.get("db_after", 0) - allinvalid_obs.get("db_before", 0)
        aok = (len(results) == 10
               and all(_status_of(r) == 400 for r in results)
               and d == 0)
    per_case["all_invalid"] = aok

    # TC3 oversize (valid count 0 persisted)
    ook = False
    if isinstance(oversize_obs, dict) and "batch_status" in oversize_obs:
        d = oversize_obs.get("db_after", 0) - oversize_obs.get("db_before", 0)
        ook = (str(oversize_obs.get("batch_status")) in OVERSIZE_OK_TOKENS and d == 0)
    per_case["oversize"] = ook

    passed = sum(1 for v in per_case.values() if v)
    total = len(per_case)
    pct = round(100.0 * passed / total, 2) if total else 0.0
    return {"accuracy_pct": pct, "cases_passed": passed, "cases_total": total,
            "per_case": per_case}
