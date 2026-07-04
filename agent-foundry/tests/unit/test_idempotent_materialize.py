#!/usr/bin/env python3
"""Unit test 17 (§7.4) — HF26 determinism / idempotency.

Pure Python, NO model. Materialising the same ledger twice with the same
FORGE_BUG_DATE/FORGE_BUG_TIME/run_id produces byte-identical report files AND byte-identical
indexes. Proven by hashing every artifact of two independent materialisations.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_idempotent_materialize.py
"""
from __future__ import annotations

import hashlib

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_GOLDEN = H.load_golden()


def _materialize_into(sub, deterministic_time_applied: bool):
    case = _GOLDEN["idempotency_cases"]
    BR = H.load_bugreport(sub)
    H.materialize_unverified(BR, case["run_id"], case["rows"], db_available=False, workspace=sub)
    bp = BR.bug_paths(case["run_id"], workspace=sub)
    return bp


def _digest_tree(tree) -> dict:
    """{relative-json-path -> sha256} for every JSON file under the BugReport tree."""
    out = {}
    for p in sorted(tree.rglob("*.json")):
        out[str(p.relative_to(tree))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_double_materialization_byte_identical(deterministic_time, tmp_path) -> None:
    a = tmp_path / "runA"
    b = tmp_path / "runB"
    a.mkdir()
    b.mkdir()
    bp_a = _materialize_into(a, True)
    bp_b = _materialize_into(b, True)
    da = _digest_tree(bp_a.tree)
    db = _digest_tree(bp_b.tree)
    assert da == db, "materialisation is not byte-identical across runs (HF26)"
    # index files are among the hashed set and must be present + identical
    assert "unverified-index.json" in da
    assert da["unverified-index.json"] == db["unverified-index.json"]
