#!/usr/bin/env python3
"""Judge scorer — fidelity layer for the validate-header-propagation task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded scenarios for a run, compares them to
data/validate-header-propagation/gold.json under the contract in
judge/validate-header-propagation/metric.json, computes Header-Propagation-Test
Fidelity, and writes that number back as each agent's metric_value. Then
scripts/judge_score.py ranks and updates the leaderboard.

Usage:
    python judge/validate-header-propagation/score.py --workspace . --run-id <id>
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
    """(endpoint, scenario) -> gold observed_token, over every gold scenario."""
    gold = _load(ws / "data" / "validate-header-propagation" / "gold.json", {"endpoints": []})
    truth = {}
    for ep in gold["endpoints"]:
        for s in ep["scenarios"]:
            truth[(ep["endpoint"], s["scenario"])] = s["observed_token"]
    return truth


def agent_observed(cases_doc: dict) -> dict:
    """(endpoint, scenario) -> observed_token, for scenarios the agent exercised."""
    obs = {}
    for ep in cases_doc.get("endpoints", []):
        for s in ep.get("scenarios", []):
            obs[(ep["endpoint"], s["scenario"])] = s.get("observed_token")
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
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"endpoints": []})
        if "endpoints" not in cases_doc:
            continue  # not a header-propagation run (e.g. a different task's emit)
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        meta["metric_name"] = "header_propagation_test_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_scenarios"] = covered
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, denom, covered,
                     cases_doc.get("header_propagation_rate_pct")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Header-Propagation-Test Fidelity (denominator = {denom} gold scenarios)")
    print(f"{'agent':40} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'propag%':>8}")
    for agent, fid, m, d, cov, rate in rows:
        print(f"{agent:40} {fid:>9} {m:>8} {cov:>9} {str(rate):>8}")
    if not rows:
        print("[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
