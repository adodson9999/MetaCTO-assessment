#!/usr/bin/env python3
"""Unit test 2 (§7.4) — the materialiser writes the exact tree with full artifacts.

Pure Python, NO model. Fixed date/time/run_id -> exact path + ID prefix (layout_cases),
full 10-artifact presence, the verified mirror path, and the report-only exit gate
(unverified bugs never trip would_exit_code_1).

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_materialize.py
"""
from __future__ import annotations

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


@pytest.mark.parametrize("case", _GOLDEN["layout_cases"], ids=lambda c: c["id"])
def test_layout_path_and_prefix(case: dict, bugreport) -> None:
    BR, ws = bugreport
    counters: dict = {}
    # mint IDs up to the case's sequence so the per-category counter reaches it.
    bug_id = None
    for _ in range(case["seq"]):
        bug_id = BR.mint_id("unverified", case["run_id"], case["category"], counters)
    assert bug_id.startswith(case["expect_prefix"] + "-")
    bp = BR.bug_paths(case["run_id"], workspace=ws)
    path = bp.unverified_dir(case["agent"], case["category"]) / f"{bug_id}.json"
    rel = str(path.relative_to(ws))
    assert rel == case["expect_path"], f"{case['id']}: {rel} != {case['expect_path']}"


def test_full_artifacts_and_verified_mirror(bugreport, run_id) -> None:
    BR, ws = bugreport
    ctx = {"agent": "test-authentication-flows", "endpoint": "/auth/login",
           "scenario": "login without password", "expected": "401", "observed": "200",
           "severity": "CRITICAL"}
    counters: dict = {}
    rep = BR.write_unverified_bug(run_id, ctx, counters, db_available=False, workspace=ws)

    # exact on-disk path
    report_path = ws / rep["_meta"]["report_path"]
    assert report_path.is_file()
    assert rep["bug_id"] == "VULN-RUN-20260701-120000-0001"
    assert rep["category"] == "vulnerability"

    # full artifact capture (screenshot/recording/logs present; db_dump null when db absent)
    comp = rep["artifact_completeness"]
    for must in ("screenshot", "recording", "logs"):
        assert comp[must] is True, f"{must} missing"
    assert comp["db_dump"] is False
    assert rep["complete_artifact_count"] >= BR.VERIFIED_ARTIFACT_THRESHOLD[False]
    # the artifact files really exist on disk
    for key in ("screenshot_path", "recording_path", "log_path"):
        assert (ws / rep["artifacts"][key]).is_file()
    assert rep["artifacts"]["db_dump_path"] is None

    # verified mirror lands under verified_bugs/ with a BUG- id and a citation
    vctx = dict(ctx, source_of_truth={"file": "docs.md", "line": 3, "text": "auth required"})
    vcounters: dict = {}
    vrep = BR.write_verified_bug(run_id, vctx, vcounters, db_available=False, workspace=ws)
    assert vrep["bug_id"] == "BUG-RUN-20260701-120000-0001"
    assert "/verified_bugs/" in vrep["_meta"]["report_path"]
    assert vrep["documentation_cited"] is True and vrep["source_of_truth"] is not None
    assert "category" not in vrep

    # report-only: a CRITICAL unverified bug never trips the exit gate; only verified do.
    assert BR.would_exit_code_1(verified_reports=[], unverified_reports=[rep]) is False
    assert BR.would_exit_code_1(verified_reports=[vrep], unverified_reports=[rep]) is True
    assert BR.ci_add_set(verified_reports=[], unverified_reports=[rep]) == []


def test_db_available_captures_db_dump(bugreport, run_id) -> None:
    BR, ws = bugreport
    ctx = {"agent": "verify-crud-operation-integrity", "endpoint": "/carts",
           "scenario": "create cart", "expected": "row", "observed": "500", "severity": "HIGH"}
    rep = BR.write_unverified_bug(run_id, ctx, {}, db_available=True, workspace=ws)
    assert rep["artifact_completeness"]["db_dump"] is True
    assert (ws / rep["artifacts"]["db_dump_path"]).is_file()
    assert rep["complete_artifact_count"] >= BR.VERIFIED_ARTIFACT_THRESHOLD[True]
