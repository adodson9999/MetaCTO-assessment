#!/usr/bin/env python3
"""
Judge scorer. Reads the four agents' emitted metric JSONs for a run, applies the
metric contract (judge/metric.json), and updates the leaderboard — tracking
results over time (best-so-far per agent, run history).

The judge *defines* the metric elsewhere (see references/judge.md); this script
is the deterministic measure+rank+render step.

Usage:
    python judge_score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    metric = _load(ws / "judge" / "metric.json", {})
    metric_name = metric.get("metric_name", "metric")
    direction = metric.get("direction", "higher_is_better")
    better = (lambda x, y: x > y) if direction == "higher_is_better" else (lambda x, y: x < y)

    run_dir = ws / "results" / "runs" / a.run_id
    this_run = {}
    for jf in sorted(run_dir.glob("*.json")):
        d = _load(jf, {})
        if "metric_value" in d:
            this_run[d.get("agent", jf.stem)] = float(d["metric_value"])

    lb_path = ws / "results" / "leaderboard.json"
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
                       "values": this_run})
    lb_path.write_text(json.dumps(lb, indent=2))

    # rank by this run's value (fallback to best)
    ranked = sorted(this_run.items(), key=lambda kv: kv[1],
                    reverse=(direction == "higher_is_better"))

    md = [f"# Leaderboard — {metric_name} ({direction})",
          f"Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "| Rank | Agent | This run | Best so far | Runs |",
          "|------|-------|----------|-------------|------|"]
    for i, (agent, val) in enumerate(ranked, 1):
        rec = lb["agents"][agent]
        md.append(f"| {i} | {agent} | {val:g} | {rec['best']:g} | {rec['runs']} |")
    (ws / "results" / "leaderboard.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    if not this_run:
        print("\n[warn] no agent emitted a metric_value for this run.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
