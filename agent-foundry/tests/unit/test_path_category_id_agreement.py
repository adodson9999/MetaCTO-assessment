#!/usr/bin/env python3
"""Unit test 11 (§7.4) — HF20 path <-> category field <-> ID prefix agreement.

Pure Python, NO model. Every unverified report's on-disk {category} path segment, its
`category` field, and its ID's category (via CATEGORY_TO_PREFIX) must agree. A deliberately
misfiled report (a SW- report under .../vulnerability/) is flagged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_path_category_id_agreement.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_ROWS = [
    {"agent": "a1", "endpoint": "/x", "scenario": "s", "expected": "401", "observed": "200"},
    {"agent": "a3", "endpoint": "/z", "scenario": "s", "expected": "sorted", "observed": "unsorted data"},
    {"agent": "a4", "endpoint": "/w", "scenario": "s", "expected": "row", "observed": "500 error"},
]
RUN = "RUN-20260701-120000"


def test_path_field_prefix_agree(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    for u in G.scan_unverified_reports(bp.tree):
        prefix_cat = G.PREFIX_TO_CATEGORY[u["report"]["bug_id"].split("-", 1)[0]]
        assert u["category_seg"] == u["report"]["category"] == prefix_cat
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF20") is True


def test_misfiled_report_is_flagged(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    # drop a SW- report into the vulnerability directory (path says vuln, field/id say sw)
    misfiled_dir = bp.unverified_dir("a4", "vulnerability")
    misfiled_dir.mkdir(parents=True, exist_ok=True)
    misfiled = misfiled_dir / "SW-RUN-20260701-120000-0009.json"
    misfiled.write_text(json.dumps({
        "bug_id": "SW-RUN-20260701-120000-0009", "category": "computer-software",
        "reviewer_verdict": "missing-docs", "documentation_cited": False, "source_of_truth": None,
        "finding_agent": "a4", "finding_endpoint": "/w", "severity": "MEDIUM",
        "artifact_completeness": {"screenshot": True, "recording": True, "logs": True, "db_dump": False},
        "complete_artifact_count": 9}))
    result = G.evaluate(rows, bp.tree, json.loads(bp.unverified_index.read_text()), {}, False)
    assert result.checks.get("HF20") is False
    assert any("misfiled" in p for p in result.problems)
