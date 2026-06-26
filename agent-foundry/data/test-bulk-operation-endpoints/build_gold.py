#!/usr/bin/env python3
"""Deterministic GOLD reference for the api-tester / test-bulk-operation-endpoints
task. NOT one of the four agents — it is the canonical truth the judge scores
fidelity against.

It builds the canonical CORRECT bulk plan (bulk_spec.build_reference_plan) and
executes it through the SAME shared execution path the agents use
(agents/common/bulk._exec_plan): a mixed 8-valid + 1-missing-required + 1-wrong-type
batch, an all-invalid batch, and an oversize batch, each POSTed to the local
spec-conformant bulk endpoint, with a DIRECT SQLite count before and after. It records
the REAL observed token per scenario, so an agent that constructs the same plan
reproduces these tokens exactly.

DummyJSON is never modified or even contacted: it has no bulk endpoints. Only the
separate, local, purpose-built bulk target is exercised.

Rebuild any time (target must be up):
    FORGE_BULK_BASE_URL=http://127.0.0.1:8920 \
    python data/test-bulk-operation-endpoints/build_gold.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", Path(__file__).resolve().parents[2])).resolve()
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ.setdefault("FORGE_RUN_ID", "gold")
sys.path.insert(0, str(WS / "agents" / "common"))

import bulk  # noqa: E402
import bulk_spec  # noqa: E402

OUT_DIR = WS / "data" / "test-bulk-operation-endpoints"


def main() -> int:
    cfg = bulk.run_cfg()
    plan = bulk_spec.build_reference_plan(cfg)

    mixed_obs, allinvalid_obs, oversize_obs, reqlog = bulk._exec_plan("gold", cfg, plan)
    observed = bulk_spec.evaluate(mixed_obs, allinvalid_obs, oversize_obs, plan)
    headline = bulk_spec.bulk_operation_accuracy(mixed_obs, allinvalid_obs, oversize_obs, plan)

    scenarios = []
    total = correct = 0
    for label in bulk_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = bulk_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": bulk_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    gold = {
        "task": "api-tester / test-bulk-operation-endpoints",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "target": cfg["base_url"], "endpoint": cfg["endpoint"],
        "max_batch_size": cfg["max_batch_size"], "valid_count": cfg["valid_count"],
        "reference_plan": plan,
        "bulk_operation_accuracy_pct": headline["accuracy_pct"],
        "cases_passed": headline["cases_passed"], "cases_total": headline["cases_total"],
        "per_case": headline["per_case"],
        "mixed_db_delta": (mixed_obs.get("db_after", 0) - mixed_obs.get("db_before", 0))
        if mixed_obs else None,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "request_log": reqlog,
        "scenarios": scenarios,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gold.json").write_text(json.dumps(gold, indent=2))
    (OUT_DIR / "gold").mkdir(exist_ok=True)
    for s in scenarios:
        (OUT_DIR / "gold" / f"{s['scenario']}.json").write_text(json.dumps(s, indent=2))

    print("GOLD built — api-tester / test-bulk-operation-endpoints")
    print(f"  target: {cfg['base_url']}{cfg['endpoint']}")
    print(f"  Bulk Operation Accuracy = {headline['accuracy_pct']}% "
          f"(cases_passed={headline['cases_passed']}/{headline['cases_total']}, "
          f"per_case={headline['per_case']})")
    print(f"  mixed DB count delta = {gold['mixed_db_delta']} (expected {cfg['valid_count']})")
    print(f"  scenarios api-correct = {correct}/{total}")
    for s in scenarios:
        mark = "ok " if s["api_correct"] else "DIFF"
        print(f"    [{mark}] {s['scenario']:30} ideal={s['ideal']:6} observed={s['observed_token']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
