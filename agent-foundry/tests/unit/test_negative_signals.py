#!/usr/bin/env python3
"""Unit test 8 (§7.4) — build_category is a TOTAL function (HF14 / decision #7).

Pure Python, NO model. Drives negative_signal_cases (empty strings, missing keys,
None values, non-ASCII/unicode, a 10 KB blob, mixed case, numeric-only) and asserts
build_category never raises and always returns a legal category, matching the pinned
default. This is the forcing function behind "build_category is total on arbitrary
input".

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_negative_signals.py
"""
from __future__ import annotations

import pytest

import uv_helpers as H

import bugreport_spec as B  # noqa: E402

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


@pytest.mark.parametrize("case", _GOLDEN["negative_signal_cases"], ids=lambda c: c["id"])
def test_negative_signals_are_total(case: dict) -> None:
    signals = B.normalize_signals(**H.expand_signals(case["signals"]))
    got = B.build_category(signals)  # must not raise
    assert got in B.UNVERIFIED_CATEGORIES
    assert got == case["expect_category"], (
        f"{case['id']}: expected {case['expect_category']} got {got}"
    )


def test_build_category_tolerates_non_dict() -> None:
    # A defensive belt: even a non-dict argument must not raise (returns the default).
    assert B.build_category(None) == "computer-software"  # type: ignore[arg-type]
    assert B.build_category("not a dict") == "computer-software"  # type: ignore[arg-type]


def test_normalize_signals_coerces_every_type() -> None:
    sig = B.normalize_signals(expected=200, observed=None, spec_path=object(),
                              agent=["x"], scenario_text=3.14, stderr=b"bytes")
    assert all(isinstance(v, str) for v in sig.values())
    assert sig["observed"] == ""  # None -> ""
