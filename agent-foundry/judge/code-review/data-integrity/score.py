#!/usr/bin/env python3
"""Judge scorer + discriminator for the code-review-data-integrity task (group code-review).

The agents emit blind per-case {rating, notes} objects (they never see the gold band). This
step reads each agent's recorded per-case decisions for a run, recomputes rating_band_accuracy
authoritatively against the gold bands in the held-out set under the contract in
judge/code-review/data-integrity/metric.json, and ranks lexicographically:

  1. rating_band_accuracy (correctness) — mean over cases of 1.0 when the strict {rating,
     notes} schema passes AND rating falls inside the case gold band, else 0.0. Primary rank
     key; written back as metric_value.
  2. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower better);
     tokens=0 (framework didn't expose usage) sorts last so it can't win a tie it can't
     substantiate.

Ranking: rating_band_accuracy desc, tokens asc, elapsed asc. Writes each number into the
agent's emit JSON and renders results/leaderboard-code-review-data-integrity.{json,md}.

Usage:
    python judge/code-review/data-integrity/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "code-review-data-integrity"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def _score_agent(jf: Path, cases_gold: list, denom: int, score_decision) -> dict | None:
    """Recompute rating_band_accuracy for one agent's emit file, write the enriched numbers
    back, and return a leaderboard row (or None if not a code-review-data-integrity run)."""
    meta = _load(jf, {})
    cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
    if "cases" not in cases_doc or "rating_band_accuracy" not in cases_doc:
        return None
    score_total = schema_ok = 0.0
    by_id = {c["id"]: c for c in cases_gold}
    for case in cases_doc.get("cases", []):
        gold = by_id.get(case.get("case_id"))
        if not gold:
            continue
        cells = score_decision(case.get("emitted") or {}, gold["gold_band"])
        score_total += cells["case_score"]
        schema_ok += 1.0 if cells["schema_ok"] else 0.0
    band_accuracy = round(score_total / denom, 4) if denom else 0.0
    schema_pct = round(100.0 * schema_ok / denom, 2) if denom else 0.0
    tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
    elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)
    meta.update({
        "metric_name": "rating_band_accuracy", "metric_value": band_accuracy,
        "cases_total": denom, "schema_valid_pct": schema_pct,
        "tokens_total": tokens, "elapsed_seconds": elapsed,
    })
    jf.write_text(json.dumps(meta, indent=2))
    return {"agent": meta.get("agent", jf.stem), "band_accuracy": band_accuracy,
            "schema_pct": schema_pct, "tokens": tokens, "elapsed": elapsed}


def _write_leaderboard(ws: Path, out_prefix: str, run_id: str, rows: list) -> None:
    lb_path = ws / f"{out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "rating_band_accuracy desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": run_id,
                       "ts": datetime.now(timezone.utc).isoformat(), "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {TASK}",
          "Rank key: **rating_band_accuracy ↓ → tokens ↑ → elapsed ↑**",
          f"Metric: rating_band_accuracy (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {run_id}",
          "",
          "| Rank | Agent | BandAccuracy | SchemaValid% | Tokens | Elapsed(s) |",
          "|------|-------|--------------|--------------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['band_accuracy']:g} | {r['schema_pct']:g} | "
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
    import dataintegrity_spec  # noqa: E402

    spec = json.loads((ws / "data" / "code-review-data-integrity" / "dataintegrity_spec.json").read_text())
    cases_gold = dataintegrity_spec.load_cases(spec["held_out_path"])
    denom = len(cases_gold)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        row = _score_agent(jf, cases_gold, denom, dataintegrity_spec.score_decision)
        if row is not None:
            rows.append(row)

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["band_accuracy"], tok, r["elapsed"])
    rows.sort(key=keyf)

    _write_leaderboard(ws, a.out_prefix, a.run_id, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
