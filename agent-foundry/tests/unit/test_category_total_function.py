#!/usr/bin/env python3
"""Optional property test (§7.4) — build_category totality + determinism under fuzzing.

Pure Python, NO model. Uses hypothesis if available; otherwise a stdlib randomized loop
seeded deterministically (Date/random are avoided in workflow scripts, but this is a plain
test module, so a fixed-seed Random is fine and reproducible). Asserts:
  * totality  — build_category never raises and always returns a legal category, for
    arbitrary text in every signal field;
  * determinism — the same input yields the same output.

Run: python3 -m pytest -m unit agent-foundry/tests/unit/test_category_total_function.py
"""
from __future__ import annotations

import random

import pytest

import uv_helpers  # noqa: F401  (side-effect: primes sys.path for bugreport_spec)

import bugreport_spec as B  # noqa: E402

pytestmark = pytest.mark.unit

_FIELDS = ("expected", "observed", "spec_path", "agent", "scenario_text", "stderr")
_ALPHABET = "abcAB 0123 401 200 500 database data user without password ☃ 你好 \t\n{}[]:,\"'"


def _rand_signals(rng: random.Random) -> dict:
    return {f: "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(0, 40))) for f in _FIELDS}


def test_totality_and_determinism_stdlib_fuzz() -> None:
    rng = random.Random(1729)
    for _ in range(3000):
        raw = _rand_signals(rng)
        sig = B.normalize_signals(**raw)
        got = B.build_category(sig)
        assert got in B.UNVERIFIED_CATEGORIES
        assert B.build_category(sig) == got  # deterministic on repeat


try:  # pragma: no cover - only when hypothesis is installed
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _text = st.text(max_size=200)

    @settings(max_examples=300, deadline=None)
    @given(_text, _text, _text, _text, _text, _text)
    def test_totality_hypothesis(a: str, b: str, c: str, d: str, e: str, f: str) -> None:
        sig = B.normalize_signals(expected=a, observed=b, spec_path=c, agent=d,
                                  scenario_text=e, stderr=f)
        got = B.build_category(sig)
        assert got in B.UNVERIFIED_CATEGORIES
        assert B.build_category(sig) == got
except ImportError:  # hypothesis not installed — the stdlib fuzz above still runs.
    pass
