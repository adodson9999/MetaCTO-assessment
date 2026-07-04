#!/usr/bin/env python3
"""Unit test 9 (§7.4) — HF18 bidirectional file<->row<->index reconciliation.

Pure Python, NO model. Materialises the idempotency_cases rows, asserts the gate passes,
then injects (a) an orphan report file with no ledger row and (b) a dangling ledger row
with no file, and asserts each is caught (HF18 fails both ways).

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_denominator.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


def _materialize(BR, ws):
    case = _GOLDEN["idempotency_cases"]
    rows, entries = H.materialize_unverified(BR, case["run_id"], case["rows"],
                                             db_available=False, workspace=ws)
    bp = BR.bug_paths(case["run_id"], workspace=ws)
    unv = json.loads(bp.unverified_index.read_text())
    return case["run_id"], rows, bp, unv


def test_clean_run_passes_hf18(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    _, rows, bp, unv = _materialize(BR, ws)
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.status == "pass", result.problems
    assert result.checks.get("HF18") is True


def test_orphan_file_is_caught(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    run_id, rows, bp, unv = _materialize(BR, ws)
    # inject an orphan report file (a real category dir, id not in any ledger row / index)
    orphan_dir = bp.unverified_dir("test-authentication-flows", "vulnerability")
    orphan = orphan_dir / "VULN-RUN-20260701-120000-9999.json"
    orphan.write_text(json.dumps({
        "bug_id": "VULN-RUN-20260701-120000-9999", "category": "vulnerability",
        "reviewer_verdict": "missing-docs", "documentation_cited": False,
        "source_of_truth": None, "finding_agent": "test-authentication-flows",
        "finding_endpoint": "/x", "severity": "LOW",
        "artifact_completeness": {"screenshot": True, "recording": True, "logs": True, "db_dump": False},
        "complete_artifact_count": 9}))
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.status == "fail"
    assert result.checks.get("HF18") is False
    assert any("orphan" in p for p in result.problems)


def test_dangling_row_is_caught(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    run_id, rows, bp, unv = _materialize(BR, ws)
    rows.append({"agent": "ghost", "scenario": "phantom", "expected": "x", "observed": "y",
                 "outcome": "missing-docs", "reviewer_verdict": "missing-docs",
                 "exclude_from_cicd": True, "category": "computer-software",
                 "unverified_bug_id": "SW-RUN-20260701-120000-9999"})
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.status == "fail"
    assert result.checks.get("HF18") is False
    assert any("dangling" in p for p in result.problems)
