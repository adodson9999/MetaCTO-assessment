#!/usr/bin/env python3
"""G26 documented-expectation gate: a VERIFIED (documentation-cited) bug's expected_result must
state the documented behavior in its own words — not a vague placeholder, and grounded in the
cited doc text (a reworded version passes; generic boilerplate fails). Uncited bugs are out of
scope.

Run:  agent-foundry/.venv/bin/python -m pytest agent-foundry/tests/test_documented_expectation_gate.py
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

DOC = "limit=0 clears the limit and you get all items"


def _bug(tmp_path, expected, *, cited=True, doctext=DOC):
    out = tmp_path / "2026-07-04" / "00-00-00"
    d = out / "BugReport" / "test-pagination-behavior" / "verified_bugs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "BUG-1.json").write_text(json.dumps({
        "id": "BUG-1", "expected_result": expected,
        "documentation": {"cited": cited, "text": doctext}}))
    return out


def test_g26_passes_verbatim_documented_expected(tmp_path):
    out = _bug(tmp_path, f'Per the documentation (docs.md:27): "{DOC}." Every check must conform.')
    r = G.g26_documented_expectation(out)
    assert r["status"] == "PASS" and r["hard"], r["detail"]


def test_g26_passes_synonym_rewording(tmp_path):
    out = _bug(tmp_path, "Setting limit to zero should remove the cap and return every item.")
    assert G.g26_documented_expectation(out)["status"] == "PASS"


def test_g26_fails_vague_placeholder(tmp_path):
    out = _bug(tmp_path, "All 18 checks pass against the documented behaviour")
    r = G.g26_documented_expectation(out)
    assert r["status"] == "FAIL" and "vague" in r["detail"] and r["hard"]


def test_g26_fails_empty_expected(tmp_path):
    out = _bug(tmp_path, "")
    assert G.g26_documented_expectation(out)["status"] == "FAIL"


def test_g26_fails_ungrounded_boilerplate(tmp_path):
    out = _bug(tmp_path, "The server should just work correctly and return something valid.")
    r = G.g26_documented_expectation(out)
    assert r["status"] == "FAIL" and "not grounded" in r["detail"]


def test_g26_ignores_uncited_bugs(tmp_path):
    """An uncited (unverified-style) bug's expected is the contract expectation, not doc-derived —
    G26 does not police it."""
    out = _bug(tmp_path, "All 18 checks pass against the documented behaviour", cited=False)
    assert G.g26_documented_expectation(out)["status"] == "PASS"


def test_g26_passes_when_no_verified_bugs(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    (out / "BugReport" / "unverified" / "computer-software").mkdir(parents=True)
    assert G.g26_documented_expectation(out)["status"] == "PASS"
