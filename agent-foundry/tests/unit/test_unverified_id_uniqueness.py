#!/usr/bin/env python3
"""Unit test 10 (§7.4) — HF19 ID uniqueness + per-category sequence integrity.

Pure Python, NO model. Materialises rows spanning multiple agents/categories, asserts every
bug_id is unique and per-category sequences are dense and non-colliding, then injects a
duplicate id and asserts the gate catches it.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_id_uniqueness.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_ROWS = [
    {"agent": "a1", "endpoint": "/x", "scenario": "s", "expected": "401", "observed": "200"},
    {"agent": "a2", "endpoint": "/y", "scenario": "s", "expected": "401", "observed": "200"},
    {"agent": "a3", "endpoint": "/z", "scenario": "s", "expected": "sorted", "observed": "unsorted data"},
    {"agent": "a4", "endpoint": "/w", "scenario": "s", "expected": "row", "observed": "500 error"},
    {"agent": "a5", "endpoint": "/v", "scenario": "s", "expected": "row", "observed": "database down"},
]
RUN = "RUN-20260701-120000"


def test_ids_unique_and_sequences_dense(bugreport) -> None:
    BR, ws = bugreport
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    ids = [r["unverified_bug_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate bug_id minted"
    # two vulnerabilities -> VULN-...-0001, VULN-...-0002 ; sequences per category are dense
    vulns = sorted(i for i in ids if i.startswith("VULN-"))
    assert vulns == ["VULN-RUN-20260701-120000-0001", "VULN-RUN-20260701-120000-0002"]
    sw = sorted(i for i in ids if i.startswith("SW-"))
    assert sw == ["SW-RUN-20260701-120000-0001", "SW-RUN-20260701-120000-0002"]
    biz = sorted(i for i in ids if i.startswith("BIZ-"))
    assert biz == ["BIZ-RUN-20260701-120000-0001"]


def test_duplicate_id_is_caught(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    rows, entries = H.materialize_unverified(BR, RUN, _ROWS, db_available=False, workspace=ws)
    bp = BR.bug_paths(RUN, workspace=ws)
    # write a second file that reuses an existing id under the same category dir
    dup = bp.unverified_dir("a1", "vulnerability") / "VULN-RUN-20260701-120000-0002.json"
    dup.write_text(json.dumps({
        "bug_id": "VULN-RUN-20260701-120000-0002", "category": "vulnerability",
        "reviewer_verdict": "missing-docs", "documentation_cited": False, "source_of_truth": None,
        "finding_agent": "a1", "finding_endpoint": "/x", "severity": "LOW",
        "artifact_completeness": {"screenshot": True, "recording": True, "logs": True, "db_dump": False},
        "complete_artifact_count": 9}))
    unv = json.loads(bp.unverified_index.read_text())
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=False)
    assert result.checks.get("HF19") is False
    assert any("duplicate" in p for p in result.problems)
