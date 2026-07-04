#!/usr/bin/env python3
"""Judge scorer — fidelity layer for the rate-limit-enforcement task.

The agents emit blind test results (they never see the gold). This step reads each
agent's recorded scenarios for a run, compares them to
data/test-rate-limit-enforcement/gold.json under the contract in
judge/test-rate-limit-enforcement/metric.json, computes Rate-Limit-Test Fidelity, and
writes that number back as each agent's metric_value. Then scripts/judge_score.py
ranks and updates the leaderboard.

Usage:
    python judge/test-rate-limit-enforcement/score.py --workspace . --run-id <id>
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
    gold = _load(ws / "data" / "test-rate-limit-enforcement" / "gold.json", {"endpoints": []})
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
            continue  # not a rate-limit run (e.g. a different task's emit)
        obs = agent_observed(cases_doc)

        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        meta["metric_name"] = "rate_limit_test_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_scenarios"] = covered
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, denom, covered,
                     cases_doc.get("rate_limit_contract_correctness_rate_pct"),
                     cases_doc.get("rate_limit_enforced")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Rate-Limit-Test Fidelity (denominator = {denom} gold scenarios)")
    print(f"{'agent':40} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'correct%':>9} {'enforced':>9}")
    for agent, fid, m, d, cov, corr, enf in rows:
        print(f"{agent:40} {fid:>9} {m:>8} {cov:>9} {str(corr):>9} {str(enf):>9}")
    if not rows:
        print("[warn] no agent results found for this run.")
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
