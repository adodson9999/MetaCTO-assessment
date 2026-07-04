#!/usr/bin/env python3
"""Judge scorer — fidelity layer for the soft-delete-behavior task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded scenarios for a run, compares them to
data/test-soft-delete-behavior/gold.json under the contract in
judge/test-soft-delete-behavior/metric.json, computes Soft-Delete-Test Fidelity, and
writes that number back as each agent's metric_value. Then scripts/judge_score.py ranks
and updates the leaderboard.

Usage:
    python judge/test-soft-delete-behavior/score.py --workspace . --run-id <id>
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
    """scenario -> gold observed_token, over every gold scenario."""
    gold = _load(ws / "data" / "test-soft-delete-behavior" / "gold.json",
                 {"scenarios": []})
    return {s["scenario"]: s["observed_token"] for s in gold.get("scenarios", [])}


def agent_observed(cases_doc: dict) -> dict:
    """scenario -> observed_token, for scenarios the agent exercised."""
    return {s["scenario"]: s.get("observed_token")
            for s in cases_doc.get("scenarios", [])}


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
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "scenarios" not in cases_doc or "soft_delete_correctness_rate_pct" not in cases_doc:
            continue  # not a soft-delete run (e.g. a different task's emit)
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        meta["metric_name"] = "soft_delete_test_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_scenarios"] = covered
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, covered,
                     cases_doc.get("soft_delete_correctness_rate_pct"),
                     cases_doc.get("correct_cases")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Soft-Delete-Test Fidelity (denominator = {denom} gold scenarios)")
    print(f"{'agent':40} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'correct%':>9} {'cases_ok':>9}")
    for agent, fid, m, cov, rate, ok in rows:
        print(f"{agent:40} {fid:>9} {m:>8} {cov:>9} {str(rate):>9} {str(ok):>9}")
    if not rows:
        print("[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
