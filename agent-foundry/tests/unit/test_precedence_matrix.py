#!/usr/bin/env python3
"""Unit test 7 (§7.4) — the full V/B/S conflict matrix (HF14).

Pure Python, NO model. Drives precedence_matrix_cases: V+B->V, V+S->V,
B+S(system present)->S, B+S(user-visible only)->B, all-three->V. Guards against a
silent rule reordering — if someone moves the S check ahead of B, or B ahead of V,
one of these rows breaks.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_precedence_matrix.py
"""
from __future__ import annotations

import pytest

import uv_helpers as H

import bugreport_spec as B  # noqa: E402

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


@pytest.mark.parametrize("case", _GOLDEN["precedence_matrix_cases"], ids=lambda c: c["id"])
def test_precedence_matrix(case: dict) -> None:
    signals = B.normalize_signals(**H.expand_signals(case["signals"]))
    got = B.build_category(signals)
    assert got == case["expect_category"], (
        f"precedence {case['id']}: expected {case['expect_category']} got {got}"
    )
