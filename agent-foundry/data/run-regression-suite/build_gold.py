#!/usr/bin/env python3
"""Gold-set builder for the API "Run Regression Suite" task.

This is NOT one of the four agents. It is the deterministic *reference*: it publishes
the agents' briefing input (regression_spec.json) from the build-pair catalogue and
the local artifact fixtures, then derives the canonical CORRECT seven-field regression
report for every build pair by parsing the same two artifacts the agents receive.

Why fixtures: DummyJSON exposes no CI build-result-artifact surface and must not be
modified, so the build N-1 / build N "test result artifacts" are local, air-gapped
fixtures (Newman JUnit XML, pytest JUnit XML, Jest --json, pytest-json-report). The
agents are ranked on how faithfully their own reports reproduce these gold reports.
DummyJSON itself is tested AS-IS and never modified; the only (optional) network call
is a read-only GET <target>/health to mirror the task's deployment-confirmation step.

Outputs (all under data/run-regression-suite/):
  - regression_spec.json     the build-pair catalogue the agents are briefed from (INPUT)
  - gold/<pair>.json         per-pair gold report
  - gold.json                consolidated gold reports + regression-rate summary

Usage:
  [BASE_URL=http://localhost:8899] python3 build_gold.py
Stdlib only. Air-gapped (no network beyond the optional read-only /health GET).
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
BUILDS_DIR = HERE / "builds"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")

# Shared comparison structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import regression_spec  # noqa: E402


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from: the build-pair catalogue with the
    reporter format, the two build identifiers, and the artifact file names — WITHOUT
    the answer report."""
    return {
        "title": "Run Regression Suite — build-pair catalogue (api-tester)",
        "description": "Each entry is one (build N-1, build N) test-result-artifact pair in a "
                       "named reporter format. Agents parse both artifacts and emit the seven-field "
                       "regression report; ground truth is the deterministic comparison in "
                       "regression_spec. DummyJSON is read-only and never modified; the deployment "
                       "health check is a read-only GET /health against the local target.",
        "target": BASE_URL,
        "builds_subdir": "builds",
        "build_pairs": regression_spec.BUILD_PAIRS,
    }


def optional_health() -> dict:
    """Read-only GET /health (mirrors the task's deployment confirmation). Non-fatal:
    the gold reports are computed from the fixtures, not the API."""
    url = f"{BASE_URL}/health"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as r:
            return {"endpoint": "/health", "status": r.getcode(), "deployment_confirmed": r.getcode() == 200}
    except urllib.error.HTTPError as e:
        return {"endpoint": "/health", "status": e.code, "deployment_confirmed": e.code == 200}
    except Exception as e:  # noqa
        return {"endpoint": "/health", "status": -1, "deployment_confirmed": False, "note": str(e)}


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (HERE / "regression_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    rate_summary = []
    for p in regression_spec.BUILD_PAIRS:
        prev_text = (BUILDS_DIR / p["pair"] / p["prev_file"]).read_text()
        curr_text = (BUILDS_DIR / p["pair"] / p["curr_file"]).read_text()
        prev_parsed = regression_spec.parse_artifact(prev_text, p["format"])
        curr_parsed = regression_spec.parse_artifact(curr_text, p["format"])
        gold = regression_spec.build_reference_report(
            prev_parsed, curr_parsed, p["prev_build_id"], p["build_id"])
        rate = regression_spec.regression_rate(gold)

        rec = {
            "pair": p["pair"], "format": p["format"], "note": p.get("note", ""),
            "gold_report": gold,
            "regression_rate_pct": rate,
            "would_block_deployment": gold["overall_status"] == "fail",
        }
        (GOLD_DIR / f"{p['pair']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)
        rate_summary.append({"pair": p["pair"], "build_n": p["build_id"],
                             "regression_rate_pct": rate,
                             "overall_status": gold["overall_status"]})

    blocked = sorted({r["build_n"] for r in rate_summary if r["overall_status"] == "fail"})
    summary = {
        "target": BASE_URL,
        "deployment_health": optional_health(),
        "build_pairs": len(regression_spec.BUILD_PAIRS),
        "fields_per_pair": len(regression_spec.REPORT_FIELDS),
        "total_gold_fields": len(regression_spec.BUILD_PAIRS) * len(regression_spec.REPORT_FIELDS),
        "regression_rates": rate_summary,
        "builds_that_must_block_deployment": blocked,
        "note": "Ground truth = the deterministic seven-field regression report per build pair "
                "(passed-in-N-1-then-failed-in-N detection). Regression Rate is fixture-determined; "
                "the genuine finding is which build-N deployments must be BLOCKED for having any "
                "regression (pass = exactly 0%, no tolerance). Framework ranking is "
                "Regression-Report Fidelity (agent report vs gold), which is API-independent.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "pairs": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
