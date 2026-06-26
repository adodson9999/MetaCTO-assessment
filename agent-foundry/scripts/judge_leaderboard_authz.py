#!/usr/bin/env python3
"""Authorization-workflow leaderboard. Reads the four agents' emitted metric JSONs
for a run (results/authz/runs/<id>/*.json), applies judge/metric_authz.json, and
updates results/authz/leaderboard.{json,md} — tracking results over time.

Usage:
    python judge_leaderboard_authz.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    metric = _load(ws / "judge" / "metric_authz.json", {})
    metric_name = metric.get("metric_name", "authorization_test_fidelity")
    direction = metric.get("direction", "higher_is_better")
    better = (lambda x, y: x > y) if direction == "higher_is_better" else (lambda x, y: x < y)

    run_dir = ws / "results" / "authz" / "runs" / a.run_id
    this_run = {}
    headline = {}
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        d = _load(jf, {})
        if "metric_value" in d:
            this_run[d.get("agent", jf.stem)] = float(d["metric_value"])
            headline[d.get("agent", jf.stem)] = d.get("access_control_accuracy_rate_pct")

    lb_path = ws / "results" / "authz" / "leaderboard.json"
    lb = _load(lb_path, {"metric_name": metric_name, "direction": direction,
                         "agents": {}, "runs": []})
    lb["metric_name"] = metric_name
    lb["direction"] = direction

    for agent, val in this_run.items():
        rec = lb["agents"].get(agent, {"best": None, "runs": 0})
        rec["runs"] += 1
        rec["last"] = val
        if rec["best"] is None or better(val, rec["best"]):
            rec["best"] = val
        lb["agents"][agent] = rec

    lb["runs"].append({"run_id": a.run_id,
                       "ts": datetime.now(timezone.utc).isoformat(),
                       "values": this_run, "headline_accuracy": headline})
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb_path.write_text(json.dumps(lb, indent=2))

    ranked = sorted(this_run.items(), key=lambda kv: kv[1],
                    reverse=(direction == "higher_is_better"))

    md = [f"# Authorization Leaderboard — {metric_name} ({direction})",
          f"Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "Headline = Access Control Accuracy Rate (property of the target API).",
          "Rank key = Authorization-Test Fidelity vs gold (framework test quality).",
          "",
          "| Rank | Agent | Fidelity (this run) | Best | Accuracy% | Runs |",
          "|------|-------|---------------------|------|-----------|------|"]
    for i, (agent, val) in enumerate(ranked, 1):
        rec = lb["agents"][agent]
        acc = headline.get(agent)
        md.append(f"| {i} | {agent} | {val:g} | {rec['best']:g} | {acc} | {rec['runs']} |")
    (ws / "results" / "authz" / "leaderboard.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    if not this_run:
        print("\n[warn] no agent emitted a metric_value for this run.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
