#!/usr/bin/env python3
"""Unit test 14 (§7.4) — HF23 citation isolation.

Pure Python, NO model. Unverified bugs carry documentation_cited:false + source_of_truth:null;
verified bugs carry documentation_cited:true + a non-null source_of_truth. Any leakage in
either direction is flagged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_citation_isolation.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

RUN = "RUN-20260701-120000"
_ROW = {"agent": "test-authentication-flows", "endpoint": "/auth/login",
        "scenario": "login without password", "expected": "401", "observed": "200"}


def test_unverified_has_no_citation(bugreport) -> None:
    BR, ws = bugreport
    rep = BR.write_unverified_bug(RUN, dict(_ROW), {}, db_available=False, workspace=ws)
    assert rep["documentation_cited"] is False
    assert rep["source_of_truth"] is None


def test_verified_has_citation(bugreport) -> None:
    BR, ws = bugreport
    ctx = dict(_ROW, source_of_truth={"file": "docs.md", "line": 4, "text": "auth required"})
    rep = BR.write_verified_bug(RUN, ctx, {}, db_available=False, workspace=ws)
    assert rep["documentation_cited"] is True
    assert rep["source_of_truth"] is not None


def test_gate_flags_citation_leak(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, [_ROW], db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    u = G.scan_unverified_reports(bp.tree)[0]
    rec = json.loads(u["path"].read_text())
    rec["documentation_cited"] = True                        # leak a citation onto an unverified bug
    rec["source_of_truth"] = {"file": "x.md", "line": 1, "text": "y"}
    u["path"].write_text(json.dumps(rec))
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF23") is False
