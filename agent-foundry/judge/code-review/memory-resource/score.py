#!/usr/bin/env python3
"""Judge scorer + discriminator for the Memory-and-Resource code-review task.

The agents emit blind per-case {rating, notes} objects (they never see the gold band). This
step reads each agent's recorded per-case decisions for a run, recomputes the rating-band
accuracy authoritatively against the held-out bands in
results/code-review/memory-resource/held_out.jsonl under the contract in
judge/code-review/memory-resource/metric.json, and ranks lexicographically:

  1. Rating-Band Accuracy (correctness) — mean over held-out cases of 1.0 if the emission
     passes the strict {rating, notes} schema AND the rating is in the gold band, else 0.0.
     Primary rank key; written back as metric_value.
  2. Schema-Pass — % of cases whose emission held the bare {rating, notes} contract.
     Discriminator on a band-accuracy tie.
  3. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower better);
     tokens=0 sorts last so it can't win a tie it can't substantiate.

Ranking: rating_band_accuracy desc, schema_pass desc, tokens asc, elapsed asc. Writes each
number into the agent's emit JSON and renders
results/leaderboard-code-review-memory-resource.{json,md}.

Usage:
    python judge/code-review/memory-resource/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "code-review-memory-resource"


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def _score_agent(jf: Path, bands: dict, denom: int, score_output) -> dict | None:
    """Recompute band accuracy + schema-pass for one agent's emit file, write the enriched
    numbers back, and return a leaderboard row (or None if not a memory-resource run)."""
    meta = _load(jf, {})
    cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
    if "cases" not in cases_doc or "rating_band_accuracy" not in cases_doc:
        return None
    score_sum = schema_ok = 0.0
    for case in cases_doc.get("cases", []):
        band = bands.get(case.get("case_id"))
        if band is None:
            continue
        cells = score_output(case.get("emitted") or {}, band)
        score_sum += cells["score"]
        schema_ok += 1 if cells["schema_ok"] else 0
    band_acc = round(score_sum / denom, 4) if denom else 0.0
    schema_pct = round(100.0 * schema_ok / denom, 2) if denom else 0.0
    tokens = int((cases_doc.get("tokens") or {}).get("total_tokens", 0) or 0)
    elapsed = float(cases_doc.get("elapsed_seconds", 0.0) or 0.0)
    meta.update({
        "metric_name": "rating_band_accuracy", "metric_value": band_acc,
        "cases_scored": denom, "schema_pass_pct": schema_pct,
        "tokens_total": tokens, "elapsed_seconds": elapsed,
    })
    jf.write_text(json.dumps(meta, indent=2))
    return {"agent": meta.get("agent", jf.stem), "band_acc": band_acc,
            "schema_pct": schema_pct, "tokens": tokens, "elapsed": elapsed}


def _write_leaderboard(ws: Path, out_prefix: str, run_id: str, rows: list) -> None:
    lb_path = ws / f"{out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = "rating_band_accuracy desc, schema_pass desc, tokens asc, elapsed asc"
    lb["runs"].append({"run_id": run_id,
                       "ts": datetime.now(timezone.utc).isoformat(), "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {TASK}",
          "Rank key: **rating-band accuracy ↓ → schema-pass ↓ → tokens ↑ → elapsed ↑**",
          f"Metric: rating_band_accuracy (higher_is_better)  ·  Updated: "
          f"{datetime.now(timezone.utc).isoformat()}  ·  run: {run_id}",
          "",
          "| Rank | Agent | BandAccuracy | SchemaPass% | Tokens | Elapsed(s) |",
          "|------|-------|--------------|-------------|--------|------------|"]
    for i, r in enumerate(rows, 1):
        tok = r["tokens"] if r["tokens"] > 0 else "n/a"
        md.append(f"| {i} | {r['agent']} | {r['band_acc']:g} | {r['schema_pct']:g} | "
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
    import memresource_spec  # noqa: E402

    cases = memresource_spec.load_heldout(ws)
    bands = {c["id"]: c["gold_band"] for c in cases}
    denom = len(bands)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        row = _score_agent(jf, bands, denom, memresource_spec.score_output)
        if row is not None:
            rows.append(row)

    if not rows:
        print("[warn] no agent results found for this run.")
        return 1

    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["band_acc"], -r["schema_pct"], tok, r["elapsed"])
    rows.sort(key=keyf)

    _write_leaderboard(ws, a.out_prefix, a.run_id, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
