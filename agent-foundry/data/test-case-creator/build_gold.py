#!/usr/bin/env python3
"""Gold-set builder for the Test-Case-Creator task (n600).

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
build-manifest fixture catalogue (the agents' INPUT — manifest.json + the agent-node
spec cards under specs/) and computes the canonical correct test-case registry via the
shared pure module agents/common/testcase_spec.py, recording it as ground truth.

Fully air-gapped and offline: no network, no DummyJSON. The spec cards stand in for the
real n8n agent-node spec files a production build manifest would point at, so the whole
task is reproducible locally. DummyJSON is irrelevant here and is never touched.

Outputs (all under data/test-case-creator/):
  - specs/<name>.md       the agent-node spec cards the manifest points at (INPUT)
  - manifest.json         the build manifest (agent list: name + enabled + spec_path)
  - gold.json             the canonical correct registry + summary (ground truth)

Usage:
  python3 build_gold.py
Stdlib only. No network. Air-gapped.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECS_DIR = HERE / "specs"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import testcase_spec as tc  # noqa: E402


# Agent-node spec cards. Each exercises a different slice of the extraction contract:
# multi-step How sections, sub-lettered steps (3a/3b), every involves_* flag substring,
# Assert clauses for expected_outcome, and a Metric line carrying a "Fail:" condition.
# One enabled agent has NO How section (a PARSE_ERROR), and one agent is disabled.
SPECS = [
    {
        "name": "api-tester-demo-pagination",
        "enabled": True,
        "filename": "demo-pagination.md",
        "spec_text": """# api-tester-demo-pagination — node card

- **What:** Convert one collection's pagination contract into a read-only page plan.
- **How:**
1. Read the collection brief and parse it as JSON.
2. Send GET /products?limit=10&skip=0 and assert exactly 200 with ten items.
3. Write the page plan to results/pagination-plan.json.
4. Assert the third page skip equals twice the page size.
- **Tools:** Python json, urllib (read-only GET).
- **Metric:** Pagination Correctness Rate = correct pages / total pages. Pass: 100%. Fail: any page whose skip or limit is wrong.
""",
    },
    {
        "name": "api-tester-demo-crud",
        "enabled": True,
        "filename": "demo-crud.md",
        "spec_text": """# api-tester-demo-crud — node card

- **What:** Exercise a full create/read/update/delete lifecycle and verify DB state.
- **How:**
1. Send POST /users with a valid body and capture the new id.
2. Query the database with SELECT * FROM users WHERE id = the captured id and assert one row.
3a. Send PUT /users/{id} changing one field and assert exactly 200.
3b. Query the database again and assert the changed field persisted.
4. Send DELETE /users/{id} and assert exactly 204.
5. Record the lifecycle outcome to results/crud-log.json.
- **Tools:** Python urllib, psql.
- **Metric:** CRUD Integrity Rate = correct steps / total steps. Pass: 100%. Fail: any HTTP or DB state mismatch.
""",
    },
    {
        "name": "api-tester-demo-metrics",
        "enabled": True,
        "filename": "demo-metrics.md",
        "spec_text": """# api-tester-demo-metrics — node card

- **What:** Compute a satisfaction rate and publish a dashboard.
- **How:**
1. Read the seeded usage fixture.
2. Compute the response rate as responses ÷ recipients.
3. Publish the dashboard and emit results/metrics-dashboard.json.
- **Tools:** Python json.
- **Metric:** Response Validity = responses ÷ recipients. Pass: rate ≥ 30%. Fail: rate below 30% invalidates the report.
""",
    },
    {
        "name": "api-tester-demo-noop",
        "enabled": True,
        "filename": "demo-noop.md",
        "spec_text": """# api-tester-demo-noop — node card

- **What:** A node card with no How section, to exercise PARSE_ERROR handling.
- **Tools:** none.
- **Metric:** none. Pass: n/a.
""",
    },
    {
        "name": "api-tester-demo-disabled",
        "enabled": False,
        "filename": "demo-disabled.md",
        "spec_text": """# api-tester-demo-disabled — node card

- **What:** A disabled node, excluded from the registry by the manifest filter.
- **How:**
1. Send GET /ignored and assert exactly 200.
- **Tools:** Python urllib.
- **Metric:** Should never appear in the registry. Pass: absent. Fail: present.
""",
    },
]


def build_manifest() -> list[dict]:
    """The build manifest the harness reads (step 1): name + enabled + spec_path."""
    return [
        {"name": s["name"], "enabled": s["enabled"],
         "spec_path": f"data/test-case-creator/specs/{s['filename']}"}
        for s in SPECS
    ]


def main():
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    for s in SPECS:
        (SPECS_DIR / s["filename"]).write_text(s["spec_text"])
    (HERE / "manifest.json").write_text(json.dumps(build_manifest(), indent=2))

    enabled = [{"name": s["name"], "spec_text": s["spec_text"]} for s in SPECS if s["enabled"]]
    gold = tc.build_reference_registry(enabled)
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": gold["summary"],
         "parse_error_agents": gold["parse_error_agents"],
         "registry": gold["registry"]}, indent=2))

    # Self-check: the deterministic reference scores 100% against itself, and the count
    # assertion (registry length == total steps extracted) holds with no gaps.
    s = gold["summary"]
    scored = tc.score_registry(gold["registry"], gold["registry"])
    print(json.dumps({
        "agents_processed": s["agents_processed"],
        "agents_parse_error": s["agents_parse_error"],
        "total_steps_extracted": s["total_steps_extracted"],
        "total_test_cases_created": s["total_test_cases_created"],
        "coverage_rate": s["coverage_rate"],
        "gaps_found": s["gaps_found"], "gap_count": s["gap_count"],
        "http_call_count": s["http_call_count"], "db_query_count": s["db_query_count"],
        "file_write_count": s["file_write_count"], "assertion_count": s["assertion_count"],
        "reference_self_coverage_pct": scored["coverage_rate_pct"],
        "reference_self_field_accuracy_pct": scored["field_accuracy_pct"],
    }, indent=2))
    assert s["coverage_rate"] == 100.0 and not s["gaps_found"], "gold must be gap-free"
    assert scored["field_accuracy_pct"] == 100.0, "reference must self-score 100%"


if __name__ == "__main__":
    main()
