#!/usr/bin/env python3
"""Gold-set builder for the Track-Defect-Density task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the sprint fixture catalogue (the agents' INPUT, defectdensity_spec.json)
and computes the canonical correct dashboard record per sprint via the shared pure
module agents/common/defectdensity_spec.py, recording it as ground truth.

Fully air-gapped and offline: no Jira, no Git, no network, no DummyJSON. The sprint
fixtures stand in for "the Jira REST query result + git diff --numstat output" so the
whole task is reproducible locally. DummyJSON is irrelevant here and never touched.

Outputs (all under data/track-defect-density/):
  - defectdensity_spec.json   the sprint fixtures the agents are briefed from (INPUT)
  - gold/<sprint>.json        per-sprint gold record + the inputs it was computed from
  - gold.json                 consolidated gold table + field/sprint summary

Usage:
  python3 build_gold.py
Stdlib only. No network. Air-gapped.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import defectdensity_spec as dd  # noqa: E402


def numstat(rows: list[tuple[int, int, str]]) -> str:
    """Render (insertions, deletions, path) rows as a `git diff --numstat` block."""
    return "\n".join(f"{ins}\t{dele}\t{path}" for ins, dele, path in rows)


# Six sprint fixtures, chosen to exercise every flag path and the test-file filter.
# Per-file numstat rows include *test.go / *test.py / *.spec.ts entries that MUST be
# excluded from lines_changed; the non-test rows sum to the L_CHANGED used below.
SPRINTS = [
    {
        # All-clear: density on target, deviation 0, no P1.
        "sprint_name": "Sprint-25",
        "sprint_start_date": "2026-04-06",
        "sprint_end_date": "2026-04-17",
        "jira_issues": [
            {"key": "API-201", "priority": "High"},
            {"key": "API-202", "priority": "Medium"},
            {"key": "API-203", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (900, 300, "src/api/users.go"),       # 1200 non-test
            (500, 300, "src/api/orders.go"),       # 800 non-test  -> L=2000
            (400, 100, "src/api/users_test.go"),   # excluded (test.go)
        ]),
        "prev_density_1": 1.4, "prev_density_2": 1.6, "prev_density_3": 1.5,
    },
    {
        # Density spike: deviation >20% -> alert, no P1.
        "sprint_name": "Sprint-26",
        "sprint_start_date": "2026-04-20",
        "sprint_end_date": "2026-05-01",
        "jira_issues": [
            {"key": "API-210", "priority": "High"},
            {"key": "API-211", "priority": "High"},
            {"key": "API-212", "priority": "High"},
            {"key": "API-213", "priority": "Medium"},
            {"key": "API-214", "priority": "Medium"},
            {"key": "API-215", "priority": "Medium"},
            {"key": "API-216", "priority": "Low"},
            {"key": "API-217", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (1200, 500, "src/api/payments.go"),    # 1700 non-test
            (200, 100, "src/api/billing.go"),       # 300 non-test -> L=2000
            (300, 50, "src/api/billing_test.py"),   # excluded (test.py)
            (100, 20, "ui/cart.spec.ts"),           # excluded (.spec.ts)
        ]),
        "prev_density_1": 2.0, "prev_density_2": 2.4, "prev_density_3": 2.2,
    },
    {
        # P1 present, density fine: alert false but a P1 was filed (escalation via p1_count>0).
        "sprint_name": "Sprint-27",
        "sprint_start_date": "2026-05-04",
        "sprint_end_date": "2026-05-15",
        "jira_issues": [
            {"key": "API-220", "priority": "Highest"},
            {"key": "API-221", "priority": "High"},
            {"key": "API-222", "priority": "Medium"},
            {"key": "API-223", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (1500, 500, "src/api/auth.go"),         # 2000 non-test
            (300, 200, "src/api/session.go"),        # 500 non-test -> L=2500
            (600, 200, "src/api/auth_test.go"),      # excluded
        ]),
        "prev_density_1": 1.5, "prev_density_2": 1.7, "prev_density_3": 1.6,
    },
    {
        # Both: density spike AND P1 defects.
        "sprint_name": "Sprint-28",
        "sprint_start_date": "2026-05-18",
        "sprint_end_date": "2026-05-29",
        "jira_issues": [
            {"key": "API-230", "priority": "Highest"},
            {"key": "API-231", "priority": "Highest"},
            {"key": "API-232", "priority": "High"},
            {"key": "API-233", "priority": "High"},
            {"key": "API-234", "priority": "High"},
            {"key": "API-235", "priority": "High"},
            {"key": "API-236", "priority": "Medium"},
            {"key": "API-237", "priority": "Medium"},
            {"key": "API-238", "priority": "Medium"},
            {"key": "API-239", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (1500, 500, "src/api/orders.go"),       # 2000 non-test
            (300, 200, "src/api/inventory.go"),      # 500 non-test -> L=2500
            (800, 300, "src/api/orders_test.go"),    # excluded
            (120, 30, "ui/checkout.spec.ts"),        # excluded
        ]),
        "prev_density_1": 2.5, "prev_density_2": 2.7, "prev_density_3": 2.6,
    },
    {
        # Improvement: negative trend, deviation well below threshold, no flags.
        "sprint_name": "Sprint-29",
        "sprint_start_date": "2026-06-01",
        "sprint_end_date": "2026-06-12",
        "jira_issues": [
            {"key": "API-240", "priority": "Medium"},
            {"key": "API-241", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (1200, 300, "src/api/profile.go"),      # 1500 non-test
            (400, 100, "src/api/avatar.go"),         # 500 non-test -> L=2000
            (200, 50, "src/api/profile_test.py"),    # excluded
        ]),
        "prev_density_1": 2.0, "prev_density_2": 1.8, "prev_density_3": 1.9,
    },
    {
        # Boundary: deviation == exactly 20.00 -> alert FALSE (strictly-greater rule);
        # heavy test-file presence to stress the exclusion filter.
        "sprint_name": "Sprint-30",
        "sprint_start_date": "2026-06-15",
        "sprint_end_date": "2026-06-26",
        "jira_issues": [
            {"key": "API-250", "priority": "High"},
            {"key": "API-251", "priority": "High"},
            {"key": "API-252", "priority": "Medium"},
            {"key": "API-253", "priority": "Medium"},
            {"key": "API-254", "priority": "Low"},
            {"key": "API-255", "priority": "Low"},
        ],
        "diff_numstat": numstat([
            (1500, 500, "src/api/search.go"),       # 2000 non-test
            (300, 200, "src/api/index.go"),          # 500 non-test -> L=2500
            (900, 300, "src/api/search_test.go"),    # excluded
            (400, 100, "src/api/index_test.py"),     # excluded
            (200, 50, "ui/search.spec.ts"),          # excluded
        ]),
        "prev_density_1": 1.9, "prev_density_2": 2.1, "prev_density_3": 2.0,
    },
]


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Carries each sprint's raw Jira bug
    list, git numstat block, and the three preceding densities — WITHOUT the answer."""
    return {
        "title": "Sprint defect-density fixtures (authored for the Track-Defect-Density task)",
        "description": (
            "Each sprint stands in for the Jira REST query result (component=API, "
            "issuetype=Bug, created in the sprint window) plus `git diff --numstat` over "
            "the API source. Agents compute the published dashboard record; ground truth "
            "is the deterministic reference in agents/common/defectdensity_spec.py. Fully "
            "air-gapped: no Jira, no Git, no network, no DummyJSON."),
        "test_file_suffixes": list(dd.TEST_FILE_SUFFIXES),
        "alert_deviation_threshold_pct": dd.ALERT_DEVIATION_THRESHOLD,
        "fields": list(dd.FIELDS),
        "sprints": SPRINTS,
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (HERE / "defectdensity_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total_fields = correct_self = 0  # self-check: reference vs itself = 100% (sanity)
    for cfg in SPRINTS:
        record = dd.build_reference_record(cfg)
        lines = dd.lines_changed(dd.parse_numstat(cfg["diff_numstat"]))
        rec = {
            "sprint_name": cfg["sprint_name"],
            "inputs": {
                "total_defects": len(cfg["jira_issues"]),
                "lines_changed_non_test": lines,
                "prev_density_1": cfg["prev_density_1"],
                "prev_density_2": cfg["prev_density_2"],
                "prev_density_3": cfg["prev_density_3"],
            },
            "record": record,
        }
        (GOLD_DIR / f"{cfg['sprint_name']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)
        checks = dd.evaluate(record, record)
        total_fields += len(checks)
        correct_self += sum(1 for ok in checks.values() if ok)

    summary = {
        "sprints": len(SPRINTS),
        "fields_per_sprint": len(dd.FIELDS),
        "total_cells": total_fields,
        "reference_self_consistency_pct": round(100.0 * correct_self / total_fields, 2),
        "note": (
            "Ground truth = the deterministic reference record per sprint. The metric "
            "ranks agents on how many of the 10 published fields per sprint they "
            "reproduce. Fixtures cover: all-clear, density-spike alert, P1-only, "
            "alert+P1, improving negative-trend, and an exactly-20%% boundary (alert "
            "false) with a heavy test-file-exclusion case."),
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "sprints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    for rec in consolidated:
        r = rec["record"]
        print(f"{r['sprint_name']:10} dd={r['defect_density']:>5} roll={r['rolling_avg_3_sprint']:>5} "
              f"dev={r['deviation_pct']:>7} alert={str(r['alert_flag']):>5} "
              f"P1-4={r['p1_count']}/{r['p2_count']}/{r['p3_count']}/{r['p4_count']} "
              f"trend={r['trend']}")


if __name__ == "__main__":
    main()
