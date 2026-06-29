#!/usr/bin/env python3
"""Unit tests for the output guardrail (guardrails/validate_output.py).

These pin the structural contract every reviewer agent must satisfy. Pure
Python, no LLM, fully deterministic. Run with: pytest -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make guardrails/validate_output.py importable regardless of cwd.
GUARDRAILS = Path(__file__).resolve().parents[1] / "guardrails"
sys.path.insert(0, str(GUARDRAILS))

import validate_output as vo  # noqa: E402


# ---- valid outputs -----------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "rating",
    [0, 1, 42, 99, 100],
)
def test_valid_ratings_across_range(rating: int) -> None:
    raw = json.dumps({"rating": rating, "notes": "reason and the fix to reach 100"})
    assert vo.validate(raw).ok


@pytest.mark.unit
def test_valid_100_with_no_change_note() -> None:
    raw = json.dumps({"rating": 100, "notes": "No problems found through the lens; no change needed."})
    res = vo.validate(raw)
    assert res.ok
    assert res.value == {"rating": 100, "notes": "No problems found through the lens; no change needed."}


@pytest.mark.unit
def test_key_order_does_not_matter() -> None:
    raw = '{"notes": "x", "rating": 50}'
    assert vo.validate(raw).ok


# ---- rating must be an integer in range -------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("bad", [-1, 101, 1000, -50])
def test_rating_out_of_range_fails(bad: int) -> None:
    raw = json.dumps({"rating": bad, "notes": "x"})
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_rating_float_fails() -> None:
    raw = '{"rating": 90.5, "notes": "x"}'
    res = vo.validate(raw)
    assert not res.ok
    assert any("integer" in e for e in res.errors)


@pytest.mark.unit
def test_rating_string_fails() -> None:
    raw = '{"rating": "90", "notes": "x"}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_rating_bool_fails() -> None:
    # True is an int subclass in Python; the guardrail must reject it.
    raw = '{"rating": true, "notes": "x"}'
    res = vo.validate(raw)
    assert not res.ok
    assert any("integer" in e for e in res.errors)


@pytest.mark.unit
def test_rating_as_range_string_fails() -> None:
    raw = '{"rating": "90-100", "notes": "x"}'
    assert not vo.validate(raw).ok


# ---- notes must be a non-empty string ---------------------------------------

@pytest.mark.unit
def test_empty_notes_fails() -> None:
    raw = '{"rating": 80, "notes": ""}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_whitespace_notes_fails() -> None:
    raw = '{"rating": 80, "notes": "   "}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_notes_non_string_fails() -> None:
    raw = '{"rating": 80, "notes": ["a", "b"]}'
    assert not vo.validate(raw).ok


# ---- exactly two keys --------------------------------------------------------

@pytest.mark.unit
def test_missing_notes_fails() -> None:
    raw = '{"rating": 80}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_missing_rating_fails() -> None:
    raw = '{"notes": "x"}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_extra_key_fails() -> None:
    raw = '{"rating": 80, "notes": "x", "severity": "high"}'
    res = vo.validate(raw)
    assert not res.ok
    assert any("unexpected key" in e for e in res.errors)


# ---- exactly one bare JSON object -------------------------------------------

@pytest.mark.unit
def test_non_json_fails() -> None:
    assert not vo.validate("the rating is 80 because ...").ok


@pytest.mark.unit
def test_code_fence_fails() -> None:
    raw = '```json\n{"rating": 80, "notes": "x"}\n```'
    res = vo.validate(raw)
    assert not res.ok
    assert any("code fence" in e for e in res.errors)


@pytest.mark.unit
def test_prose_before_object_fails() -> None:
    raw = 'Here is my review: {"rating": 80, "notes": "x"}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_prose_after_object_fails() -> None:
    raw = '{"rating": 80, "notes": "x"} -- hope that helps!'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_two_objects_fail() -> None:
    raw = '{"rating": 80, "notes": "x"}\n{"rating": 90, "notes": "y"}'
    assert not vo.validate(raw).ok


@pytest.mark.unit
def test_empty_output_fails() -> None:
    assert not vo.validate("").ok
    assert not vo.validate("   \n  ").ok


@pytest.mark.unit
def test_array_top_level_fails() -> None:
    raw = '[{"rating": 80, "notes": "x"}]'
    assert not vo.validate(raw).ok


# ---- surrounding whitespace is tolerated (a bare object with newlines) -------

@pytest.mark.unit
def test_surrounding_whitespace_ok() -> None:
    raw = '\n  {"rating": 80, "notes": "x"}  \n'
    assert vo.validate(raw).ok
