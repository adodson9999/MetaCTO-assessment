#!/usr/bin/env python3
"""Judge scorer + discriminator for the Documentation-Reviewer task ("n603").

The agents emit blind per-report verdicts (they never see the gold). This step reads each
agent's recorded per-case decisions for a run, recomputes verdict accuracy authoritatively
against the gold verdicts in data/documentation-reviewer/gold.json under the contract in
judge/general/documentation-reviewer/metric.json, and ranks lexicographically:

  1. Verdict Accuracy (correctness) — % of labeled reports whose emitted verdict matches the
     gold verdict (yes | no | missing-docs). Primary rank key; written back as metric_value.
  2. Source-of-Truth-File Match — % of reports where the correct verdict ALSO named the
     correct source-of-truth file (the newest-file rule). Discriminator on a verdict tie.
  3. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower better);
     tokens=0 sorts last so it can't win a tie it can't substantiate.

Ranking: verdict_accuracy desc, source_of_truth_match desc, tokens asc, elapsed asc. Writes
each number into the agent's emit JSON and renders results/leaderboard-documentation-reviewer.{json,md}.

Usage:
    python judge/general/documentation-reviewer/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "documentation-reviewer"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def _score_agent(jf: Path, golds: dict, denom: int, score_decision) -> dict | None:
    """Recompute verdict accuracy + source-of-truth match for one agent's emit file,
    write the enriched numbers back, and return a leaderboard row (or None if not a
    documentation-reviewer run)."""
    meta = _load(jf, {})
    cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
    if "cases" not in cases_doc or "verdict_accuracy_pct" not in cases_doc:
        return None
    v_correct = sot_correct = 0
    for case in cases_doc.get("cases", []):
        gold = golds.get(case.get("case_id"))
        if not gold:
            continue
        cells = score_decision(case.get("emitted") or {}, gold)
        v_correct += 1 if cells["verdict"] else 0
        sot_correct += 1 if cells["source_of_truth_file"] else 0
    verdict_accuracy = round(100.0 * v_correct / denom, 2) if denom else 0.0
    sot_match = round(100.0 * sot_correct / denom, 2) if denom else 0.0
    tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
    elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)
    meta.update({
        "metric_name": "verdict_accuracy_pct", "metric_value": verdict_accuracy,
        "verdicts_correct": v_correct, "verdicts_denominator": denom,
        "source_of_truth_match_pct": sot_match,
        "tokens_total": tokens, "elapsed_seconds": elapsed,
    })
    jf.write_text(json.dumps(meta, indent=2))
    return {"agent": meta.get("agent", jf.stem), "verdict_accuracy": verdict_accuracy,
            "sot_match": sot_match, "tokens": tokens, "elapsed": elapsed}


def _write_leaderboard(ws: Path, out_prefix: str, run_id: str, rows: list) -> None:
    lb_path = ws / f"{out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "verdict_accuracy desc, source_of_truth_match desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": run_id,
                       "ts": datetime.now(timezone.utc).isoformat(), "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {TASK} (n603)",
          "Rank key: **verdict accuracy ↓ → source-of-truth-file match ↓ → tokens ↑ → elapsed ↑**",
          f"Metric: verdict_accuracy_pct (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {run_id}",
          "",
          "| Rank | Agent | Verdict% | SourceOfTruthFile% | Tokens | Elapsed(s) |",
          "|------|-------|----------|--------------------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['verdict_accuracy']:g} | {r['sot_match']:g} | "
                  f"{tok} | {r['elapsed']:g} |")
    (ws / f"{out_prefix}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import docreview_spec  # noqa: E402

    golds = docreview_spec.gold_index(ws, TASK)
    denom = len(golds)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        row = _score_agent(jf, golds, denom, docreview_spec.score_decision)
        if row is not None:
            rows.append(row)

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["verdict_accuracy"], -r["sot_match"], tok, r["elapsed"])
    rows.sort(key=keyf)

    _write_leaderboard(ws, a.out_prefix, a.run_id, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
