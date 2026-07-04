#!/usr/bin/env python3
"""G25 unverified-layout gate: proves it PASSES only when every unverified bug lives at
BugReport/unverified/{category}/{PREFIX}-*.json with category-consistent id and co-located
artifacts, and FAILS on each violation (legacy per-agent layout, a stray unverified report, a
category mismatch, an empty finding_agent, or a non-co-located artifact).

Run:  agent-foundry/.venv/bin/python -m pytest agent-foundry/tests/test_unverified_layout_gate.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "scripts"))
import guardrails as G  # noqa: E402


def _uv(tree: Path, category: str, bug_id: str, **over) -> Path:
    """Write one unverified report under BugReport/unverified/{category}/ + a co-located artifact."""
    d = tree / "unverified" / category
    (d / "screenshots").mkdir(parents=True, exist_ok=True)
    (d / "screenshots" / f"{bug_id}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    rep = {"bug_id": bug_id, "category": category, "finding_agent": "test-pagination-behavior",
           "documentation_cited": False,
           "artifacts": {"screenshot_path": f"BugReport/unverified/{category}/screenshots/{bug_id}.png"}}
    rep.update(over)
    p = d / f"{bug_id}.json"
    p.write_text(json.dumps(rep))
    return p


def test_g25_passes_correct_layout(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    _uv(out / "BugReport", "business-workflow", "BIZ-RUN-1-0001")
    _uv(out / "BugReport", "computer-software", "SW-RUN-1-0001")
    r = G.g25_unverified_layout(out)
    assert r["status"] == "PASS" and r["hard"], r["detail"]


def test_g25_passes_when_no_unverified(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    (out / "BugReport" / "test-authentication-flows" / "verified_bugs").mkdir(parents=True)
    assert G.g25_unverified_layout(out)["status"] == "PASS"


def test_g25_fails_legacy_per_agent_layout(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    d = out / "BugReport" / "test-pagination-behavior" / "unverified_bugs" / "computer-software"
    d.mkdir(parents=True)
    (d / "SW-RUN-1-0001.json").write_text(json.dumps(
        {"bug_id": "SW-RUN-1-0001", "category": "computer-software",
         "finding_agent": "test-pagination-behavior"}))
    r = G.g25_unverified_layout(out)
    assert r["status"] == "FAIL" and "unverified_bugs" in r["detail"]


def test_g25_fails_stray_unverified_report(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    d = out / "BugReport" / "test-pagination-behavior" / "verified_bugs"
    d.mkdir(parents=True)
    (d / "SW-RUN-1-0001.json").write_text(json.dumps(
        {"bug_id": "SW-RUN-1-0001", "category": "computer-software",
         "finding_agent": "test-pagination-behavior"}))
    r = G.g25_unverified_layout(out)
    assert r["status"] == "FAIL" and "not under BugReport/unverified/" in r["detail"]


def test_g25_fails_category_mismatch(tmp_path):
    """A SW- report filed in the business-workflow folder fails."""
    out = tmp_path / "2026-07-04" / "00-00-00"
    _uv(out / "BugReport", "business-workflow", "SW-RUN-1-0001")  # SW id in BIZ folder
    r = G.g25_unverified_layout(out)
    assert r["status"] == "FAIL" and "category mismatch" in r["detail"]


def test_g25_fails_empty_finding_agent(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    _uv(out / "BugReport", "computer-software", "SW-RUN-1-0001", finding_agent="")
    r = G.g25_unverified_layout(out)
    assert r["status"] == "FAIL" and "finding_agent" in r["detail"]


def test_g25_fails_artifact_not_colocated(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    _uv(out / "BugReport", "computer-software", "SW-RUN-1-0001",
        artifacts={"screenshot_path": "BugReport/test-pagination-behavior/screenshots/SW-RUN-1-0001.png"})
    r = G.g25_unverified_layout(out)
    assert r["status"] == "FAIL" and "co-located" in r["detail"]
