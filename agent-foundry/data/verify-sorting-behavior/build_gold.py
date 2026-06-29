#!/usr/bin/env python3
"""Gold-set builder for the API sorting-behavior testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the agents' input spec (sorting_spec.json), derives the canonical correct plan (20
seed records + six sort cases), seeds an ISOLATED in-process reference resource with
those records, sends every sort case to it with READ-ONLY GET calls, and records the
REAL observed behavior (status class + realized ordering / 400 message) per scenario.

Why a reference resource and NOT DummyJSON
------------------------------------------
This task is stateful: it must seed 20 records with known non-sequential names and
created_at timestamps two seconds apart, then verify ascending/descending ordering
and 400 handling for an invalid sort field and an invalid order direction. DummyJSON
is tested read-only by every other agent and MUST NEVER be modified — and it has no
created_at field, uses `sortBy` not `sort`, and ignores an unknown sort field with
200. So the idealized sort contract is exercised against the in-process reference
resource (agents/common/sortserver.py) instead. DummyJSON is never touched.

The recorded per-scenario observed token is the ground truth. Agents are later ranked
on how faithfully their own runs reproduce this table (correct seed + correct request
construction + ordering verification). The reference resource implements the idealized
contract exactly, so the gold tokens all match sorting_spec.IDEAL.

Outputs (all under data/verify-sorting-behavior/):
  - sorting_spec.json   the contract the agents are briefed from (INPUT)
  - gold.json           gold scenarios + empirical accuracy summary
Stdlib only. No network — the reference resource binds 127.0.0.1 on an ephemeral
port. Air-gapped.
"""
import json
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Shared scenario structure + reference server (one source of truth with the harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import sorting_spec  # noqa: E402
from sortserver import ReferenceServer  # noqa: E402


def get(base_url: str, path: str, params: dict):
    """Read-only GET against the reference resource. Returns (status, parsed|None)."""
    qs = urllib.parse.urlencode(params)
    url = f"{base_url}{path}?{qs}" if qs else f"{base_url}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa
            return e.code, None
    except Exception:  # noqa
        return -1, None


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes the sort contract
    WITHOUT the answer plan (no seed values, no case params)."""
    return {
        "title": "Idealized sort contract (authored for the sorting-behavior task)",
        "description": "One collection exposes a sort query parameter selecting a sortable field and "
                       "an order query parameter (asc|desc). The task seeds 20 records with distinct "
                       "non-sequential names and created_at timestamps two seconds apart, then verifies "
                       "ascending/descending ordering on name and created_at plus 400 handling for an "
                       "invalid sort field and an invalid order direction. Exercised against an isolated "
                       "in-process reference resource; DummyJSON is never seeded or modified.",
        "resource_path": "/resources",
        "list_field": "resources",
        "name_field": "name",
        "timestamp_field": "created_at",
        "sortable_fields": sorting_spec.SORTABLE_FIELDS,
        "valid_orders": sorting_spec.VALID_ORDERS,
        "seed_count": sorting_spec.SEED_COUNT,
        "seed_timestamp_step_seconds": sorting_spec.SEED_STEP_SECONDS,
    }


def main():
    (HERE / "sorting_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    plan = sorting_spec.build_reference_plan()
    name_field = plan["name_field"]
    timestamp_field = plan["timestamp_field"]

    with ReferenceServer(plan["seed"], name_field, timestamp_field) as server:
        base = server.base_url
        case_obs, reqlog = {}, {}
        for case in plan["sort_cases"]:
            status, body = get(base, plan["resource_path"], case["params"])
            records = body.get("resources") if (status == 200 and isinstance(body, dict)) else None
            message = body.get("message") if isinstance(body, dict) and status != 200 else None
            case_obs[case["label"]] = {"status": status, "records": records, "message": message}
            reqlog[case["label"]] = {"type": case.get("type"), "params": case["params"],
                                     "status": status,
                                     "returned_count": (len(records) if records is not None else None)}

    seed_meta = {"emitted": len(plan["seed"]),
                 "distinct": len({r["name"] for r in plan["seed"]})}
    observed = sorting_spec.evaluate(case_obs, seed_meta, name_field, timestamp_field)

    scenarios = []
    total = correct = 0
    findings = []
    for label in sorting_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = sorting_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": sorting_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0
        if not ok:
            findings.append({"scenario": label, "ideal": sorting_spec.IDEAL[label], "observed": tok})

    rate = round(100.0 * correct / total, 2) if total else None
    summary = {
        "target": "in-process reference resource (127.0.0.1, ephemeral port)",
        "scenarios": len(sorting_spec.SCENARIO_LABELS),
        "total_scenarios": total,
        "api_correct_scenarios": correct,
        "empirical_sorting_scenario_accuracy_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = the idealized reference resource's observed token per scenario. "
                "The resource is correct-by-construction (it sorts name case-insensitively and "
                "created_at as ISO-8601 instants, and returns 400 with a field-naming message on an "
                "unknown sort field and 400 on an out-of-enum order). DummyJSON is NOT used by this "
                "task because it cannot be seeded read-only and lacks a created_at field; seeding it "
                "would violate the read-only-target invariant.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "reference_plan": plan, "request_log": reqlog,
         "scenarios": scenarios}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
