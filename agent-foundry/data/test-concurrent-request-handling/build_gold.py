#!/usr/bin/env python3
"""Deterministic GOLD reference for the api-tester / test-concurrent-request-handling
task. NOT one of the four agents — it is the canonical truth the judge scores
fidelity against.

It builds the canonical CORRECT concurrency plan (concurrency_spec.build_reference_plan)
and executes it through the SAME shared execution path the agents use
(agents/common/concurrency._exec_plan) — N simultaneous GETs to the read-only
DummyJSON read endpoint + N simultaneous POSTs to the local SQLite write target,
then a DIRECT SQLite query for the count delta / duplicates / missing. It records the
REAL observed token per scenario, so an agent that constructs the same plan
reproduces these tokens exactly.

DummyJSON is never modified: the read leg is GET-only. Only the separate, local,
purpose-built SQLite target is written to.

Rebuild any time (targets must be up):
    FORGE_READ_BASE_URL=http://localhost:8899 \
    FORGE_WRITE_BASE_URL=http://127.0.0.1:8910 \
    python data/test-concurrent-request-handling/build_gold.py
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

import concurrency  # noqa: E402
import concurrency_spec  # noqa: E402

OUT_DIR = WS / "data" / "test-concurrent-request-handling"


def main() -> int:
    cfg = concurrency.run_cfg()
    plan = concurrency_spec.build_reference_plan(cfg)

    read_obs, write_obs, db_obs, reqlog = concurrency._exec_plan("gold", cfg, plan)
    observed = concurrency_spec.evaluate(read_obs, write_obs, db_obs)
    headline = concurrency_spec.success_rate(read_obs, write_obs, db_obs)

    scenarios = []
    total = correct = 0
    for label in concurrency_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = concurrency_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": concurrency_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    gold = {
        "task": "api-tester / test-concurrent-request-handling",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "read_target": cfg["read_base_url"], "write_target": cfg["write_base_url"],
        "concurrency": cfg["concurrency"],
        "reference_plan": plan,
        "concurrent_request_success_rate_pct": headline["rate_pct"],
        "read_correct": headline["read_correct"], "write_correct": headline["write_correct"],
        "requests_total": headline["total"],
        "db_count_delta": (db_obs.get("count_after", 0) - db_obs.get("count_before", 0))
        if db_obs else None,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "request_log": reqlog,
        "scenarios": scenarios,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gold.json").write_text(json.dumps(gold, indent=2))
    (OUT_DIR / "gold").mkdir(exist_ok=True)
    for s in scenarios:
        (OUT_DIR / "gold" / f"{s['scenario']}.json").write_text(json.dumps(s, indent=2))

    print("GOLD built — api-tester / test-concurrent-request-handling")
    print(f"  read target : {cfg['read_base_url']}{plan['read']['endpoint']}")
    print(f"  write target: {cfg['write_base_url']}{plan['write']['endpoint']}")
    print(f"  Concurrent Request Success Rate = {headline['rate_pct']}% "
          f"(read_ok={headline['read_correct']}/{cfg['concurrency']}, "
          f"write_ok={headline['write_correct']}/{cfg['concurrency']})")
    print(f"  DB count delta = {gold['db_count_delta']} (expected {cfg['concurrency']})")
    print(f"  scenarios api-correct = {correct}/{total}")
    for s in scenarios:
        mark = "ok " if s["api_correct"] else "DIFF"
        print(f"    [{mark}] {s['scenario']:28} ideal={s['ideal']:6} observed={s['observed_token']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
