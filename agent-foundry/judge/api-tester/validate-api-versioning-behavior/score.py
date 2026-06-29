#!/usr/bin/env python3
"""Judge scorer + discriminator for the versioning-behavior task.

Two layers, and a tie-breaking discriminator stack so the leaderboard is strictly
ranked even when correctness saturates:

  1. Version-Routing Test Fidelity (correctness) — % of gold (endpoint x scenario)
     cases the agent's harness-observed token reproduces EXACTLY, including
     legitimately-"missing" tokens (against unversioned DummyJSON the gold itself
     records "missing" for the schema/Deprecation-header scenarios, so faithfully
     reproducing them is correct; an agent that fails to EMIT a case instead diverges
     on that case's routing/status scenario, where gold holds a real code, and is
     penalised). Primary rank key.

  2. Plan Conformance (construction precision) — DETERMINISTIC structural exactness of
     the agent's RAW emitted plan vs the canonical debate-gated reference plan, BEFORE
     the tolerant harness normalises it (see versioning_spec.plan_conformance). The
     discriminator that separates frameworks when fidelity ties.

  3. Efficiency — total LLM tokens consumed (lower better) then wall-clock elapsed
     (lower better). Captured uniformly by the harness. Final tie-breaks.

Ranking is lexicographic: fidelity ↓, conformance ↓, tokens ↑, elapsed ↑. Writes each
number back into the agent's emit JSON and renders
results/leaderboard-validate-api-versioning-behavior.{json,md}.

Usage:
    python judge/validate-api-versioning-behavior/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "validate-api-versioning-behavior"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_doc(ws: Path) -> dict:
    return _load(ws / "data" / TASK / "gold.json", {"endpoints": []})


def gold_truth(gold: dict) -> dict:
    truth = {}
    for ep in gold["endpoints"]:
        for s in ep["scenarios"]:
            truth[(ep["endpoint"], s["scenario"])] = s["observed_token"]
    return truth


def gold_reference_plans(gold: dict) -> dict:
    return {ep["endpoint"]: ep.get("reference_plan", {}) for ep in gold["endpoints"]}


def agent_observed(cases_doc: dict) -> dict:
    obs = {}
    for ep in cases_doc.get("endpoints", []):
        for s in ep.get("scenarios", []):
            obs[(ep["endpoint"], s["scenario"])] = s.get("observed_token")
    return obs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import versioning_spec  # noqa: E402

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
        if "endpoints" not in cases_doc or "version_routing_accuracy_pct" not in cases_doc:
            continue  # not a versioning run

        # 1. fidelity (exact token reproduction, "missing"=="missing" counts)
        obs = agent_observed(cases_doc)
        matches = sum(1 for key, gold_tok in truth.items() if obs.get(key) == gold_tok)
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        covered = sum(1 for v in obs.values() if v not in (None, "missing"))

        # 2. plan conformance (deterministic discriminator)
        earned = total = 0
        conf_issues = []
        for ep in cases_doc.get("endpoints", []):
            ref = ref_plans.get(ep["endpoint"], {})
            res = versioning_spec.plan_conformance(ep.get("emitted_plan") or {}, ref)
            earned += res["earned"]
            total += res["total"]
            for iss in res["issues"]:
                if len(conf_issues) < 30:
                    conf_issues.append(f"{ep['endpoint']}: {iss}")
        conformance = round(100.0 * earned / total, 2) if total else 0.0

        # 3. efficiency
        tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
        elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)

        meta.update({
            "metric_name": "version_routing_test_fidelity",
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
            "headline_accuracy_pct": cases_doc.get("version_routing_accuracy_pct"),
        })
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "conformance": conformance,
                     "tokens": tokens, "elapsed": elapsed, "coverage": covered,
                     "accuracy": cases_doc.get("version_routing_accuracy_pct")})

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
