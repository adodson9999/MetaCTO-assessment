#!/usr/bin/env python3
"""Unit test 3 (§7.4) — reconciliation: clean run passes; HF13-HF17 violations flagged.

Pure Python, NO model. Two layers:
  * gate-level: build a materialised run, assert the gate passes, then break HF13/14/15/16/17
    one at a time and assert each is caught;
  * integration: drive adjudicate.materialize_new_tree + adjudicate.reconcile over a tmp
    workspace so the real wiring (routing -> tree -> reconcile) is exercised.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_reconcile.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

RUN = "RUN-20260701-120000"
_ROWS = [
    {"agent": "test-authentication-flows", "endpoint": "/auth/login", "scenario": "login without password",
     "expected": "401", "observed": "200"},
    {"agent": "verify-sorting-behavior", "endpoint": "/products", "scenario": "sort price",
     "expected": "sorted", "observed": "unsorted data"},
    {"agent": "verify-crud-operation-integrity", "endpoint": "/carts", "scenario": "create",
     "expected": "row", "observed": "500 error"},
]


def _materialize(BR, ws):
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    unv = json.loads(bp.unverified_index.read_text())
    return rows, bp, unv


def test_clean_run_passes(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.status == "pass", result.problems
    for hf in ("HF13", "HF14", "HF15", "HF16", "HF17"):
        assert result.checks.get(hf) is True


def test_hf13_missing_id_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    rows[0]["unverified_bug_id"] = None
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF13") is False


def test_hf14_wrong_category_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    rows[0]["category"] = "computer-software"  # truly vulnerability (401->200)
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF14") is False


def test_hf15_not_excluded_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    rows[0]["exclude_from_cicd"] = False
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF15") is False


def test_hf16_bug_prefix_in_unverified_index_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    unv["bugs"].append({"bug_id": "BUG-RUN-20260701-120000-0001", "category": "vulnerability",
                        "severity": "LOW", "finding_agent": "x"})
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF16") is False


def test_hf17_vuln_not_first_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, bp, unv = _materialize(BR, ws)
    # reverse the index order so the vulnerability no longer sorts first
    unv["bugs"] = list(reversed(unv["bugs"]))
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF17") is False


def test_adjudicate_integration(monkeypatch, deterministic_time, tmp_path) -> None:
    """The real routing wiring: adjudicate.materialize_new_tree stamps rows + writes the tree,
    and adjudicate.reconcile's unverified gate passes on the clean result."""
    import adjudicate as A
    monkeypatch.setattr(A, "WS", tmp_path)
    monkeypatch.setattr(A, "BUG_DIR", tmp_path / "results" / "bug-reports")
    A.BR.WORKSPACE = tmp_path
    A.BR.SANDBOX_ROOT = tmp_path
    rows = [dict(r, outcome="missing-docs", reviewer_verdict="missing-docs",
                 exclude_from_cicd=True) for r in _ROWS]
    counts = A.materialize_new_tree(RUN, rows)
    assert counts["unverified"] == 3
    # rows were stamped in place (HF13)
    assert all(r["unverified_bug_id"] and r["category"] in A.bugreport_spec.UNVERIFIED_CATEGORIES
               for r in rows)
    run_dir = tmp_path / "results" / "runs" / RUN
    run_dir.mkdir(parents=True, exist_ok=True)
    recon = A.reconcile(RUN, run_dir, rows, bug_ids=[])
    assert recon["ok"] is True, recon["problems"]
    assert recon["unverified"]["status"] == "pass"
