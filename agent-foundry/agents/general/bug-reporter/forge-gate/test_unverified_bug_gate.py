#!/usr/bin/env python3
"""Colocated unit test for the unverified-bug gate's pure evaluate() core (§7.2).

NO model. Verifies the three-way status contract (pass / fail / error / does-not-apply) and
the receipt shape directly against unverified_bug_gate.evaluate, independent of the foundry
materialiser. The exhaustive HF13-HF26 injection matrix lives in
tests/unit/test_unverified_gate_end_to_end.py (driven by unverified-bug-gate.golden.json).

Run: python3 -m pytest -m unit \
       agent-foundry/agents/general/bug-reporter/forge-gate/test_unverified_bug_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unverified_bug_gate as G  # noqa: E402

pytestmark = pytest.mark.unit


def test_does_not_apply_is_pass(tmp_path) -> None:
    result = G.evaluate([], tmp_path / "no-tree", {}, {}, db_available=False)
    assert result.applies is False
    assert result.status == "pass"
    assert result.ok is True


def test_setup_error_when_rows_but_no_tree(tmp_path) -> None:
    rows = [{"outcome": "missing-docs", "unverified_bug_id": "VULN-x-0001",
             "category": "vulnerability", "agent": "a"}]
    result = G.evaluate(rows, tmp_path / "absent", {}, {}, db_available=False)
    assert result.status == "error"


def test_receipt_shape() -> None:
    result = G.GateResult(applies=True, status="pass", checks={"HF13": True}, problems=[],
                          counts={"unverified_files": 0})
    receipt = G.build_receipt("RUN-x", result)
    assert receipt["gate"] == "unverified-bug"
    assert receipt["status"] == "pass"
    assert receipt["run_id"] == "RUN-x"
    assert "ts" in receipt and "checks" in receipt


def test_prefix_category_maps_round_trip() -> None:
    for cat, prefix in G.CATEGORY_TO_PREFIX.items():
        assert G.PREFIX_TO_CATEGORY[prefix] == cat
