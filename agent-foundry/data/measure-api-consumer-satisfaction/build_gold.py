#!/usr/bin/env python3
"""Gold-set builder for the Measure-API-Consumer-Satisfaction task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
documented NPS-survey-measurement contract (nps_spec.json, the INPUT the harness briefs
the agent from), derives the canonical CORRECT measurement plan, executes it against the
LOCAL seeded usage fixture (read-only SQLite query for the 90-day recipients + the
collected survey responses), computes the published dashboard, and records the REAL
observed scenario tokens per dataset as the gold ground truth.

Two datasets:
  - current : the live quarter (headline result, the ranking set).
  - q_prev  : the held-out quarter (evolution gate; agents never see it during ranking).

The plan-structure scenarios are checked against fixed documented ideals; the computed
dashboard scenarios are the canonical truth by construction. The fixture + reference plan
are internally consistent, so empirical "plan accuracy" is 100% — a clean positive. Any
non-100% row is a genuine fixture/contract defect, not an agent failure. DummyJSON is
never used or modified.

Outputs (under data/measure-api-consumer-satisfaction/):
  - nps_spec.json          the documented contract (INPUT to the harness brief)
  - gold/<dataset>.json    per-dataset gold scenarios + dashboard
  - gold.json              consolidated gold table + empirical accuracy summary

Usage:
  python3 build_gold.py
Stdlib + (optional) scikit-learn for clustering. Air-gapped; no network. No DummyJSON.
"""
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
WS = HERE.parents[1]

sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "tools" / "satisfaction-fixture"))
import nps_spec  # noqa: E402
import seed as fixture  # noqa: E402

DATASETS = list(fixture.DATASETS)


def build_contract() -> dict:
    """The documented contract the harness briefs the agent from (no seeded answers)."""
    plan = nps_spec.build_reference_plan()
    return {
        "title": "API Consumer Satisfaction (NPS) survey-measurement contract",
        "description": "A purpose-built, air-gapped local usage fixture seeded with an "
                       "api_request_logs table + collected survey responses (DummyJSON is "
                       "never used or modified). Agents render the documented contract as a "
                       "measurement plan; ground truth is the canonical plan executed "
                       "against the seeded fixture.",
        "target": "tools/satisfaction-fixture (local seeded SQLite)",
        "recipient_window_days": plan["recipient_window_days"],
        "survey_questions": plan["survey_questions"],
        "collection_window_days": plan["collection_window_days"],
        "score_bands": plan["score_bands"],
        "nps_formula": plan["nps_formula"],
        "validity_min_response_rate_pct": plan["validity_min_response_rate_pct"],
        "clustering": plan["clustering"],
        "dashboard_fields": plan["dashboard_fields"],
    }


def _fixture_inputs(dataset: str, window: int):
    db_path = WS / "tools" / "satisfaction-fixture" / f"usage_{dataset}.db"
    fixture.build_db(db_path, dataset)
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.execute(
            "SELECT DISTINCT user_id FROM api_request_logs "
            "WHERE day_offset >= 0 AND day_offset <= ? ORDER BY user_id", (window,))
        recipients = [r[0] for r in cur.fetchall()]
        cur = con.execute(
            "SELECT user_id, score, submit_day, painpoint, improvement, other "
            "FROM survey_responses")
        responses = [{"user_id": r[0], "score": r[1], "submit_day": r[2],
                      "painpoint": r[3], "improvement": r[4], "other": r[5]}
                     for r in cur.fetchall()]
    finally:
        con.close()
    return recipients, responses


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    contract = build_contract()
    spec = {"contract": contract, "datasets": DATASETS,
            "ranking_dataset": "current", "held_out_dataset": "q_prev"}
    (HERE / "nps_spec.json").write_text(json.dumps(spec, indent=2))

    ref_plan = nps_spec.build_reference_plan()
    datasets_out = []
    total_scenarios = correct_scenarios = 0
    findings = []

    for ds in DATASETS:
        window = ref_plan["recipient_window_days"]
        recipients, responses = _fixture_inputs(ds, window)
        period = fixture.survey_period(ds, window)
        dashboard = nps_spec.compute_dashboard(ref_plan, recipients, responses, period)
        observed = nps_spec.evaluate(ref_plan, dashboard)

        # First pass: fixed plan-structure ideals + raw computed tokens (no gold yet).
        scenarios = []
        for label in nps_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            # gold token IS the canonical observed token; for fixed scenarios the
            # documented ideal must equal it (else the contract is internally broken).
            fixed_ideal = nps_spec._IDEAL_RAW[label]
            ok = True
            if fixed_ideal != "<gold>":
                ok = (tok == fixed_ideal)
                if not ok:
                    findings.append({"dataset": ds, "scenario": label,
                                     "ideal": fixed_ideal, "observed": tok})
            scenarios.append({"scenario": label,
                              "ideal": (fixed_ideal if fixed_ideal != "<gold>" else tok),
                              "observed_token": tok, "plan_correct": ok})
            total_scenarios += 1
            correct_scenarios += 1 if ok else 0

        rec = {"dataset": ds, "reference_plan": ref_plan, "recipients": len(recipients),
               "dashboard": dashboard, "scenarios": scenarios}
        (GOLD_DIR / f"{ds}.json").write_text(json.dumps(rec, indent=2))
        datasets_out.append(rec)

    rate = round(100.0 * correct_scenarios / total_scenarios, 2) if total_scenarios else None
    summary = {
        "target": "tools/satisfaction-fixture (local seeded SQLite; no DummyJSON)",
        "datasets": DATASETS,
        "scenarios_per_dataset": len(nps_spec.SCENARIO_LABELS),
        "total_scenarios": total_scenarios,
        "plan_correct_scenarios": correct_scenarios,
        "empirical_plan_accuracy_pct": rate,
        "clustering_backend": "sklearn" if nps_spec._use_sklearn() else "stdlib",
        "qa_findings": findings,
        "headline_current": {
            "nps_score": datasets_out[0]["dashboard"]["nps_score"],
            "statistical_validity": datasets_out[0]["dashboard"]["statistical_validity"],
            "response_rate_pct": datasets_out[0]["dashboard"]["response_rate_pct"],
            "top_3_theme_sizes": [t["count"] for t in datasets_out[0]["dashboard"]["top_3_themes"]],
        },
        "note": "Ground truth = the canonical correct plan executed against the seeded "
                "fixture. The fixture + reference plan are internally consistent, so "
                "empirical plan accuracy is 100% (a clean positive). Fidelity-to-gold is "
                "what scores each framework's emitted plan. DummyJSON is never used or "
                "modified.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "datasets": datasets_out}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
