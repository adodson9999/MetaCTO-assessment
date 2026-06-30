#!/usr/bin/env python3
"""Judge scorer + leaderboard for the Security code-review task
(group ``code-review``, short name ``security``).

The four agents emit a blind ``{rating, notes}`` object per held-out case (they never see
the gold band). This step reads each agent's recorded per-case emissions for a run,
recomputes ``rating_band_accuracy`` authoritatively against the gold bands in
``results/code-review/security/held_out.jsonl`` under the contract in
``judge/code-review/security/metric.json``, writes the number back into each agent's
emit JSON, and ranks lexicographically:

  1. rating_band_accuracy (correctness) — mean over cases of (strict {rating,notes} schema
     passes AND rating in the inclusive gold band). Primary rank key; written as metric_value.
  2. schema_pass_pct — % of cases whose emission passed the strict schema. Discriminator on
     a band-accuracy tie (rewards the agent that always emits the exact contract).
  3. Efficiency — total LLM tokens (lower better) then wall-clock elapsed (lower better);
     tokens=0 (framework didn't expose usage) sorts last so it can't win a tie it can't
     substantiate.

Ranking: rating_band_accuracy desc, schema_pass_pct desc, tokens asc, elapsed asc.
Renders results/leaderboard-security.{json,md}.

Determinism / saturation guard (the project's hard rule): the metric is pure-Python and
identical for all four agents, and an empty or malformed emission scores 0.0 — it can never
saturate to 100%. ``--oracle-selftest`` proves both halves with no model: the reference
oracle scores 1.0 and an empty emission scores 0.0.

Usage:
    python judge/code-review/security/score.py --workspace . --run-id <id>
    python judge/code-review/security/score.py --oracle-selftest   # no model needed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GROUP = "code-review"
SHORT = "security"
TASK = "security"
AGENTS = ("langgraph", "crewai", "claude_sdk", "code-review-security")


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def _import_spec(ws: Path):
    sys.path.insert(0, str(ws / "agents" / "common"))
    import security_spec  # noqa: PLC0415
    return security_spec


# --------------------------------------------------------------------------- #
# Scoring one agent's recorded run
# --------------------------------------------------------------------------- #
def _score_agent(cases_path: Path, golds: dict, spec) -> dict | None:
    """Recompute rating_band_accuracy for one agent's recorded ``<agent>.cases.json``,
    enrich + return a leaderboard row, or None if the file is not a security run."""
    doc = _load(cases_path, {})
    if not doc or "cases" not in doc or doc.get("metric_name") != "rating_band_accuracy":
        return None
    total = correct = schema_ok = 0
    for case in doc.get("cases", []):
        gold = golds.get(case.get("case_id"))
        if gold is None:
            continue
        total += 1
        cells = spec.score_output(case.get("emitted") or {}, gold)
        correct += 1 if cells["score"] >= 1.0 else 0
        schema_ok += 1 if cells["schema_ok"] else 0
    band_accuracy = round(correct / total, 4) if total else 0.0
    schema_pct = round(100.0 * schema_ok / total, 2) if total else 0.0
    tokens = int((doc.get("tokens") or {}).get("total_tokens", 0) or 0)
    elapsed = float(doc.get("elapsed_seconds", 0.0) or 0.0)
    return {
        "agent": doc.get("agent", cases_path.stem.replace(".cases", "")),
        "rating_band_accuracy": band_accuracy,
        "schema_pass_pct": schema_pct,
        "cases_total": total,
        "tokens": tokens,
        "elapsed_seconds": elapsed,
    }


def _rank_key(row: dict) -> tuple:
    # higher accuracy, higher schema%, then fewer tokens (0 -> +inf), then less elapsed.
    tokens = row["tokens"] if row["tokens"] > 0 else float("inf")
    return (-row["rating_band_accuracy"], -row["schema_pass_pct"], tokens, row["elapsed_seconds"])


def score_run(ws: Path, run_id: str) -> dict:
    spec = _import_spec(ws)
    cases = spec.load_heldout(ws)
    golds = {c["id"]: c["gold_band"] for c in cases}
    run_dir = ws / "results" / "runs" / run_id

    rows: list[dict] = []
    for cf in sorted(run_dir.glob("*.cases.json")):
        row = _score_agent(cf, golds, spec)
        if row is None:
            continue
        rows.append(row)
        # write the authoritative number back into the agent's emit JSON.
        emit_path = run_dir / f"{row['agent']}.json"
        emit = _load(emit_path, {})
        if emit:
            emit.update({
                "metric_name": "rating_band_accuracy",
                "metric_value": row["rating_band_accuracy"],
                "schema_pass_pct": row["schema_pass_pct"],
            })
            emit_path.write_text(json.dumps(emit, indent=2))

    rows.sort(key=_rank_key)
    leaderboard = {
        "task": f"{GROUP} / {SHORT}",
        "run_id": run_id,
        "metric_name": "rating_band_accuracy",
        "ranked": rows,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    out_json = ws / "results" / f"leaderboard-{TASK}.json"
    out_json.write_text(json.dumps(leaderboard, indent=2))
    _render_md(ws, leaderboard)
    return leaderboard


def _render_md(ws: Path, lb: dict) -> None:
    lines = [
        f"# Leaderboard — {lb['task']}",
        "",
        f"Run `{lb['run_id']}` · metric **rating_band_accuracy** (higher is better)",
        "",
        "| # | agent | rating_band_accuracy | schema_pass_pct | cases | tokens | elapsed_s |",
        "|---|-------|----------------------|-----------------|-------|--------|-----------|",
    ]
    for i, r in enumerate(lb["ranked"], 1):
        lines.append(
            f"| {i} | {r['agent']} | {r['rating_band_accuracy']} | "
            f"{r['schema_pass_pct']}% | {r['cases_total']} | {r['tokens']} | "
            f"{r['elapsed_seconds']} |"
        )
    (ws / "results" / f"leaderboard-{TASK}.md").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Oracle self-test (no model): proves the metric is sound and cannot saturate.
# --------------------------------------------------------------------------- #
def oracle_selftest(ws: Path) -> int:
    spec = _import_spec(ws)
    cases = spec.load_heldout(ws)
    if not cases:
        print("FAIL: no held-out cases loaded", file=sys.stderr)
        return 1

    # 1. The reference oracle must score 1.0 on every case.
    oracle_score = sum(
        spec.score_output(spec.build_reference_decision(c), c["gold_band"])["score"]
        for c in cases
    ) / len(cases)
    # 2. An empty emission must score 0.0 on every case (saturation guard).
    empty_score = sum(
        spec.score_output({}, c["gold_band"])["score"] for c in cases
    ) / len(cases)
    # 3. A wrong-band but schema-valid emission must also score 0.0 (band is enforced).
    def _wrong(c):
        lo, hi = c["gold_band"]
        wrong_rating = 100 if hi < 100 else 0  # guaranteed outside the band
        return {"rating": wrong_rating, "notes": "deliberately out of band"}
    wrong_score = sum(
        spec.score_output(_wrong(c), c["gold_band"])["score"] for c in cases
    ) / len(cases)

    print(f"oracle_score={oracle_score} (want 1.0)")
    print(f"empty_score={empty_score} (want 0.0)")
    print(f"wrong_band_score={wrong_score} (want 0.0)")
    ok = oracle_score == 1.0 and empty_score == 0.0 and wrong_score == 0.0
    print("ORACLE SELF-TEST PASSED" if ok else "ORACLE SELF-TEST FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Security judge scorer / leaderboard.")
    ap.add_argument("--workspace", type=Path, default=Path("."))
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--oracle-selftest", action="store_true",
                    help="prove the metric scores the oracle 1.0 and empty/out-of-band 0.0 (no model)")
    args = ap.parse_args(argv[1:])
    ws = args.workspace.resolve()

    if args.oracle_selftest:
        return oracle_selftest(ws)
    if not args.run_id:
        print("error: --run-id is required unless --oracle-selftest", file=sys.stderr)
        return 2
    lb = score_run(ws, args.run_id)
    print(f"ranked {len(lb['ranked'])} agent(s); wrote results/leaderboard-{TASK}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
