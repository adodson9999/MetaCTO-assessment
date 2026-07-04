#!/usr/bin/env python3
"""Regression guard (§7.5 / G-DOC) — the documentation-reviewer is untouched by this feature.

Pure Python, NO model. The unverified-bug feature routes on the reviewer's EXISTING
"missing-docs" verdict; it must not edit the reviewer's contract or its judged baseline. This
guard pins:
  * the byte content of general-documentation-reviewer.md (hash), so any edit trips it;
  * the reviewer's judged golden baseline value (its recorded oracle ceiling).

If a future change legitimately re-hardens the reviewer, update these pins in the same commit
and record why — that is the whole point of the guard.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_docreviewer_baseline_unchanged.py
"""
from __future__ import annotations

import hashlib
import json

import pytest

import uv_helpers as H

pytestmark = pytest.mark.unit

_SPEC = (H.WS / "agents" / "general" / "documentation-reviewer" / "subagent"
         / "general-documentation-reviewer.md")
_GOLDEN = H.WS / "tests" / "golden" / "general" / "documentation-reviewer" / "golden.json"

# Pinned at unverified-bug feature time. Editing the reviewer spec for THIS feature is out of
# scope (§11) — a mismatch here means the reviewer contract drifted.
_SPEC_SHA256 = "4060daed16fc3d5ef8c713817624bcf437a328fd39d9ef2b2986a85f68108a65"
_BASELINE_VALUE = 100.0


def test_reviewer_spec_unedited() -> None:
    digest = hashlib.sha256(_SPEC.read_bytes()).hexdigest()
    assert digest == _SPEC_SHA256, (
        "general-documentation-reviewer.md changed — the unverified-bug feature must not edit "
        "the reviewer contract (§7.5 G-DOC / §11 out of scope)."
    )


def test_reviewer_baseline_unchanged() -> None:
    golden = json.loads(_GOLDEN.read_text())
    assert golden["baseline"]["value"] == _BASELINE_VALUE
    assert golden["baseline"]["direction"] == "higher_is_better"
