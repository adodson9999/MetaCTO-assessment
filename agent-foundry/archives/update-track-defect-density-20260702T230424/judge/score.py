#!/usr/bin/env python3
"""Judge scorer — accuracy layer for the track-defect-density task.

The agents emit their dashboard reports blind (they never see the gold). This step
reads each agent's recorded per-field results for a run, compares them to
data/track-defect-density/gold.json under the contract in
judge/track-defect-density/metric.json, computes Defect-Density Report Accuracy, and
writes that number back as each agent's metric_value. Then scripts/judge_score.py
ranks and updates the leaderboard.

Usage:
    python judge/track-defect-density/score.py --workspace . --run-id <id>
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    sys.path.insert(0, str(ws / "agents" / "common"))
    import defectdensity_spec as ddspec  # noqa: E402

    gold = _load(ws / "data" / "track-defect-density" / "gold.json", {"sprints": []})
    gold_by_sprint = {s["sprint_name"]: s["record"] for s in gold.get("sprints", [])}
    denom = len(gold_by_sprint) * len(ddspec.FIELDS)
    run_dir = ws / "results" / "runs" / a.run_id

    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith(".cases.json"):
            continue
        meta = _load(jf, {})
        agent = meta.get("agent", jf.stem)
        cases_doc = _load(Path(meta.get("raw_output_path", "")), {})
        if "sprints" not in cases_doc:
            continue  # not a defect-density run (e.g. a different task's emit)

        matches = 0
        for sp in cases_doc.get("sprints", []):
            gold_rec = gold_by_sprint.get(sp["sprint"])
            if not gold_rec:
                continue
            emitted = sp.get("emitted_report", {})
            checks = ddspec.evaluate(emitted, gold_rec)
            matches += sum(1 for ok in checks.values() if ok)

        accuracy = round(100.0 * matches / denom, 2) if denom else 0.0
        meta["metric_name"] = "defect_density_report_accuracy"
        meta["metric_value"] = accuracy
        meta["accuracy_matches"] = matches
        meta["accuracy_denominator"] = denom
        jf.write_text(json.dumps(meta, indent=2))
        rows.append((agent, accuracy, matches, denom,
                     cases_doc.get("defect_density_report_accuracy_pct")))

    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"Defect-Density Report Accuracy (denominator = {denom} gold cells)")
    print(f"{'agent':36} {'accuracy%':>9} {'matches':>8} {'harness%':>9}")
    for agent, acc, m, d, harness in rows:
        print(f"{agent:36} {acc:>9} {m:>8} {str(harness):>9}")
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
