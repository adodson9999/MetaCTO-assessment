#!/usr/bin/env python3
"""Judge scorer + discriminator for the Bug-Reporter task ("n602").

The agents emit blind per-failure decisions (they never see the gold). This step reads
each agent's recorded per-failure decisions for a run, compares them to the deterministic
gold decisions in data/bug-reporter/gold.json under the contract in
judge/bug-reporter/metric.json, and ranks lexicographically:

  1. Bug-Report Fidelity (correctness) — % of gold (failure x decision_field) cells the
     agent's emitted decision reproduces. Primary rank key. Written back as metric_value.

  2. Bug Report Completeness Rate (the task's own headline metric) — sum of
     complete_artifact_count over reports / (reports x 10) x 100. Discriminator when
     fidelity ties.

  3. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower better).
     Final tie-breaks; tokens=0 sorts last so it can't win a tie it can't substantiate.

Ranking: fidelity ↓, completeness ↓, tokens ↑, elapsed ↑. Writes each number into the
agent's emit JSON and renders results/leaderboard-bug-reporter.{json,md}.

Usage:
    python judge/bug-reporter/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "bug-reporter"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def gold_decisions(ws: Path) -> list:
    gold = _load(ws / "data" / TASK / "gold.json", {"gold_decisions": []})
    return gold.get("gold_decisions", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import bugreport_spec  # noqa: E402

    golds = {g["agent_name"]: g["decision"] for g in gold_decisions(ws)}
    fields_per = len(bugreport_spec.DECISION_FIELDS)
    denom = len(golds) * fields_per
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "reports" not in cases_doc or "bug_report_fidelity_pct" not in cases_doc:
            continue  # not a bug-reporter run

        # 1. fidelity (recomputed authoritatively from the emitted reports vs gold)
        matches = 0
        for rep in cases_doc.get("reports", []):
            gold = golds.get(rep.get("agent_name"))
            if not gold:
                continue
            emitted = {
                "title": rep.get("title"),
                "severity": rep.get("severity"),
                "priority": rep.get("priority"),
                "testing_steps": (rep.get("artifacts") or {}).get("testing_steps"),
                "postman_references": (rep.get("artifacts") or {}).get("postman_references"),
            }
            cells = bugreport_spec.score_decision(emitted, gold)
            matches += sum(1 for v in cells.values() if v)
        fidelity = round(100.0 * matches / denom, 2) if denom else 0.0

        # 2. completeness (the task's headline)
        completeness = float((cases_doc.get("metrics") or {}).get(
            "bug_report_completeness_rate_pct", 0.0) or 0.0)

        # 3. efficiency
        tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
        elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)

        meta.update({
            "metric_name": "bug_report_fidelity_pct",
            "metric_value": fidelity,
            "fidelity_matches": matches,
            "fidelity_denominator": denom,
            "bug_report_completeness_rate_pct": completeness,
            "tokens_total": tokens,
            "elapsed_seconds": elapsed,
            "would_exit_code_1": (cases_doc.get("metrics") or {}).get("would_exit_code_1"),
            "task_metrics": cases_doc.get("metrics"),
        })
        jf.write_text(json.dumps(meta, indent=2))
        rows.append({"agent": agent, "fidelity": fidelity, "completeness": completeness,
                     "tokens": tokens, "elapsed": elapsed,
                     "exit1": (cases_doc.get("metrics") or {}).get("would_exit_code_1")})

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["fidelity"], -r["completeness"], tok, r["elapsed"])
    rows.sort(key=keyf)

    lb_path = ws / f"{a.out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "fidelity desc, completeness desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": a.run_id,
                       "ts": datetime.now(timezone.utc).isoformat(),
                       "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {TASK} (n602)",
          "Rank key: **fidelity ↓ → completeness ↓ → tokens ↑ → elapsed ↑** "
          "(completeness + efficiency break fidelity ties)",
          f"Metric: bug_report_fidelity_pct (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {a.run_id}",
          "",
          "| Rank | Agent | Fidelity% | Completeness% | Exit1 | Tokens | Elapsed(s) |",
          "|------|-------|-----------|---------------|-------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['fidelity']:g} | {r['completeness']:g} | "
                  f"{r['exit1']} | {tok} | {r['elapsed']:g} |")
    (ws / f"{a.out_prefix}.md").write_text("\n".join(md) + "\n")

    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
