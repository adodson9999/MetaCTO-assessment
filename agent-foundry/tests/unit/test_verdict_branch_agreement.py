#!/usr/bin/env python3
"""Unit test 15 (§7.4) — HF24 verdict <-> branch agreement.

Pure Python, NO model. Only missing-docs rows may produce VULN/BIZ/SW reports; only yes rows
may produce BUG reports. A yes report in the unverified tree (or a missing-docs report in the
verified tree) is flagged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_verdict_branch_agreement.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

RUN = "RUN-20260701-120000"
_ROW = {"agent": "test-authentication-flows", "endpoint": "/auth/login",
        "scenario": "login without password", "expected": "401", "observed": "200"}


def test_reports_carry_expected_verdict(bugreport) -> None:
    BR, ws = bugreport
    uv = BR.write_unverified_bug(RUN, dict(_ROW), {}, db_available=False, workspace=ws)
    assert uv["reviewer_verdict"] == "missing-docs"
    v = BR.write_verified_bug(RUN, dict(_ROW, source_of_truth={"file": "d", "line": 1, "text": "t"}),
                              {}, db_available=False, workspace=ws)
    assert v["reviewer_verdict"] == "yes"


def test_gate_flags_yes_report_in_unverified_tree(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, [_ROW], db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    u = G.scan_unverified_reports(bp.tree)[0]
    rec = json.loads(u["path"].read_text())
    rec["reviewer_verdict"] = "yes"  # a yes verdict has no business in the unverified tree
    u["path"].write_text(json.dumps(rec))
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF24") is False


def test_gate_flags_missing_docs_report_in_verified_tree(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    # a lone verified report whose verdict is (wrongly) missing-docs
    v = BR.write_verified_bug(RUN, dict(_ROW, source_of_truth={"file": "d", "line": 1, "text": "t"}),
                              {}, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    vpath = ws / v["_meta"]["report_path"]
    rec = json.loads(vpath.read_text())
    rec["reviewer_verdict"] = "missing-docs"
    vpath.write_text(json.dumps(rec))
    result = G.evaluate([], bp.tree, {}, {}, db_available=False)
    assert result.checks.get("HF24") is False
