#!/usr/bin/env python3
"""Judge scorer — fidelity layer for the pagination-behavior task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded scenarios for a run, compares them to
data/test-pagination-behavior/gold.json under the contract in
judge/test-pagination-behavior/metric.json, computes Pagination-Test Fidelity, and
writes that number back as each agent's metric_value. Then scripts/judge_score.py
ranks and updates the leaderboard.

Usage:
    python judge/test-pagination-behavior/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_truth(ws: Path) -> dict:
    """(collection, scenario) -> gold observed_token, over every gold scenario."""
    gold = _load(ws / "data" / "test-pagination-behavior" / "gold.json", {"collections": []})
    truth = {}
    for col in gold["collections"]:
        for s in col["scenarios"]:
            truth[(col["collection"], s["scenario"])] = s["observed_token"]
    return truth


def agent_observed(cases_doc: dict) -> dict:
    """(collection, scenario) -> observed_token, for scenarios the agent exercised."""
    obs = {}
    for col in cases_doc.get("collections", []):
        for s in col.get("scenarios", []):
            obs[(col["collection"], s["scenario"])] = s.get("observed_token")
    return obs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    truth = gold_truth(ws)
    denom = len(truth)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"collections": []})
        if "collections" not in cases_doc:
            continue  # not a pagination run (e.g. a different task's emit)
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        meta["metric_name"] = "pagination_test_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_scenarios"] = covered
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, denom, covered,
                     cases_doc.get("pagination_correctness_rate_pct")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Pagination-Test Fidelity (denominator = {denom} gold scenarios)")
    print(f"{'agent':36} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'correct%':>9}")
    for agent, fid, m, d, cov, rej in rows:
        print(f"{agent:36} {fid:>9} {m:>8} {cov:>9} {str(rej):>9}")
    if not rows:
        print("[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
