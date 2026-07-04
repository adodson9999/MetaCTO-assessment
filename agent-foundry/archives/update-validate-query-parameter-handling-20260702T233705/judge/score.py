#!/usr/bin/env python3
"""Judge scorer + discriminator for the query-parameter-handling task.

Two layers, and a tie-breaking discriminator stack so the leaderboard is strictly
ranked even when correctness saturates:

  1. Query-Parameter Test Fidelity (correctness) — % of gold (collection x scenario)
     cases the agent's harness-observed token reproduces. Primary rank key.

  2. Plan Conformance (construction precision) — DETERMINISTIC structural exactness of
     the agent's RAW emitted plan vs the canonical debate-gated reference plan, BEFORE
     the tolerant harness normalises it (see queryparam_spec.plan_conformance). This is
     the discriminator that separates frameworks when fidelity ties: a plan that only
     scores 100% fidelity because the harness fixed it up loses conformance points here.

  3. Efficiency — total LLM tokens consumed (lower better) then wall-clock elapsed
     (lower better). Captured uniformly by the harness. Final tie-breaks.

Ranking is lexicographic: fidelity ↓, conformance ↓, tokens ↑, elapsed ↑. Writes each
number back into the agent's emit JSON and renders
results/leaderboard-validate-query-parameter-handling.{json,md}.

Usage:
    python judge/validate-query-parameter-handling/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "validate-query-parameter-handling"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_doc(ws: Path) -> dict:
    return _load(ws / "data" / TASK / "gold.json", {"collections": []})


def gold_truth(gold: dict) -> dict:
    truth = {}
    for col in gold["collections"]:
        for s in col["scenarios"]:
            truth[(col["collection"], s["scenario"])] = s["observed_token"]
    return truth


def gold_reference_plans(gold: dict) -> dict:
    return {col["collection"]: col.get("reference_plan", {}) for col in gold["collections"]}


def agent_observed(cases_doc: dict) -> dict:
    obs = {}
    for col in cases_doc.get("collections", []):
        for s in col.get("scenarios", []):
            obs[(col["collection"], s["scenario"])] = s.get("observed_token")
    return obs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import queryparam_spec  # noqa: E402

    gold = gold_doc(ws)
    truth = gold_truth(gold)
    ref_plans = gold_reference_plans(gold)
    denom = len(truth)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "collections" not in cases_doc or "query_param_handling_accuracy_pct" not in cases_doc:
            continue  # not a query-parameter run

        # 1. fidelity
        obs = agent_observed(cases_doc)
        matches = sum(1 for key, gold_tok in truth.items()
                      if obs.get(key) == gold_tok and obs.get(key) not in (None, "missing"))
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        # 2. plan conformance (deterministic discriminator)
        earned = total = 0
        conf_issues = []
        for col in cases_doc.get("collections", []):
            ref = ref_plans.get(col["collection"], {})
            res = queryparam_spec.plan_conformance(col.get("emitted_plan") or {}, ref)
            earned += res["earned"]
            total += res["total"]
            for iss in res["issues"]:
                if len(conf_issues) < 30:
                    conf_issues.append(f"{col['collection']}: {iss}")
        conformance = round(100.0 * earned / total, 2) if total else 0.0

        # 3. efficiency
        tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
        elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)

        meta.update({
            "metric_name": "query_param_test_fidelity",
            "metric_value": fidelity,
            "fidelity_matches": matches,
            "fidelity_denominator": denom,
            "coverage_scenarios": covered,
            "plan_conformance_pct": conformance,
            "plan_conformance_earned": earned,
            "plan_conformance_total": total,
            "plan_conformance_issues": conf_issues,
            "tokens_total": tokens,
            "elapsed_seconds": elapsed,
            "headline_accuracy_pct": cases_doc.get("query_param_handling_accuracy_pct"),
        })
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "conformance": conformance,
                     "tokens": tokens, "elapsed": elapsed, "coverage": covered,
                     "accuracy": cases_doc.get("query_param_handling_accuracy_pct")})

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    # Lexicographic discriminator stack: fidelity ↓, conformance ↓, tokens ↑, elapsed ↑.
    # tokens==0 (framework didn't expose usage) sorts last among ties so it never
    # wins a tie-break it can't substantiate.
    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["fidelity"], -r["conformance"], tok, r["elapsed"])
    rows.sort(key=keyf)

    # persist leaderboard json (with run history)
    lb_path = ws / f"{a.out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "rank_key": "fidelity > conformance > tokens > elapsed",
                         "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "fidelity desc, conformance desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": a.run_id,
                       "ts": datetime.now(timezone.utc).isoformat(),
                       "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    # render md
    md = [f"# Leaderboard — {TASK}",
          "Rank key: **fidelity ↓ → plan-conformance ↓ → tokens ↑ → elapsed ↑** "
          "(conformance + efficiency are the discriminators that break fidelity ties)",
          f"Updated: {datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "| Rank | Agent | Fidelity% | Conformance% | Tokens | Elapsed(s) | Accuracy% |",
          "|------|-------|-----------|--------------|--------|------------|-----------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {r['conformance']:g} | "
                  f"{tok} | {r['elapsed']:g} | {r['accuracy']} |")
    (ws / f"{a.out_prefix}.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
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
