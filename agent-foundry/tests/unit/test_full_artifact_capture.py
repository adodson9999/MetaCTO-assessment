#!/usr/bin/env python3
"""Unit test 13 (§7.4) — HF22 full-capture parity.

Pure Python, NO model. Every unverified report carries screenshot/recording/logs;
db_dump only when db_available; complete_artifact_count meets the verified threshold. A
report missing its recording is flagged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_full_artifact_capture.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_ROWS = [
    {"agent": "test-authentication-flows", "endpoint": "/auth/login", "scenario": "login without password",
     "expected": "401", "observed": "200", "severity": "CRITICAL"},
    {"agent": "verify-sorting-behavior", "endpoint": "/products", "scenario": "sort price",
     "expected": "sorted", "observed": "unsorted data", "severity": "MEDIUM"},
]
RUN = "RUN-20260701-120000"


@pytest.mark.parametrize("db_available", [False, True])
def test_full_capture_parity(bugreport, db_available: bool) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=db_available, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    for u in G.scan_unverified_reports(bp.tree):
        comp = u["report"]["artifact_completeness"]
        assert comp["screenshot"] and comp["recording"] and comp["logs"]
        assert comp["db_dump"] is db_available
        assert u["report"]["complete_artifact_count"] >= BR.VERIFIED_ARTIFACT_THRESHOLD[db_available]
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, db_available)
    assert result.checks.get("HF22") is True


def test_missing_recording_is_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    u = G.scan_unverified_reports(bp.tree)[0]
    rec = json.loads(u["path"].read_text())
    rec["artifact_completeness"]["recording"] = False
    rec["complete_artifact_count"] -= 1
    u["path"].write_text(json.dumps(rec))
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF22") is False
