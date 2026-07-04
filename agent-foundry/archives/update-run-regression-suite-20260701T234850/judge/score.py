#!/usr/bin/env python3
"""Judge scorer + discriminator for the Run-Regression-Suite task.

The agents emit blind regression reports (they never see the gold). This step reads
each agent's recorded per-pair reports for a run, compares them to the deterministic
gold reports in data/run-regression-suite/gold.json under the contract in
judge/run-regression-suite/metric.json, and ranks lexicographically:

  1. Regression-Report Fidelity (correctness) — % of gold (build_pair x field) cells
     the agent's emitted report reproduces. Primary rank key. Written back as
     metric_value.

  2. Report Conformance (construction precision) — DETERMINISTIC structural exactness
     of the agent's RAW report vs gold BEFORE the tolerant fidelity normalisation
     (see regression_spec.report_conformance). Discriminator when fidelity ties.

  3. Message Fidelity — fraction of flagged regressions whose failure_message was
     reproduced verbatim. Discriminator.

  4. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower
     better). Final tie-breaks; tokens=0 sorts last so it can't win a tie it can't
     substantiate.

Ranking: fidelity ↓, conformance ↓, message_fidelity ↓, tokens ↑, elapsed ↑. Writes
each number into the agent's emit JSON and renders
results/leaderboard-run-regression-suite.{json,md}.

Usage:
    python judge/run-regression-suite/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "run-regression-suite"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_reports(ws: Path) -> dict:
    """pair -> gold_report."""
    gold = _load(ws / "data" / TASK / "gold.json", {"pairs": []})
    return {p["pair"]: p["gold_report"] for p in gold.get("pairs", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import regression_spec  # noqa: E402

    golds = gold_reports(ws)
    fields_per_pair = len(regression_spec.REPORT_FIELDS)
    denom = len(golds) * fields_per_pair
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "pairs" not in cases_doc or "regression_report_fidelity_pct" not in cases_doc:
            continue  # not a regression run

        # 1. fidelity + 2. conformance + 3. message fidelity (recomputed authoritatively)
        matches = 0
        conf_earned = conf_total = 0
        msg_hits = msg_total = 0
        conf_issues = []
        for pair in cases_doc.get("pairs", []):
            gold = golds.get(pair["pair"])
            if not gold:
                continue
            report = pair.get("emitted_report") or {}
            cells = regression_spec.score_report(report, gold)
            matches += sum(1 for v in cells.values() if v)

            conf = regression_spec.report_conformance(report, gold)
            conf_earned += conf["earned"]
            conf_total += conf["total"]
            for iss in conf["issues"]:
                if len(conf_issues) < 30:
                    conf_issues.append(f"{pair['pair']}: {iss}")

            mf = regression_spec.message_fidelity(report, gold)
            if mf is not None:
                msg_hits += mf
                msg_total += 100.0  # mf is a percent; average the percents

        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        conformance = round(100.0 * conf_earned / conf_total, 2) if conf_total else 0.0
        message_fid = round(msg_hits / (msg_total / 100.0), 2) if msg_total else None

        # 4. efficiency
        tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
        elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)

        meta.update({
            "metric_name": "regression_report_fidelity_pct",
            "metric_value": fidelity,
            "fidelity_matches": matches,
            "fidelity_denominator": denom,
            "report_conformance_pct": conformance,
            "report_conformance_earned": conf_earned,
            "report_conformance_total": conf_total,
            "report_conformance_issues": conf_issues,
            "message_fidelity_pct": message_fid,
            "tokens_total": tokens,
            "elapsed_seconds": elapsed,
            "builds_that_must_block_deployment": cases_doc.get("builds_that_must_block_deployment"),
            "deployment_confirmed": (cases_doc.get("deployment_health") or {}).get("deployment_confirmed"),
        })
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "conformance": conformance,
                     "message_fidelity": message_fid if message_fid is not None else 0.0,
                     "tokens": tokens, "elapsed": elapsed})

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    # Lexicographic: fidelity ↓, conformance ↓, message_fidelity ↓, tokens ↑, elapsed ↑.
    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["fidelity"], -r["conformance"], -r["message_fidelity"], tok, r["elapsed"])
    rows.sort(key=keyf)

    # persist leaderboard json (with run history)
    lb_path = ws / f"{a.out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "fidelity desc, conformance desc, message_fidelity desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": a.run_id,
                       "ts": datetime.now(timezone.utc).isoformat(),
                       "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    # render md
    md = [f"# Leaderboard — {TASK}",
          "Rank key: **fidelity ↓ → report-conformance ↓ → message-fidelity ↓ → tokens ↑ → elapsed ↑** "
          "(conformance + message-fidelity + efficiency break fidelity ties)",
          f"Metric: regression_report_fidelity_pct (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "| Rank | Agent | Fidelity% | Conformance% | MsgFidelity% | Tokens | Elapsed(s) |",
          "|------|-------|-----------|--------------|--------------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        mf = r["message_fidelity"]
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {r['conformance']:g} | "
                  f"{mf:g} | {tok} | {r['elapsed']:g} |")
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
