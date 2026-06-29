#!/usr/bin/env python3
"""Deterministic GOLD reference + fixtures for the API "Bug Reporter" task (general
position, "n602"). NOT one of the four agents — it is the canonical truth the judge
scores fidelity against.

It materialises the local, air-gapped fixture bundle the agents read (a pipeline-summary
of nine non-PASSED agents covering every severity rule + two excluded PASSED agents, the
test-case registry, and the Postman collection), then derives the canonical CORRECT
five-key DECISION for every failure through the SAME shared logic the agents must
reproduce (bugreport_spec.build_reference_decision).

No LLM, no server, no HTTP, no subprocess — n602 is a pure JSON->JSON transform.
DummyJSON is never used and never modified. The fixture has NO [database], so DB_AVAILABLE
is false and the DB-dump artifact is null for every report (so a fully-complete report
scores 9/10 — completeness ~90%, comfortably above the 80% gate).

Rebuild any time:
    python data/bug-reporter/build_gold.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))
import bugreport_spec  # noqa: E402

OUT_DIR = WS / "data" / "bug-reporter"
SPEC = json.loads((OUT_DIR / "bugreport_spec.json").read_text())

# --------------------------------------------------------------------------- #
# The failure catalogue — one pipeline run whose non-PASSED agents exercise every
# severity rule R1..R9 exactly once, plus two PASSED agents that MUST be excluded.
# --------------------------------------------------------------------------- #
FAILURES = [
    # R1 CRITICAL — spec_path contains "authentication"
    {"agent_name": "authentication-flow-tester",
     "spec_path": "agents/test-authentication-flows/authentication-flow-tester.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "authentication-flow-tester", "status": "fail", "checks": 7}',
     "stderr": "AssertionError: expected 200 on valid login but got 401\n  at verify_login"},
    # R2 CRITICAL — stderr carries a security substring ("TLS handshake")
    {"agent_name": "tls-enforcer",
     "spec_path": "agents/test-ssl-tls-enforcement/tls-enforcer.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "tls-enforcer", "status": "fail"}',
     "stderr": "TLS handshake failed: server negotiated a weak cipher (TLS_RSA_WITH_RC4)"},
    # R3 CRITICAL — TIMED_OUT and spec_path contains "pipeline"
    {"agent_name": "ci-gatekeeper",
     "spec_path": "agents/run-cicd-pipeline/ci-gatekeeper.prompt.md",
     "status": "TIMED_OUT", "exit_code": 124, "stdout": "", "stderr": ""},
    # R4 HIGH — FAILED with stdout JSON false_acceptance_rate > 0
    {"agent_name": "biometric-far-checker",
     "spec_path": "agents/verify-biometric-matching/biometric-far-checker.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "biometric-far-checker", "false_acceptance_rate": 0.043, "status": "fail"}',
     "stderr": "biometric match exceeded tolerance"},
    # R5 HIGH — FAILED with stderr "database"/"connection refused"/"500"
    {"agent_name": "crud-integrity-prober",
     "spec_path": "agents/verify-crud-operation-integrity/crud-integrity-prober.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "crud-integrity-prober", "status": "error"}',
     "stderr": "psycopg2.OperationalError: database connection refused (500) during CRUD write"},
    # R6 HIGH — MALFORMED (exit 0, stdout not valid JSON)
    {"agent_name": "schema-response-validator",
     "spec_path": "agents/validate-json-schema-responses/schema-response-validator.prompt.md",
     "status": "MALFORMED", "exit_code": 0,
     "stdout": "Traceback (most recent call last):\n  RuntimeError: validator crashed mid-run",
     "stderr": "warning: emitted non-JSON to stdout"},
    # R7 MEDIUM — FAILED with stderr "404"/"pagination"
    {"agent_name": "pagination-checker",
     "spec_path": "agents/test-pagination-behavior/pagination-checker.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "pagination-checker", "status": "fail"}',
     "stderr": "AssertionError: 404 on page 3 — pagination offset computed incorrectly"},
    # R8 MEDIUM — TIMED_OUT, agent_name has no "pipeline"
    {"agent_name": "webhook-delivery-tester",
     "spec_path": "agents/test-webhook-delivery/webhook-delivery-tester.prompt.md",
     "status": "TIMED_OUT", "exit_code": 124,
     "stdout": '{"agent": "webhook-delivery-tester", "status": "in_pro',
     "stderr": ""},
    # R9 LOW — FAILED, matches none of the keyword lists
    {"agent_name": "error-clarity-checker",
     "spec_path": "agents/verify-error-message-clarity/error-clarity-checker.prompt.md",
     "status": "FAILED", "exit_code": 1,
     "stdout": '{"agent": "error-clarity-checker", "status": "fail"}',
     "stderr": "AssertionError: message wording differs from the expected copy"},
]

PASSED = [
    {"agent_name": "health-check-prober",
     "spec_path": "agents/verify-response-status-codes/health-check-prober.prompt.md",
     "status": "PASSED", "exit_code": 0,
     "stdout": '{"agent": "health-check-prober", "status": "pass"}', "stderr": ""},
    {"agent_name": "version-checker",
     "spec_path": "agents/validate-api-versioning-behavior/version-checker.prompt.md",
     "status": "PASSED", "exit_code": 0,
     "stdout": '{"agent": "version-checker", "status": "pass"}', "stderr": ""},
]

# --------------------------------------------------------------------------- #
# Registry — every FAILED agent has >=1 test case; HTTP cases are split between those
# already present in the collection and those that must trigger a constructed new_item.
# IN_COLLECTION tc_ids are the ones the Postman collection below carries.
# --------------------------------------------------------------------------- #
def _tc(idx, tc_id, agent, http, text, assertion=True,
        outcome="The asserted response is returned.", fail="The assertion does not hold."):
    return {"index": idx, "tc_id": tc_id, "agent": agent, "step_id": f"{tc_id}-s1",
            "involves_http_call": http, "involves_assertion": assertion,
            "step_text": text, "expected_outcome": outcome, "fail_condition": fail}


REGISTRY = [
    # authentication-flow-tester
    _tc(1, "tc-auth-001", "authentication-flow-tester", True,
        "Send POST /auth/login with a valid body and Assert response code equals 200."),
    _tc(2, "tc-auth-002", "authentication-flow-tester", True,
        "GET /auth/me with Authorization header, Asserts response code is exactly 401 when the token is missing."),
    _tc(3, "tc-auth-003", "authentication-flow-tester", False,
        "Inspect the in-memory session table for a stale entry.", assertion=False),
    # tls-enforcer
    _tc(4, "tc-tls-001", "tls-enforcer", True,
        "GET /secure/ping over TLS 1.2 and Assert response code = 200."),
    # ci-gatekeeper (pipeline, timed out)
    _tc(5, "tc-pipe-001", "ci-gatekeeper", True,
        "POST /pipeline/run with body = a manifest and Asserts exactly 202."),
    # biometric-far-checker
    _tc(6, "tc-bio-001", "biometric-far-checker", True,
        "POST /biometric/verify with a valid body, Assert response code equals 200."),
    # crud-integrity-prober
    _tc(7, "tc-crud-001", "crud-integrity-prober", True,
        "POST /resources with body: a new resource and Asserts exactly 201."),
    _tc(8, "tc-crud-002", "crud-integrity-prober", True,
        "DELETE /resources/42 with Authorization header, Asserts response code = 204."),
    # schema-response-validator
    _tc(9, "tc-schema-001", "schema-response-validator", True,
        "GET /products/1 and Assert response code is exactly 200."),
    # pagination-checker
    _tc(10, "tc-page-001", "pagination-checker", True,
        "GET /products with X-Correlation-ID, Asserts response code equals 200."),
    _tc(11, "tc-page-002", "pagination-checker", False,
        "Compute the expected page boundaries locally.", assertion=False),
    # webhook-delivery-tester
    _tc(12, "tc-webhook-001", "webhook-delivery-tester", True,
        "POST /webhooks/register with body = a callback URL and Asserts exactly 201."),
    # error-clarity-checker
    _tc(13, "tc-clarity-001", "error-clarity-checker", True,
        "GET /products/999999 → assert 404."),
]

# tc_ids that already exist in the Postman collection (so they yield an existing-item ref;
# the rest of the HTTP cases yield a constructed new_item).
IN_COLLECTION = {
    "tc-auth-001": "authentication-flow-tester",
    "tc-tls-001": "tls-enforcer",
    "tc-bio-001": "biometric-far-checker",
    "tc-crud-001": "crud-integrity-prober",
    "tc-crud-002": "crud-integrity-prober",
    "tc-schema-001": "schema-response-validator",
    "tc-page-001": "pagination-checker",
    "tc-clarity-001": "error-clarity-checker",
}


def build_collection() -> dict:
    """A Postman v2.1 collection holding one request item (named by tc_id) per IN_COLLECTION
    test case, grouped into one folder per agent."""
    by_agent: dict = {}
    for tc in REGISTRY:
        tid = tc["tc_id"]
        if tid in IN_COLLECTION:
            by_agent.setdefault(tc["agent"], []).append(
                bugreport_spec.build_new_item(tc))
    folders = [{"name": agent, "item": items} for agent, items in by_agent.items()]
    return {
        "info": {"name": "API Test Agent Suite — 2026-06-26",
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "variable": [{"key": "base_url", "value": "http://localhost:8080", "type": "string"}],
        "item": folders,
    }


def build_fixture() -> dict:
    agents = []
    for f in (FAILURES + PASSED):
        agents.append({
            "agent_name": f["agent_name"], "status": f["status"],
            "exit_code": f["exit_code"], "spec_path": f["spec_path"],
            "stdout": f["stdout"], "stderr": f["stderr"],
            "stdout_path": f"results/runs/{SPEC['fixture_run_id']}/stdout/{f['agent_name']}.stdout.txt",
            "stderr_path": f"results/runs/{SPEC['fixture_run_id']}/stderr/{f['agent_name']}.stderr.txt",
        })
    return {
        "db_available": False,
        "pipeline_summary": {"run_id": SPEC["fixture_run_id"], "agents": agents},
        "registry": REGISTRY,
        "postman_collection": build_collection(),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture()
    (OUT_DIR / "fixture.json").write_text(json.dumps(fixture, indent=2))

    postman_items = bugreport_spec.build_postman_items(fixture["postman_collection"])
    failed = [a for a in fixture["pipeline_summary"]["agents"] if a["status"] != "PASSED"]

    gold_decisions = []
    seq = 1
    for failure in failed:
        gold = bugreport_spec.build_reference_decision(failure, REGISTRY, postman_items)
        severity = gold["severity"]
        gold_decisions.append({
            "bug_index": seq,
            "agent_name": failure["agent_name"],
            "status": failure["status"],
            "severity": severity,
            "priority": gold["priority"],
            "title": gold["title"],
            "decision": gold,
        })
        seq += 1

    crit = sum(1 for g in gold_decisions if g["severity"] == "CRITICAL")
    high = sum(1 for g in gold_decisions if g["severity"] == "HIGH")
    med = sum(1 for g in gold_decisions if g["severity"] == "MEDIUM")
    low = sum(1 for g in gold_decisions if g["severity"] == "LOW")

    gold = {
        "task": "general / bug-reporter",
        "alias": "n602",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "fixture": SPEC["fixture"],
        "failures": len(failed),
        "fields_per_failure": len(bugreport_spec.DECISION_FIELDS),
        "total_gold_fields": len(failed) * len(bugreport_spec.DECISION_FIELDS),
        "severity_counts": {"CRITICAL": crit, "HIGH": high, "MEDIUM": med, "LOW": low},
        "has_critical_or_high": (crit + high) > 0,
        "must_exit_code_1": (crit + high) > 0,
        "gold_decisions": gold_decisions,
        "note": "Ground truth = the deterministic five-key decision per failure (title, "
                "severity via the nine ordered rules, priority, mapped testing_steps, and "
                "postman_references). Framework ranking is Bug-Report Fidelity (agent "
                "decision vs gold), which is backend-independent. The headline Bug Report "
                "Completeness Rate is fixture+harness-determined (~90% with the DB dump "
                "null because the fixture has no [database]). DummyJSON untouched; no "
                "server started.",
    }
    (OUT_DIR / "gold.json").write_text(json.dumps(gold, indent=2))
    (OUT_DIR / "gold").mkdir(exist_ok=True)
    for g in gold_decisions:
        (OUT_DIR / "gold" / f"{g['agent_name']}.json").write_text(json.dumps(g, indent=2))

    print("GOLD built — general / bug-reporter (n602)")
    print(f"  fixture      : {SPEC['fixture']}")
    print(f"  failures     : {len(failed)} (excluded PASSED: {len(PASSED)})")
    print(f"  severity     : CRITICAL={crit} HIGH={high} MEDIUM={med} LOW={low}")
    print(f"  must exit 1  : {(crit + high) > 0}")
    for g in gold_decisions:
        print(f"    [{g['severity']:8} {g['priority']}] {g['agent_name']:28} {g['title'][:60]}")
    # sanity: every rule produced its intended severity
    expected = ["CRITICAL", "CRITICAL", "CRITICAL", "HIGH", "HIGH", "HIGH",
                "MEDIUM", "MEDIUM", "LOW"]
    got = [g["severity"] for g in gold_decisions]
    ok = got == expected
    print(f"  severity rules R1..R9 -> {'OK' if ok else 'MISMATCH ' + str(got)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
