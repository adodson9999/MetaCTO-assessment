#!/usr/bin/env python3
"""Judge scorer + leaderboard for the response status-code task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded cases for a run, compares them to data/status/gold.json under the
contract in judge/status/metric.json, computes Status-Code Test Fidelity, writes
that number back as each agent's metric_value, applies the documented tie-breakers,
and updates results/status/leaderboard.{json,md} (tracking best-so-far over time).

Usage:
    python judge/status/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_truth(ws: Path) -> dict:
    """(slug, documented_code) -> gold actual_code, over every gold case."""
    gold = _load(ws / "data" / "status" / "gold.json", {"endpoints": []})
    truth = {}
    for ep in gold["endpoints"]:
        for c in ep["cases"]:
            truth[(ep["slug"], c["documented_code"])] = c["actual_code"]
    return truth


def agent_observed(cases_doc: dict) -> dict:
    """(slug, documented_code) -> observed actual_code, for covered cases."""
    obs = {}
    for c in cases_doc.get("cases", []):
        if not c.get("covered"):
            continue
        if c.get("actual_code") is None:
            continue
        obs[(c["slug"], c["documented_code"])] = c["actual_code"]
    return obs


def _valid_2xx_success(cases_doc: dict) -> int:
    """Tie-breaker: count of 200/201 cases the agent actually drove to a 2xx."""
    n = 0
    for c in cases_doc.get("cases", []):
        if c.get("documented_code") in (200, 201) and isinstance(c.get("actual_code"), int):
            if 200 <= c["actual_code"] < 300:
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    metric = _load(ws / "judge" / "status" / "metric.json", {})
    metric_name = metric.get("metric_name", "status_code_test_fidelity")
    truth = gold_truth(ws)
    denom = len(truth)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"cases": []})
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_code in truth.items() if obs.get(key) == gold_code)
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
                     "accuracy": cases_doc.get("status_code_accuracy_rate_pct")})

    # rank by fidelity, then tie-breakers: coverage -> valid_2xx -> agent name
    rows.sort(key=lambda r: (r["fidelity"], r["coverage"], r["valid2xx"]), reverse=True)

    # leaderboard over time
    lb_path = ws / "results" / "status" / "leaderboard.json"
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
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {metric_name} (higher_is_better)",
          f"Metric: Status-Code Test Fidelity vs gold  ·  Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          f"Denominator = {denom} testable gold cases.  Headline = Status Code Accuracy Rate (API property).",
          "",
          "| Rank | Agent | Fidelity% | This-run best | Runs | Coverage | Accuracy% (API) |",
          "|------|-------|-----------|---------------|------|----------|-----------------|"]
    for i, r in enumerate(rows, 1):
        rec = lb["agents"][r["agent"]]
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {rec['best']:g} | {rec['runs']} | "
                  f"{r['coverage']}/{denom} | {r['accuracy']} |")
    (ws / "results" / "status" / "leaderboard.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    if not rows:
        print("\n[warn] no agent results found for this run.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# --- Contract-oracle rollout (plan 40): hard guardrail carried in every prompt copy ---
# ## Contract-conformance oracle & deviation findings (hard guardrail)
#
# Your expected outcome for every case is the UNIVERSAL HTTP/REST contract for that operation, read from
# `agent-foundry/references/contract-oracle.md` — NEVER the target's own documentation or observed
# behaviour. For each case emit `expected_by_contract` (the status + invariants from the contract table)
# and, only when the target's documented expectation differs, `expected_by_docs`. A separate
# deterministic harness fills `observed` and emits `deviations[]` — every case where observed differs
# from expected_by_contract, or where expected_by_docs differs from expected_by_contract — as findings,
# surfaced EVEN WHEN the response is acceptable by the target's own docs. Verify every effect BLACK-BOX by
# read-back (a follow-up request): a create is proven by a follow-up GET returning the resource, a delete
# by a follow-up GET returning 404, an update by a follow-up GET reflecting the change — never by a
# database row, log line, or injected instrumentation the target may not expose; where such an assertion
# is impossible black-box, degrade to the observable signal rather than skipping it. Repeat each case the
# configured soak count and flag any non-deterministic result as a deviation. Enumerate the FULL
# documented surface — every resource × every method, and every field/parameter including nested paths and
# date/range; a documented capability that is unimplemented (404 or ignored) is a `missing_capability`
# deviation. You MUST NOT encode the target's observed behaviour as the contract, and MUST NOT carry an
# `also_accept` that admits a deviation from a standard code (e.g. accepting 200 for a creation the
# contract fixes at 201); either is a hard-guardrail violation and fails closed.
