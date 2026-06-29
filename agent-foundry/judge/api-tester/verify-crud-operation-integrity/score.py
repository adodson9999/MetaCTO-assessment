#!/usr/bin/env python3
"""Judge scorer + leaderboard for the Verify-CRUD-Operation-Integrity task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded cases for a run, compares them to data/crud/gold.json under the
contract in judge/crud/metric.json, computes CRUD-Test Fidelity, writes that number
back as each agent's metric_value, applies the tie-breakers, and updates
results/crud/leaderboard.{json,md} (tracking best-so-far over time).

Usage:
    python judge/crud/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

HTTP_STEPS = ("CREATE", "READ", "UPDATE", "READ_AFTER_UPDATE", "DELETE", "READ_AFTER_DELETE")
DB_CHECKPOINTS = ("DB_AFTER_CREATE", "DB_AFTER_READ", "DB_AFTER_UPDATE", "DB_FINAL")


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_truth(ws: Path) -> dict:
    """(slug, kind, key) -> observed value, over every gold cell.
    kind in {"http","db"}; http key = step name -> actual_code; db key = checkpoint -> db_state."""
    gold = _load(ws / "data" / "crud" / "gold.json", {"resources": []})
    truth = {}
    for r in gold["resources"]:
        for s in r["steps"]:
            truth[(r["slug"], "http", s["step"])] = s["actual_code"]
        for d in r["db_checkpoints"]:
            truth[(r["slug"], "db", d["checkpoint"])] = d["db_state"]
    return truth


def agent_observed(cases_doc: dict) -> dict:
    obs = {}
    for r in cases_doc.get("resources", []):
        for s in r.get("steps", []):
            if s.get("covered") and s.get("actual_code") is not None:
                obs[(r["slug"], "http", s["step"])] = s["actual_code"]
        for d in r.get("db_checkpoints", []):
            obs[(r["slug"], "db", d["checkpoint"])] = d.get("db_state")
    return obs


def _create_success(cases_doc: dict) -> int:
    """Tie-breaker: count of resources whose CREATE step drove a 2xx."""
    n = 0
    for r in cases_doc.get("resources", []):
        for s in r.get("steps", []):
            if s["step"] == "CREATE" and isinstance(s.get("actual_code"), int):
                if 200 <= s["actual_code"] < 300:
                    n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    metric = _load(ws / "judge" / "crud" / "metric.json", {})
    metric_name = metric.get("metric_name", "crud_test_fidelity")
    truth = gold_truth(ws)
    denom = len(truth)
    run_dir = ws / "results" / "crud" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"resources": []})
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_v in truth.items() if obs.get(key) == gold_v)
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for k in truth if k in obs)

        meta["metric_name"] = metric_name
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_cells"] = covered
        meta["create_success"] = _create_success(cases_doc)
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "matches": matches,
                     "coverage": covered, "create": meta["create_success"],
                     "integrity": cases_doc.get("crud_integrity_rate_pct")})

    rows.sort(key=lambda r: (r["fidelity"], r["coverage"], r["create"]), reverse=True)

    lb_path = ws / "results" / "crud" / "leaderboard.json"
    lb = _load(lb_path, {"metric_name": metric_name, "direction": "higher_is_better",
                         "agents": {}, "runs": []})
    this_run = {r["agent"]: r["fidelity"] for r in rows}
    for r in rows:
        rec = lb["agents"].get(r["agent"], {"best": None, "runs": 0})
        rec["runs"] += 1
        rec["last"] = r["fidelity"]
        if rec["best"] is None or r["fidelity"] > rec["best"]:
            rec["best"] = r["fidelity"]
        lb["agents"][r["agent"]] = rec
    lb["runs"].append({"run_id": a.run_id, "ts": datetime.now(timezone.utc).isoformat(),
                       "values": this_run})
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {metric_name} (higher_is_better)",
          f"Metric: CRUD-Test Fidelity vs gold  ·  Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          f"Denominator = {denom} gold cells (7 resources x 10 cells).  Headline = CRUD Integrity Rate (API property, 0% by design).",
          "",
          "| Rank | Agent | Fidelity% | This-run best | Runs | Coverage | Integrity% (API) |",
          "|------|-------|-----------|---------------|------|----------|------------------|"]
    for i, r in enumerate(rows, 1):
        rec = lb["agents"][r["agent"]]
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {rec['best']:g} | {rec['runs']} | "
                  f"{r['coverage']}/{denom} | {r['integrity']} |")
    (ws / "results" / "crud" / "leaderboard.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    if not rows:
        print("\n[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
