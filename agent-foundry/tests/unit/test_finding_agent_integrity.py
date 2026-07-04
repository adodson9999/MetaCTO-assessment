#!/usr/bin/env python3
"""Unit test 12 (§7.4) — HF21 finding-agent integrity.

Pure Python, NO model. Every unverified report's finding_agent is non-empty and equals the
{agent} path segment AND the ledger row's agent; finding_endpoint is present. Uses the
finding_agent_cases golden. A blanked finding_agent is flagged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_finding_agent_integrity.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


def test_finding_agent_matches_path_and_row(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["finding_agent_cases"][0]
    run_id = case["run_id"]
    rows, entries = H.materialize_unverified(BR, run_id, [case["row"]], db_available=False, workspace=ws)
    bp = BR.bug_paths(run_id, workspace=ws)
    G = H.load_gate()
    scanned = G.scan_unverified_reports(bp.tree)
    assert len(scanned) == 1
    u = scanned[0]
    assert u["report"]["finding_agent"] == case["expect_finding_agent"]
    assert u["report"]["finding_endpoint"] == case["expect_finding_endpoint"]
    assert u["agent_seg"] == case["expect_path_segment"]
    assert u["report"]["finding_agent"] == u["agent_seg"] == rows[0]["agent"]
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF21") is True


def test_blank_finding_agent_is_flagged(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["finding_agent_cases"][0]
    run_id = case["run_id"]
    rows, entries = H.materialize_unverified(BR, run_id, [case["row"]], db_available=False, workspace=ws)
    bp = BR.bug_paths(run_id, workspace=ws)
    G = H.load_gate()
    u = G.scan_unverified_reports(bp.tree)[0]
    rec = json.loads(u["path"].read_text())
    rec["finding_agent"] = ""
    u["path"].write_text(json.dumps(rec))
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF21") is False
