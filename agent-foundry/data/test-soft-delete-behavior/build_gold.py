#!/usr/bin/env python3
"""Deterministic GOLD reference for the api-tester / test-soft-delete-behavior task.
NOT one of the four agents — it is the canonical truth the judge scores fidelity against.

It builds the canonical CORRECT soft-delete plan (softdelete_spec.build_reference_plan)
and executes it through the SAME shared execution path the agents use
(agents/common/softdelete._exec_plan) — case_count create->delete->verify lifecycles
against the local soft-delete target, with a DIRECT SQLite query for the surviving row /
deleted_at / is_deleted / within-10s check. It records the REAL observed token per
scenario, so an agent that constructs the same plan reproduces these tokens exactly.

DummyJSON is never used and never modified. Every request goes to the local,
purpose-built soft-delete target (tools/softdelete_target/app.py).

Rebuild any time (target must be up):
    FORGE_BASE_URL=http://127.0.0.1:8950 \
    python data/test-soft-delete-behavior/build_gold.py
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

import softdelete  # noqa: E402
import softdelete_spec  # noqa: E402

OUT_DIR = WS / "data" / "test-soft-delete-behavior"


def main() -> int:
    cfg = softdelete.run_cfg()
    case_count = cfg.get("case_count", softdelete_spec.CASE_COUNT)
    plan = softdelete_spec.build_reference_plan(cfg)

    case_results, reqlog = softdelete._exec_plan("gold", cfg, plan)
    observed = softdelete_spec.evaluate(case_results, case_count)
    ideal = softdelete_spec.ideal_for(case_count)
    headline = softdelete_spec.success_rate(case_results, case_count)

    scenarios = []
    total = correct = 0
    for label in softdelete_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = softdelete_spec.correct(label, tok, ideal)
        scenarios.append({"scenario": label, "ideal": ideal[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    gold = {
        "task": "api-tester / test-soft-delete-behavior",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "target": cfg["base_url"], "case_count": case_count,
        "reference_plan": plan,
        "soft_delete_correctness_rate_pct": headline["rate_pct"],
        "correct_cases": headline["correct_cases"], "total_cases": headline["total_cases"],
        "scenarios_total": total, "scenarios_api_correct": correct,
        "request_log": reqlog,
        "scenarios": scenarios,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gold.json").write_text(json.dumps(gold, indent=2))
    (OUT_DIR / "gold").mkdir(exist_ok=True)
    for s in scenarios:
        (OUT_DIR / "gold" / f"{s['scenario']}.json").write_text(json.dumps(s, indent=2))

    print("GOLD built — api-tester / test-soft-delete-behavior")
    print(f"  target     : {cfg['base_url']}{plan['create']['endpoint']}")
    print(f"  case_count : {case_count}")
    print(f"  Soft Delete Correctness Rate = {headline['rate_pct']}% "
          f"(correct_cases={headline['correct_cases']}/{headline['total_cases']})")
    print(f"  scenarios api-correct = {correct}/{total}")
    for s in scenarios:
        mark = "ok " if s["api_correct"] else "DIFF"
        print(f"    [{mark}] {s['scenario']:30} ideal={s['ideal']:6} observed={s['observed_token']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
