#!/usr/bin/env python3
"""Judge scorer (auth-flow) — fidelity layer.

The agents emit blind test plans (they never see the gold). This step reads each
agent's executed cases for a run, compares them to data/auth_gold.json under the
contract in judge/auth_metric.json, computes Auth-Flow Fidelity, and writes that
number back as each agent's metric_value. Then scripts/judge_score.py ranks and
updates the leaderboard.

Usage:
    python judge/auth_score.py --workspace . --run-id <id>
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


def gold_truth(ws: Path) -> tuple[dict, set]:
    """Return (executed truth {(scheme,label)->actual_class}, not_applicable item set)."""
    gold = _load(ws / "data" / "auth_gold.json", {"cases": [], "summary": {}})
    exec_truth = {(c["scheme"], c["label"]): c["actual_class"] for c in gold.get("cases", [])}
    na_items = {x["item"] for x in gold.get("summary", {}).get("not_applicable", [])}
    return exec_truth, na_items


def agent_observed(cases_doc: dict) -> tuple[dict, set]:
    obs = {}
    for c in cases_doc.get("cases", []):
        if c.get("label") in (None, "_none_"):
            continue
        if c.get("actual_class") in (None, "none"):
            continue
        obs[(c["scheme"], c["label"])] = c["actual_class"]
    na = {x.get("item") for x in cases_doc.get("not_applicable_enumerated", [])
          if x.get("status") == "needs_to_be_built_and_tested"}
    return obs, na


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    exec_truth, na_truth = gold_truth(ws)
    denom = len(exec_truth) + len(na_truth)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"cases": []})
        obs_exec, obs_na = agent_observed(cases_doc)

        exec_matches = sum(1 for k, v in exec_truth.items() if obs_exec.get(k) == v)
        na_matches = sum(1 for item in na_truth if item in obs_na)
        matches = exec_matches + na_matches
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0

        meta["metric_name"] = "auth_flow_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["exec_matches"] = exec_matches
        meta["na_matches"] = na_matches
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, exec_matches, len(exec_truth),
                     na_matches, len(na_truth),
                     cases_doc.get("auth_flow_pass_rate_pct"),
                     cases_doc.get("false_acceptance_rate_pct")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Auth-Flow Fidelity (denominator = {denom}: "
          f"{len(exec_truth)} executed + {len(na_truth)} not_applicable)")
    print(f"{'agent':40} {'fidelity%':>9} {'exec':>7} {'na':>5} {'pass%':>6} {'FAR%':>6}")
    for agent, fid, em, et, nm, nt, pr, far in rows:
        print(f"{agent:40} {fid:>9} {f'{em}/{et}':>7} {f'{nm}/{nt}':>5} "
              f"{str(pr):>6} {str(far):>6}")
    if not rows:
        print("[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
