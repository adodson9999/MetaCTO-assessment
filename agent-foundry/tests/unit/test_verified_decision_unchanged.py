#!/usr/bin/env python3
"""Unit test 6 (§7.4 / §7.5 regression guard) — the verified path is byte-identical.

Pure Python, NO model. The single most important invariant of this feature: adding the
unverified (missing-docs) classification must not perturb the scored 5-key contract for
verified bugs. This test recomputes build_reference_decision(...) with NO verdict for
every failure in the gold fixture and asserts it is byte-for-byte equal to the recorded
gold decision, and that score_decision over the five DECISION_FIELDS is unchanged.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_verified_decision_unchanged.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

import bugreport_spec as B  # noqa: E402

pytestmark = pytest.mark.unit

_GOLD = json.loads((H.WS / "data" / "bug-reporter" / "gold.json").read_text())
_FIXTURE = json.loads((H.WS / "data" / "bug-reporter" / "fixture.json").read_text())
_REGISTRY = _FIXTURE.get("registry", [])
_POSTMAN = B.build_postman_items(_FIXTURE.get("postman_collection", {}))
_FAILED = [a for a in _FIXTURE["pipeline_summary"]["agents"] if a.get("status") != "PASSED"]
_GOLD_BY_AGENT = {g["agent_name"]: g["decision"] for g in _GOLD["gold_decisions"]}


def test_decision_fields_list_unchanged() -> None:
    assert B.DECISION_FIELDS == ["title", "severity", "priority", "testing_steps", "postman_references"]
    assert B.DECISION_FIELDS_UNVERIFIED == B.DECISION_FIELDS + ["category"]


@pytest.mark.parametrize("failure", _FAILED, ids=lambda f: f["agent_name"])
def test_verified_decision_byte_identical(failure: dict) -> None:
    decision = B.build_reference_decision(failure, _REGISTRY, _POSTMAN)  # no verdict
    assert "category" not in decision
    assert set(decision.keys()) == set(B.DECISION_FIELDS)
    gold = _GOLD_BY_AGENT[failure["agent_name"]]
    # byte-identical serialization (ordering + values)
    assert json.dumps(decision, sort_keys=True) == json.dumps(gold, sort_keys=True)


@pytest.mark.parametrize("failure", _FAILED, ids=lambda f: f["agent_name"])
def test_score_decision_five_cells_for_verified(failure: dict) -> None:
    gold = _GOLD_BY_AGENT[failure["agent_name"]]
    cells = B.score_decision(gold, gold)
    assert set(cells.keys()) == set(B.DECISION_FIELDS)  # no "category" cell when gold has none
    assert all(cells.values())


def test_missing_docs_verdict_adds_exactly_one_key() -> None:
    failure = dict(_FAILED[0], expected="401", observed="200")
    base = B.build_reference_decision(failure, _REGISTRY, _POSTMAN)
    unv = B.build_reference_decision(failure, _REGISTRY, _POSTMAN, verdict="missing-docs")
    assert set(unv.keys()) - set(base.keys()) == {"category"}
    assert unv["category"] in B.UNVERIFIED_CATEGORIES
    # a non-missing-docs verdict never changes the output
    for v in ("yes", "no", None, "anything"):
        assert B.build_reference_decision(failure, _REGISTRY, _POSTMAN, verdict=v) == base
