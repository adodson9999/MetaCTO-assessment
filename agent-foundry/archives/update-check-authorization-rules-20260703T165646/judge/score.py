#!/usr/bin/env python3
"""Judge scorer — authorization fidelity layer.

The agents emit blind test results (they never see the gold). This step reads
each agent's recorded cases for a run, compares them to data/authz/gold.json under
the contract in judge/metric_authz.json, computes Authorization-Test Fidelity, and
writes that number back as each agent's metric_value. Then
scripts/judge_leaderboard_authz__check-authorization-rules.py ranks and updates the leaderboard.

Fidelity per agent = fraction of gold sub_tests where the agent's recorded tuple
    (assigned expected_code, observed actual_class, data_exposed, leak_safe)
equals the gold tuple for the same sub_test. Missing sub_tests score 0.

Usage:
    python judge/score_authz.py --workspace . --run-id <id>
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


def _tuple(c: dict):
    return (c.get("expected_code"), c.get("actual_class"),
            bool(c.get("data_exposed")), bool(c.get("leak_safe")))


def gold_truth(ws: Path) -> dict:
    gold = _load(ws / "data" / "authz" / "gold.json", {"sub_tests": []})
    return {c["sub_test"]: _tuple(c) for c in gold["sub_tests"]}


def agent_observed(cases_doc: dict) -> dict:
    obs = {}
    for c in cases_doc.get("cases", []):
        st = c.get("sub_test")
        if not st or st == "_none_":
            continue
        if c.get("actual_class") in (None, "none"):
            continue
        obs[st] = _tuple(c)
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
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {"cases": []})
        obs = agent_observed(cases_doc)

        matches = sum(1 for st, gold_t in truth.items() if obs.get(st) == gold_t)
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = len(obs)

        meta["metric_name"] = "authorization_test_fidelity"
        meta["metric_value"] = fidelity
        meta["fidelity_matches"] = matches
        meta["fidelity_denominator"] = denom
        meta["coverage_sub_tests"] = covered
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, fidelity, matches, denom, covered,
                     cases_doc.get("access_control_accuracy_rate_pct")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Authorization-Test Fidelity (denominator = {denom} gold sub_tests)")
    print(f"{'agent':40} {'fidelity%':>9} {'matches':>8} {'coverage':>9} {'accuracy%':>9}")
    for agent, fid, m, d, cov, acc in rows:
        print(f"{agent:40} {fid:>9} {m:>8} {cov:>9} {str(acc):>9}")
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
