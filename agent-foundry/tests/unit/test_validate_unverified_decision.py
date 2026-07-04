#!/usr/bin/env python3
"""Unit test 4 (§7.4) — the output guardrail validate_unverified_decision (G-VALIDATE).

Pure Python, NO model. A pass/fail table over the structural validator: exactly the six keys,
severity in the enum, priority consistent with severity, category in the enum, testing_steps
null|non-empty, postman_references a list.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_validate_unverified_decision.py
"""
from __future__ import annotations

import json
import sys

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GUARD = H.WS / "agents" / "general" / "bug-reporter" / "guardrails"
sys.path.insert(0, str(_GUARD))
import validate_unverified_decision as V  # noqa: E402


def _obj(**over):
    base = {"title": "[a] s on /x — expected 401, observed 200 (undocumented)",
            "severity": "CRITICAL", "priority": "P1", "category": "vulnerability",
            "testing_steps": [{"tc_id": "UV-a-1"}], "postman_references": []}
    base.update(over)
    return base


PASS_CASES = [
    ("ok-vuln", _obj()),
    ("ok-null-steps", _obj(testing_steps=None)),
    ("ok-biz-medium", _obj(severity="MEDIUM", priority="P3", category="business-workflow")),
    ("ok-sw-low", _obj(severity="LOW", priority="P4", category="computer-software")),
    ("ok-high-p2", _obj(severity="HIGH", priority="P2")),
]

FAIL_CASES = [
    ("missing-category", {k: v for k, v in _obj().items() if k != "category"}),
    ("extra-key", _obj(source_of_truth={"file": "x"})),
    ("bad-severity", _obj(severity="BLOCKER")),
    ("priority-inconsistent", _obj(severity="CRITICAL", priority="P3")),
    ("bad-category", _obj(category="performance")),
    ("empty-steps-list", _obj(testing_steps=[])),
    ("postman-not-list", _obj(postman_references={})),
    ("empty-title", _obj(title="")),
]


@pytest.mark.parametrize("name,obj", PASS_CASES, ids=[c[0] for c in PASS_CASES])
def test_valid_decisions_pass(name, obj) -> None:
    result = V.validate(json.dumps(obj))
    assert result.ok is True, (name, result.errors)


@pytest.mark.parametrize("name,obj", FAIL_CASES, ids=[c[0] for c in FAIL_CASES])
def test_invalid_decisions_fail(name, obj) -> None:
    result = V.validate(json.dumps(obj))
    assert result.ok is False, name


def test_rejects_fence_and_prose_and_empty() -> None:
    assert V.validate("```json\n" + json.dumps(_obj()) + "\n```").ok is False
    assert V.validate("here you go: " + json.dumps(_obj())).ok is False
    assert V.validate("   ").ok is False
    assert V.validate("[1,2,3]").ok is False


def test_cli_exit_codes(tmp_path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_obj()))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_obj(category="nope")))
    assert V.main([sys.argv[0], str(good)]) == 0
    assert V.main([sys.argv[0], str(bad)]) == 1
