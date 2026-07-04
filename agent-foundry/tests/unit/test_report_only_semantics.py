#!/usr/bin/env python3
"""Unit test 16 (§7.4) — HF15 / decision #8 report-only semantics.

Pure Python, NO model. A run whose bugs are ALL unverified — including a vulnerability at P1 —
leaves the exit code at 0 and the CI add-set empty. Uses report_only_cases.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_report_only_semantics.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


def test_unverified_never_trips_exit_or_ci(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["report_only_cases"]
    run_id = case["run_id"]
    # materialise the unverified bugs (a CRITICAL/P1 vulnerability among them)
    rows = [{"agent": u["finding_agent"], "endpoint": "/x", "scenario": "s",
             "expected": "401" if u["category"] == "vulnerability" else "sorted",
             "observed": "200" if u["category"] == "vulnerability" else "unsorted data",
             "severity": u["severity"]} for u in case["unverified"]]
    ledger_rows, entries = H.materialize_unverified(BR, run_id, rows, db_available=False, workspace=ws)
    unverified_reports = [{"bug_id": r["unverified_bug_id"], "severity": rw["severity"]}
                          for r, rw in zip(ledger_rows, rows)]

    # report-only: no verified bugs -> exit code stays 0, CI add-set empty
    assert BR.would_exit_code_1(verified_reports=case["verified"],
                                unverified_reports=unverified_reports) is case["expect_would_exit_code_1"]
    assert (BR.ci_add_set(verified_reports=case["verified"],
                          unverified_reports=unverified_reports) == []) is case["expect_ci_add_set_empty"]

    # and the gate agrees (HF15 holds: every unverified row is excluded from CI)
    G = H.load_gate()
    bp = BR.bug_paths(run_id, workspace=ws)
    unv = json.loads(bp.unverified_index.read_text())
    result = G.evaluate(ledger_rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF15") is True
