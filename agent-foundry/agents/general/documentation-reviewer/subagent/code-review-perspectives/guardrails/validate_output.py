#!/usr/bin/env python3
"""Output guardrail for code-review-perspective agents.

Deterministic, stdlib-only. Given the raw text an agent produced, this decides
whether it is a valid review verdict: exactly one bare JSON object with exactly
two keys, ``rating`` (int 0-100) and ``notes`` (non-empty string).

It never judges the *content* of the notes (prose is not deterministic). It only
enforces structure -- which is the part a non-deterministic LLM can and must be
forced to get right. Same input, same verdict, every time.

Usage:
    echo '{"rating": 90, "notes": "..."}' | python validate_output.py
    python validate_output.py path/to/agent_output.txt

Exit code 0 = valid, 1 = invalid. On invalid, the reasons are printed to stderr.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

ALLOWED_KEYS = ("rating", "notes")
RATING_MIN = 0
RATING_MAX = 100


@dataclass(frozen=True)
class Result:
    """Outcome of validating one agent output."""

    ok: bool
    errors: tuple[str, ...]
    value: dict[str, Any] | None


def parse_one_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse exactly one bare JSON object from ``raw``.

    Rejects code fences, leading/trailing prose, and more than one value. This
    strictness is intentional: the prompt tells the agent to emit only the
    object, so anything else is a guardrail failure, not something to clean up.
    """
    text = raw.strip()
    if not text:
        return None, "output is empty"
    if text.startswith("```"):
        return None, "output is wrapped in a code fence; emit the bare JSON object only"
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"output is not a single valid JSON value: {exc.msg} (line {exc.lineno}, col {exc.colno})"
    if not isinstance(obj, dict):
        return None, f"top-level JSON value must be an object, got {type(obj).__name__}"
    return obj, None


def validate_object(obj: dict[str, Any]) -> list[str]:
    """Return a list of structural errors for a parsed object (empty == valid)."""
    errors: list[str] = []

    keys = set(obj.keys())
    allowed = set(ALLOWED_KEYS)
    missing = allowed - keys
    extra = keys - allowed
    if missing:
        errors.append(f"missing required key(s): {sorted(missing)}")
    if extra:
        errors.append(f"unexpected key(s) present: {sorted(extra)} (only {list(ALLOWED_KEYS)} allowed)")

    if "rating" in obj:
        rating = obj["rating"]
        # bool is a subclass of int in Python; reject it explicitly.
        if isinstance(rating, bool) or not isinstance(rating, int):
            errors.append(f"'rating' must be an integer, got {type(rating).__name__}")
        elif rating < RATING_MIN or rating > RATING_MAX:
            errors.append(f"'rating' must be between {RATING_MIN} and {RATING_MAX}, got {rating}")

    if "notes" in obj:
        notes = obj["notes"]
        if not isinstance(notes, str):
            errors.append(f"'notes' must be a string, got {type(notes).__name__}")
        elif notes.strip() == "":
            errors.append("'notes' must be a non-empty string")

    return errors


def validate(raw: str) -> Result:
    """Full pipeline: parse one object, then check structure."""
    obj, parse_err = parse_one_object(raw)
    if parse_err is not None:
        return Result(ok=False, errors=(parse_err,), value=None)
    assert obj is not None
    errors = validate_object(obj)
    return Result(ok=not errors, errors=tuple(errors), value=obj if not errors else None)


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = sys.stdin.read()

    result = validate(raw)
    if result.ok:
        print("PASS")
        return 0
    print("FAIL", file=sys.stderr)
    for err in result.errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
