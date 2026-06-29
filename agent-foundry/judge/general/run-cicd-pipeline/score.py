#!/usr/bin/env python3
"""Judge scorer + discriminator for the CI/CD-Pipeline-Runner task.

The agents emit blind pipeline-summaries (they never see the gold). This step reads
each agent's recorded per-scenario summaries for a run, compares them to the
deterministic gold summaries in data/run-cicd-pipeline/gold.json under the contract in
judge/run-cicd-pipeline/metric.json, and ranks lexicographically:

  1. Pipeline-Summary Fidelity (correctness) — % of gold (scenario x field) cells the
     agent's emitted summary reproduces. Primary rank key. Written back as metric_value.

  2. Report Conformance (construction precision) — DETERMINISTIC structural exactness of
     the agent's RAW summary vs gold BEFORE the tolerant fidelity normalisation
     (see cicd_spec.report_conformance). Discriminator when fidelity ties.

  3. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower
     better). Final tie-breaks; tokens=0 sorts last so it can't win a tie it can't
     substantiate.

Ranking: fidelity ↓, conformance ↓, tokens ↑, elapsed ↑. Writes each number into the
agent's emit JSON and renders results/leaderboard-run-cicd-pipeline.{json,md}.

Usage:
    python judge/run-cicd-pipeline/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "run-cicd-pipeline"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_summaries(ws: Path) -> dict:
    """scenario -> gold_summary."""
    gold = _load(ws / "data" / TASK / "gold.json", {"scenarios": []})
    return {s["scenario"]: s["gold_summary"] for s in gold.get("scenarios", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import cicd_spec  # noqa: E402

    golds = gold_summaries(ws)
    fields_per_scenario = len(cicd_spec.REPORT_FIELDS)
    denom = len(golds) * fields_per_scenario
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "runs" not in cases_doc or "pipeline_summary_fidelity_pct" not in cases_doc:
            continue  # not a cicd run

        # 1. fidelity + 2. conformance (recomputed authoritatively)
        matches = 0
        conf_earned = conf_total = 0
        conf_issues = []
        for run in cases_doc.get("runs", []):
            gold = golds.get(run["scenario"])
            if not gold:
                continue
            summary = run.get("emitted_summary") or {}
            cells = cicd_spec.score_summary(summary, gold)
            matches += sum(1 for v in cells.values() if v)

            conf = cicd_spec.report_conformance(summary, gold)
            conf_earned += conf["earned"]
            conf_total += conf["total"]
            for iss in conf["issues"]:
                if len(conf_issues) < 30:
                    conf_issues.append(f"{run['scenario']}: {iss}")

        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
        conformance = round(100.0 * conf_earned / conf_total, 2) if conf_total else 0.0

        # 3. efficiency
        tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
        elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)

        meta.update({
            "metric_name": "pipeline_summary_fidelity_pct",
            "metric_value": fidelity,
            "fidelity_matches": matches,
            "fidelity_denominator": denom,
            "report_conformance_pct": conformance,
            "report_conformance_earned": conf_earned,
            "report_conformance_total": conf_total,
            "report_conformance_issues": conf_issues,
            "tokens_total": tokens,
            "elapsed_seconds": elapsed,
            "runs_that_must_block_deployment": cases_doc.get("runs_that_must_block_deployment"),
            "ollama_server_up": (cases_doc.get("ollama_health") or {}).get("server_up"),
        })
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "conformance": conformance,
                     "tokens": tokens, "elapsed": elapsed})

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    # Lexicographic: fidelity ↓, conformance ↓, tokens ↑, elapsed ↑.
    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["fidelity"], -r["conformance"], tok, r["elapsed"])
    rows.sort(key=keyf)

    # persist leaderboard json (with run history)
    lb_path = ws / f"{a.out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "fidelity desc, conformance desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": a.run_id,
                       "ts": datetime.now(timezone.utc).isoformat(),
                       "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    # render md
    md = [f"# Leaderboard — {TASK}",
          "Rank key: **fidelity ↓ → report-conformance ↓ → tokens ↑ → elapsed ↑** "
          "(conformance + efficiency break fidelity ties)",
          f"Metric: pipeline_summary_fidelity_pct (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "| Rank | Agent | Fidelity% | Conformance% | Tokens | Elapsed(s) |",
          "|------|-------|-----------|--------------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {r['conformance']:g} | "
                  f"{tok} | {r['elapsed']:g} |")
    (ws / f"{a.out_prefix}.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
