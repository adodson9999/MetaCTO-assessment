#!/usr/bin/env python3
"""Unit test 5 (§7.4) — unverified index ordering, by_category counts, separation (HF16/HF17/HF25).

Pure Python, NO model. Drives index_cases + ordering_stress_cases: category-first total
order (vulnerability first), correct per-category counts, and zero BUG- leakage into the
unverified index.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_unverified_index_order.py
"""
from __future__ import annotations

import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


def _write_and_read(BR, ws, case):
    BR.write_unverified_index(case["run_id"], case["reports"], workspace=ws)
    bp = BR.bug_paths(case["run_id"], workspace=ws)
    return json.loads(bp.unverified_index.read_text())


def test_index_cases_order_and_counts(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["index_cases"]
    index = _write_and_read(BR, ws, case)
    assert [b["bug_id"] for b in index["bugs"]] == case["expect_order"]
    assert index["by_category"] == case["expect_by_category"]
    # separation: no BUG- prefix anywhere in the unverified index
    assert all(not b["bug_id"].startswith(case["expect_no_prefix"]) for b in index["bugs"])
    # vulnerability sorts first (HF17)
    assert index["bugs"][0]["category"] == "vulnerability"


def test_ordering_stress_total_order(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["ordering_stress_cases"]
    index = _write_and_read(BR, ws, case)
    assert [b["bug_id"] for b in index["bugs"]] == case["expect_order"], (
        f"got {[b['bug_id'] for b in index['bugs']]}"
    )
    # tie-break proof: within vulnerability tier, CRITICAL precedes LOW, then finding_agent,
    # then bug_id — fully specified in the golden expect_order.


def test_index_is_stable_and_wallclock_free(bugreport) -> None:
    BR, ws = bugreport
    case = _GOLDEN["index_cases"]
    bp = BR.bug_paths(case["run_id"], workspace=ws)
    BR.write_unverified_index(case["run_id"], case["reports"], workspace=ws)
    first = bp.unverified_index.read_bytes()
    BR.write_unverified_index(case["run_id"], list(reversed(case["reports"])), workspace=ws)
    second = bp.unverified_index.read_bytes()
    assert first == second, "index ordering must be independent of input order (total sort)"
    assert b"generated_at" not in first, "no wall-clock in the idempotent index (HF26)"
