#!/usr/bin/env python3
"""Deterministic test of the documentation-gated BugReport builder (run_pipeline.build_bug_reports),
with the LLM documentation-reviewer STUBBED so the policy is verified without a live model:

  bug  <=>  agent observed a mismatch (Fail)  AND  reviewer verdict == "yes" (a matching doc line)

Asserts:
  * a "yes" verdict -> BugReport/<agent>/{cases.json,cases.md} containing the FAILED test case
    enriched with the documentation evidence (file/line/text/source_url).
  * a non-"yes" verdict (no/missing-docs) -> NO BugReport folder for that agent.
  * a Fail with no parseable value -> never sent to the reviewer.

Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_bug_report_builder.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]   # agent-foundry
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))

import run_pipeline as R
import adjudicate as A
import docreview


def _tc(tc_id: str, expected: str, actual: str, status: str = "Fail") -> dict:
    return {"test_case_id": tc_id, "title_summary": f"{tc_id} scenario",
            "preconditions": "x", "test_steps": ["1. do"], "test_data": {},
            "expected_result": expected, "actual_result": actual, "status": status}


def _fail(tc: dict) -> dict:
    return {"tc": tc, "expected": R._val(tc["expected_result"]),
            "observed": R._val(tc["actual_result"]), "scenario": tc["title_summary"]}


def _install_stub_reviewer(verdict_queue: list[dict]):
    """Stub the corpus + reviewer so build_bug_reports is fully deterministic."""
    A.build_corpus = lambda: [
        {"file": "references/dummyjson-com/dummyjson-com-docs-auth.md", "folder": "references",
         "modified": "2026-01-01", "lines": [{"line": 9, "text": "Missing/invalid token returns 401."}]}]
    A._reviewer_invoke = lambda: (lambda brief: "STUB")
    q = list(verdict_queue)
    docreview.extract_json = lambda _text: (q.pop(0) if q else {})


def test_bug_report_gate():
    orig = (A.build_corpus, A._reviewer_invoke, docreview.extract_json)
    try:
        # agentA: mismatch the reviewer CONFIRMS (yes). agentB: reviewer says no.
        _install_stub_reviewer([
            {"verdict": "yes", "reason": "doc says 401",
             "source_of_truth": {"file": "references/dummyjson-com/dummyjson-com-docs-auth.md",
                                 "line": 9, "text": "Missing/invalid token returns 401."}},
            {"verdict": "no", "reason": "no matching doc line", "source_of_truth": None},
        ])
        per_agent = {
            "check-authorization-rules": {"cases": [], "fails": [_fail(_tc("TC-AUTHZ-001", "The API returns 401.", "The API returned 200."))]},
            "verify-sorting-behavior": {"cases": [], "fails": [_fail(_tc("TC-SORT-001", "The API returns sorted.", "The API returned unsorted."))]},
        }
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "2026-06-29" / "12-00-00"
            summary = R.build_bug_reports(out, per_agent, bug_limit=10, do_bugs=True)
            br = out / "BugReport"
            # agentA confirmed -> folder with evidence
            ca = br / "check-authorization-rules"
            assert ca.is_dir(), "confirmed agent must get a BugReport folder"
            assert {f.name for f in ca.iterdir()} == {"cases.json", "cases.md"}, "lowercase cases.json+cases.md"
            bug = json.loads((ca / "cases.json").read_text())[0]
            assert bug["test_case_id"] == "TC-AUTHZ-001" and bug["status"] == "Fail"
            doc = bug["bug"]["documentation"]
            assert doc["line"] == 9 and "401" in doc["text"], "must carry the documentation evidence"
            assert doc["source_url"] == "https://dummyjson.com/docs/auth", "source_url mapped from file"
            # agentB not confirmed -> NO folder
            assert not (br / "verify-sorting-behavior").exists(), "unconfirmed agent must get NO folder"
            assert summary["bugs"] == 1 and summary["agents_with_bugs"] == 1 and summary["reviewed"] == 2
    finally:
        A.build_corpus, A._reviewer_invoke, docreview.extract_json = orig


def test_unparseable_fail_not_reviewed():
    orig = (A.build_corpus, A._reviewer_invoke, docreview.extract_json)
    try:
        _install_stub_reviewer([])  # queue empty: if anything is reviewed, extract_json returns {}
        # a Fail whose prose carries no value token -> expected/observed parse to None -> skipped
        nested = {"tc": _tc("TC-X-001", "Every step succeeds.", "A step regressed."),
                  "expected": None, "observed": None, "scenario": "nested"}
        per_agent = {"verify-crud-operation-integrity": {"cases": [], "fails": [nested]}}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "2026-06-29" / "12-00-00"
            summary = R.build_bug_reports(out, per_agent, bug_limit=10, do_bugs=True)
            assert summary["reviewed"] == 0, "unparseable fails must not reach the reviewer"
            assert not (out / "BugReport").exists()
    finally:
        A.build_corpus, A._reviewer_invoke, docreview.extract_json = orig


def test_core_agents_not_starved_by_high_volume_agent():
    """Regression: a high-volume agent must NOT consume the whole bug-limit before the core agents
    are adjudicated. With bug_limit=2 and a noisy 5-fail non-core agent listed FIRST, the single
    core-agent mismatch must still be reviewed (core agents are adjudicated first)."""
    orig = (A.build_corpus, A._reviewer_invoke, docreview.extract_json)
    try:
        reviewed = []
        A.build_corpus = lambda: [{"file": "auth.md", "folder": "f", "modified": "2026",
                                   "lines": [{"line": 1, "text": "x"}]}]
        A._reviewer_invoke = lambda: (lambda brief: reviewed.append(brief) or "STUB")
        docreview.extract_json = lambda _t: {"verdict": "no"}
        core_agent = next(iter(R.CORE_AGENTS))   # a real core agent (e.g. test-authentication-flows)
        per_agent = {
            "validate-request-payloads": {"cases": [],   # listed FIRST, 5 noisy fails
                "fails": [_fail(_tc(f"TC-REQPAY-{i}", "The API returns 400.", "The API returned 500.")) for i in range(5)]},
            core_agent: {"cases": [],
                "fails": [{"tc": _tc("TC-AUTH-MAL", "The API returns 401.", "The API returned 500."),
                           "expected": "401", "observed": "500", "scenario": "CORE-MALFORMED-MARKER"}]},
        }
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "2026-06-29" / "12-00-00"
            R.build_bug_reports(out, per_agent, bug_limit=2, do_bugs=True)
        assert any("CORE-MALFORMED-MARKER" in b for b in reviewed), \
            "core-agent mismatch was starved by the high-volume agent (prioritization regressed)"
        assert len(reviewed) == 2, f"bug_limit not honoured: {len(reviewed)} reviewed"
    finally:
        A.build_corpus, A._reviewer_invoke, docreview.extract_json = orig


def main() -> int:
    tests = [test_bug_report_gate, test_unparseable_fail_not_reviewed,
             test_core_agents_not_starved_by_high_volume_agent]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
