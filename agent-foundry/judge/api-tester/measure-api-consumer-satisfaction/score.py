#!/usr/bin/env python3
"""Judge scorer — fidelity layer for the Measure-API-Consumer-Satisfaction task.

The agents emit blind plan-driven results (they never see the gold). This step reads each
agent's recorded scenarios for a run, compares them to the GOLD observed tokens for the
ranking dataset (current) in data/measure-api-consumer-satisfaction/gold.json under the
contract in judge/measure-api-consumer-satisfaction/metric.json, computes NPS-Measurement
Plan Fidelity, and writes that number back as each agent's metric_value. Then
scripts/judge_score.py ranks and updates the leaderboard.

Usage:
    python judge/measure-api-consumer-satisfaction/score.py --workspace . --run-id <id>
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


def gold_truth(ws: Path, dataset: str) -> dict:
    """scenario -> gold observed_token for the given dataset."""
    gold = _load(ws / "data" / "measure-api-consumer-satisfaction" / "gold.json",
                 {"datasets": []})
    for ds in gold.get("datasets", []):
        if ds.get("dataset") == dataset:
            return {s["scenario"]: s["observed_token"] for s in ds["scenarios"]}
    return {}


def agent_observed(cases_doc: dict) -> dict:
    return {s["scenario"]: s.get("observed_token")
            for s in cases_doc.get("scenarios", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--dataset", default="current")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    truth = gold_truth(ws, a.dataset)
    denom = len(truth)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "scenarios" not in cases_doc or "nps_score" not in cases_doc:
            continue  # not an nps run (e.g. a different task's emit)
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        meta["metric_name"] = "nps_measurement_plan_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_scenarios"] = covered
        meta["nps_score_reported"] = cases_doc.get("nps_score")
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, denom, covered, cases_doc.get("nps_score")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"NPS-Measurement Plan Fidelity (dataset={a.dataset}, denominator = {denom} gold scenarios)")
    print(f"{'agent':50} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'nps':>5}")
    for agent, fid, m, d, cov, nps in rows:
        print(f"{agent:50} {fid:>9} {m:>8} {cov:>9} {str(nps):>5}")
    if not rows:
        print("[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
