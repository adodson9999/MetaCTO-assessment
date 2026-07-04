#!/usr/bin/env python3
"""Unit test 1 (§7.4) — build_category over every category_cases entry.

Pure Python, NO model. Drives the golden category_cases table and pins the explicit
V > B > S precedence plus the empty-signal default (computer-software). This is the
deterministic forcing function for the classifier — it must always pass exactly.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_bugreport_category.py
"""
from __future__ import annotations

import pytest

import uv_helpers as H

import bugreport_spec as B  # noqa: E402  (sys.path primed by uv_helpers)

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


@pytest.mark.parametrize("case", _GOLDEN["category_cases"], ids=lambda c: c["id"])
def test_category_cases(case: dict) -> None:
    signals = B.normalize_signals(**H.expand_signals(case["signals"]))
    got = B.build_category(signals)
    assert got == case["expect_category"], (
        f"{case['id']}: expected {case['expect_category']} got {got} "
        f"for signals {case['signals']}"
    )
    assert got in B.UNVERIFIED_CATEGORIES


def test_empty_signals_default_is_computer_software() -> None:
    assert B.build_category(B.normalize_signals()) == "computer-software"
    assert B.build_category({}) == "computer-software"


def test_precedence_v_over_b_over_s() -> None:
    # A signal set that satisfies V (deny->2xx) AND B tokens AND an S token: V must win.
    v_and_b_and_s = B.normalize_signals(
        expected="401", observed="200 data", scenario_text="user list", stderr="exception"
    )
    assert B.build_category(v_and_b_and_s) == "vulnerability"
    # No V, but B tokens present AND no system signal: B must win over the S default.
    b_over_s = B.normalize_signals(expected="sorted", observed="wrong data", scenario_text="product list")
    assert B.build_category(b_over_s) == "business-workflow"
    # No V, B vetoed by a system signal: falls through to S.
    s_default = B.normalize_signals(expected="200", observed="500 error", scenario_text="product list")
    assert B.build_category(s_default) == "computer-software"


def test_category_never_overrides_severity() -> None:
    # decision #9: category is orthogonal to severity — build_severity is unchanged.
    case = _GOLDEN["severity_retention_cases"][0]
    failure = case["failure"]
    decision = B.build_reference_decision(failure, [], {}, verdict="missing-docs")
    assert decision["category"] == case["expect_category"]
    assert B.build_severity(failure) == case["expect_severity"]
    # severity is still present in the decision, unchanged by the category addition.
    assert decision["severity"] == case["expect_severity"]
