#!/usr/bin/env python3
# Used by: shared — consolidates test cases across all agents.
"""Consolidate every agent's executed test cases for a run into one registry.

Each api-tester/general agent writes results/runs/<RUN_ID>/<agent>.cases.json with
its test records under an agent-specific key (cases / scenarios / collections /
endpoints / ...). This flattens all of them into a single test-case registry so
there is one canonical "test cases" artifact for the run. Deterministic, no LLM.
"""
from __future__ import annotations

import json
import glob
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ["FORGE_WORKSPACE"]).resolve()
RUN_ID = sys.argv[1]
RUN_DIR = WS / "results" / "runs" / RUN_ID

# Priority of keys that hold the agent's primary test-case list. First hit wins.
CASE_KEYS = ["cases", "scenarios", "case_results", "collections", "endpoints",
             "subjects", "flows", "routes", "channels", "topics", "services",
             "sprints", "pairs", "reports", "request_log"]

# Lists that are bookkeeping, never the primary case list.
SKIP_KEYS = {"missing_tc_ids", "missing_tc", "gen_errors", "structural_errors",
             "field_cells", "field_mismatches", "per_agent_spec",
             "not_applicable_enumerated", "builds_that_must_block_deployment",
             "runs_that_must_block_deployment"}


def pick_list(d: dict):
    for k in CASE_KEYS:
        v = d.get(k)
        if isinstance(v, list) and v:
            return k, v
    # fallback: richest non-skip list
    best = None
    for k, v in d.items():
        if k in SKIP_KEYS or not isinstance(v, list) or not v:
            continue
        if best is None or len(v) > len(best[1]):
            best = (k, v)
    return best if best else (None, [])


def main() -> None:
    registry = []
    per_agent = {}
    for f in sorted(glob.glob(str(RUN_DIR / "*.cases.json"))):
        agent = os.path.basename(f).replace(".cases.json", "")
        try:
            d = json.load(open(f))
        except Exception as e:  # noqa
            per_agent[agent] = {"error": str(e), "count": 0}
            continue
        if not isinstance(d, dict):
            d = {"_root": d}
        key, items = pick_list(d)
        metric_name = next((k for k in d if k.endswith("_pct") or k.endswith("_rate")
                            or k in ("nps_score",)), None)
        metric_value = d.get(metric_name) if metric_name else None
        for i, rec in enumerate(items, 1):
            registry.append({
                "tc_id": f"{agent}-{i}",
                "agent": agent,
                "source_key": key,
                "step_index": i,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "record": rec,
            })
        per_agent[agent] = {"source_key": key, "count": len(items),
                            "metric_name": metric_name, "metric_value": metric_value}

    out = RUN_DIR / "test-cases.json"
    out.write_text(json.dumps({
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_test_cases": len(registry),
        "agent_count": len(per_agent),
        "per_agent": per_agent,
        "test_cases": registry,
    }, indent=2))

    summary = RUN_DIR / "test-cases-summary.json"
    summary.write_text(json.dumps({
        "run_id": RUN_ID, "total_test_cases": len(registry),
        "agent_count": len(per_agent), "per_agent": per_agent}, indent=2))

    print(f"wrote {out}")
    print(f"total test cases: {len(registry)} across {len(per_agent)} agents")
    zero = [a for a, m in per_agent.items() if m.get("count", 0) == 0]
    if zero:
        print(f"agents with 0 cases ({len(zero)}): {', '.join(zero)}")


if __name__ == "__main__":
    main()
