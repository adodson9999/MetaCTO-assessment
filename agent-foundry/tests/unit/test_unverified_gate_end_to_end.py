#!/usr/bin/env python3
"""Unit test 18 (§7.4 / §7.2) — the forge gate end to end over every HF13-HF26 injection.

Pure Python, NO model. Materialises the gate golden's base_rows, asserts the clean run passes
(exit 0), then applies each injected break from unverified-bug-gate.golden.json and asserts the
named HF check flips to false and the gate fails (exit 1). Finally proves the setup-error path
(rows present, tree removed -> exit 2).

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_gate_end_to_end.py
"""
from __future__ import annotations

import json
import shutil

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GATE_GOLDEN = json.loads(
    (H.WS / "agents" / "general" / "bug-reporter" / "forge-gate"
     / "unverified-bug-gate.golden.json").read_text())


def _materialize(BR, ws):
    run_id = "RUN-20260701-120000"
    rows, entries = H.materialize_unverified(BR, run_id, _GATE_GOLDEN["base_rows"],
                                             db_available=False, workspace=ws)
    bp = BR.bug_paths(run_id, workspace=ws)
    unv = json.loads(bp.unverified_index.read_text())
    return run_id, rows, bp, unv


def _first_report(G, bp):
    scanned = G.scan_unverified_reports(bp.tree)
    return scanned[0]["path"]


def _apply_break(name, BR, G, rows, bp, unv):
    """Mutate the materialised run in place per the golden's `break` name."""
    if name == "clear_unverified_bug_id":
        rows[0]["unverified_bug_id"] = None
    elif name == "flip_row_category":
        rows[0]["category"] = "business-workflow"  # row0 is truly vulnerability (401->200)
    elif name == "unexclude_from_cicd":
        rows[0]["exclude_from_cicd"] = False
    elif name == "inject_bug_prefix_in_unverified_index":
        unv["bugs"].append({"bug_id": "BUG-RUN-20260701-120000-0001", "category": "vulnerability",
                            "severity": "LOW", "finding_agent": "x"})
    elif name == "reverse_unverified_index":
        unv["bugs"] = list(reversed(unv["bugs"]))
    elif name == "inject_orphan_report_file":
        d = bp.unverified_dir("test-authentication-flows", "vulnerability")
        (d / "VULN-RUN-20260701-120000-9999.json").write_text(json.dumps({
            "bug_id": "VULN-RUN-20260701-120000-9999", "category": "vulnerability",
            "reviewer_verdict": "missing-docs", "documentation_cited": False, "source_of_truth": None,
            "finding_agent": "test-authentication-flows", "finding_endpoint": "/x", "severity": "LOW",
            "artifact_completeness": {"screenshot": True, "recording": True, "logs": True, "db_dump": False},
            "complete_artifact_count": 9}))
    elif name == "inject_duplicate_id_file":
        p = _first_report(G, bp)
        rec = json.loads(p.read_text())
        dup = p.parent / "dup.json"
        dup.write_text(json.dumps(rec))
    elif name == "misfile_report":
        d = bp.unverified_dir("verify-crud-operation-integrity", "vulnerability")
        d.mkdir(parents=True, exist_ok=True)
        (d / "SW-RUN-20260701-120000-0009.json").write_text(json.dumps({
            "bug_id": "SW-RUN-20260701-120000-0009", "category": "computer-software",
            "reviewer_verdict": "missing-docs", "documentation_cited": False, "source_of_truth": None,
            "finding_agent": "verify-crud-operation-integrity", "finding_endpoint": "/carts", "severity": "MEDIUM",
            "artifact_completeness": {"screenshot": True, "recording": True, "logs": True, "db_dump": False},
            "complete_artifact_count": 9}))
    elif name == "blank_finding_agent":
        p = _first_report(G, bp)
        rec = json.loads(p.read_text())
        rec["finding_agent"] = ""
        p.write_text(json.dumps(rec))
    elif name == "drop_recording":
        p = _first_report(G, bp)
        rec = json.loads(p.read_text())
        rec["artifact_completeness"]["recording"] = False
        rec["complete_artifact_count"] -= 1
        p.write_text(json.dumps(rec))
    elif name == "leak_citation":
        p = _first_report(G, bp)
        rec = json.loads(p.read_text())
        rec["documentation_cited"] = True
        rec["source_of_truth"] = {"file": "x.md", "line": 1, "text": "y"}
        p.write_text(json.dumps(rec))
    elif name == "flip_verdict_to_yes":
        p = _first_report(G, bp)
        rec = json.loads(p.read_text())
        rec["reviewer_verdict"] = "yes"
        p.write_text(json.dumps(rec))
    elif name == "corrupt_by_category_count":
        unv["by_category"]["vulnerability"] = 99
    elif name == "inject_generated_at":
        unv["generated_at"] = "2026-07-01T12:00:00Z"
    else:
        raise AssertionError(f"unknown break: {name}")


def test_clean_run_passes(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    _, rows, bp, unv = _materialize(BR, ws)
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=_GATE_GOLDEN["db_available"])
    assert result.status == _GATE_GOLDEN["expect_clean"]["status"], result.problems
    assert result.ok is True


@pytest.mark.parametrize("inj", _GATE_GOLDEN["injections"], ids=lambda i: i["id"])
def test_each_injection_is_caught(inj: dict, bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    _, rows, bp, unv = _materialize(BR, ws)
    _apply_break(inj["break"], BR, G, rows, bp, unv)
    result = G.evaluate(rows, bp.tree, unv, {}, db_available=_GATE_GOLDEN["db_available"])
    assert result.status == inj["expect_status"], (inj["id"], result.problems)
    assert result.checks.get(inj["expect_check"]) is False, (
        f"{inj['id']}: expected {inj['expect_check']} to fail; checks={result.checks}")


def test_setup_error_when_tree_missing(bugreport) -> None:
    BR, ws = bugreport
    G = H.load_gate()
    _, rows, bp, unv = _materialize(BR, ws)
    shutil.rmtree(bp.tree)  # rows present but the tree is gone -> setup error (exit 2)
    result = G.evaluate(rows, bp.tree, {}, {}, db_available=False)
    assert result.status == "error"


def test_does_not_apply_when_no_rows_and_no_tree(bugreport, tmp_path) -> None:
    G = H.load_gate()
    empty = tmp_path / "empty"  # no tree, no rows -> gate is a no-op pass (exit 0)
    result = G.evaluate([], empty, {}, {}, db_available=False)
    assert result.status == "pass" and result.applies is False
