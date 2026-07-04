#!/usr/bin/env python3
"""Judge scorer + leaderboard for the response-schema validation task.

The agents emit blind results (they never see the gold). This step reads each
agent's recorded cases for a run, compares them to data/schema/gold.json under the
contract in judge/schema/metric.json, computes Response-Validation Fidelity, writes
that number back as each agent's metric_value, applies the documented tie-breakers,
and updates results/schema/leaderboard.{json,md} (tracking best-so-far over time).

Usage:
    python judge/schema/score.py --workspace . --run-id <id>
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def gold_truth(ws: Path) -> dict:
    """slug -> the gold comparison tuple."""
    gold = _load(ws / "data" / "schema" / "gold.json", {"endpoints": []})
    truth = {}
    for ep in gold["endpoints"]:
        truth[ep["slug"]] = {
            "actual_class": ep["actual_class"],
            "documented_schema": ep["documented_schema"],
            "conformance": ep["conformance"],
            "validation_error_count": ep["validation_error_count"],
        }
    return truth


def agent_observed(cases_doc: dict) -> dict:
    """slug -> observed comparison tuple (+ schema_claim_correct), covered only."""
    obs = {}
    for c in cases_doc.get("cases", []):
        if not c.get("covered"):
            continue
        obs[c["slug"]] = {
            "actual_class": c.get("actual_class"),
            "documented_schema": c.get("documented_schema"),
            "conformance": c.get("conformance"),
            "validation_error_count": c.get("validation_error_count"),
            "schema_claim_correct": bool(c.get("schema_claim_correct")),
        }
    return obs


def _matches(gold: dict, obs: dict | None) -> bool:
    if obs is None:
        return False
    return (obs["actual_class"] == gold["actual_class"]
            and obs["documented_schema"] == gold["documented_schema"]
            and obs["conformance"] == gold["conformance"]
            and obs["validation_error_count"] == gold["validation_error_count"]
            and obs["schema_claim_correct"])


def _valid_2xx_success(cases_doc: dict) -> int:
    return sum(1 for c in cases_doc.get("cases", [])
               if c.get("covered") and c.get("actual_class") == "2xx")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    metric = _load(ws / "judge" / "schema" / "metric.json", {})
    metric_name = metric.get("metric_name", "response_validation_fidelity")
    truth = gold_truth(ws)
    denom = len(truth)
    run_dir = ws / "results" / "schema" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"cases": []})
        obs = agent_observed(cases_doc)

        matches = sum(1 for slug, g in truth.items() if _matches(g, obs.get(slug)))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = len(obs)

        meta["metric_name"] = metric_name
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_cases"] = covered
        meta["valid_2xx_success"] = _valid_2xx_success(cases_doc)
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "matches": matches,
                     "coverage": covered, "valid2xx": meta["valid_2xx_success"],
                     "conformance": cases_doc.get("schema_conformance_rate_pct")})

    rows.sort(key=lambda r: (r["fidelity"], r["coverage"], r["valid2xx"]), reverse=True)

    lb_path = ws / "results" / "schema" / "leaderboard.json"
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

    def _fmt(v):
        return "N/A" if v is None else f"{v}"

    md = [f"# Leaderboard — {metric_name} (higher_is_better)",
          f"Metric: Response-Validation Fidelity vs gold  ·  Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          f"Denominator = {denom} gold endpoints.  Headline = Schema Conformance Rate "
          "(N/A under current spec: 0 endpoints document a response schema).",
          "",
          "| Rank | Agent | Fidelity% | Best | Runs | Coverage | Conformance% |",
          "|------|-------|-----------|------|------|----------|--------------|"]
    for i, r in enumerate(rows, 1):
        rec = lb["agents"][r["agent"]]
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {rec['best']:g} | {rec['runs']} | "
                  f"{r['coverage']}/{denom} | {_fmt(r['conformance'])} |")
    (ws / "results" / "schema" / "leaderboard.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    if not rows:
        print("\n[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
