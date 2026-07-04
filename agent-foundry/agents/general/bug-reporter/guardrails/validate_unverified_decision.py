#!/usr/bin/env python3
"""Output guardrail for the bug-reporter's UNVERIFIED (missing-docs) decision.

Deterministic, stdlib-only. Given the raw text an agent produced for a missing-docs input,
this decides whether it is a valid unverified bug decision: exactly one bare JSON object with
exactly these six keys — title, severity, priority, category, testing_steps,
postman_references.

It never judges prose (non-deterministic); it enforces only structure — the part an LLM can
and must be forced to get right. Same input, same verdict, every time. (Mirror of the
code-review-perspectives validate_output.py; the constants are inlined so this stays a
zero-dependency structural gate.)

Usage:
    echo '{...}' | python validate_unverified_decision.py
    python validate_unverified_decision.py path/to/agent_output.txt

Exit code 0 = valid, 1 = invalid. On invalid, the reasons are printed to stderr.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

ALLOWED_KEYS = ("title", "severity", "priority", "category", "testing_steps", "postman_references")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
SEVERITY_TO_PRIORITY = {"CRITICAL": "P1", "HIGH": "P2", "MEDIUM": "P3", "LOW": "P4"}
UNVERIFIED_CATEGORIES = ("vulnerability", "business-workflow", "computer-software")


@dataclass(frozen=True)
class Result:
    """Outcome of validating one unverified decision."""

    ok: bool
    errors: tuple[str, ...]
    value: dict[str, Any] | None


def parse_one_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse exactly one bare JSON object; reject fences, prose, or more than one value."""
    text = raw.strip()
    if not text:
        return None, "output is empty"
    if text.startswith("```"):
        return None, "output is wrapped in a code fence; emit the bare JSON object only"
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, (f"output is not a single valid JSON value: {exc.msg} "
                      f"(line {exc.lineno}, col {exc.colno})")
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

    if "title" in obj and (not isinstance(obj["title"], str) or obj["title"].strip() == ""):
        errors.append("'title' must be a non-empty string")

    severity = obj.get("severity")
    if "severity" in obj and severity not in SEVERITIES:
        errors.append(f"'severity' must be one of {list(SEVERITIES)}, got {severity!r}")

    if "priority" in obj:
        priority = obj["priority"]
        if severity in SEVERITIES and priority != SEVERITY_TO_PRIORITY[severity]:
            errors.append(f"'priority' {priority!r} inconsistent with severity {severity!r} "
                          f"(expected {SEVERITY_TO_PRIORITY[severity]})")
        elif severity not in SEVERITIES and priority not in SEVERITY_TO_PRIORITY.values():
            errors.append(f"'priority' must be one of {sorted(set(SEVERITY_TO_PRIORITY.values()))}, "
                          f"got {priority!r}")

    if "category" in obj and obj["category"] not in UNVERIFIED_CATEGORIES:
        errors.append(f"'category' must be one of {list(UNVERIFIED_CATEGORIES)}, got {obj['category']!r}")

    if "testing_steps" in obj:
        ts = obj["testing_steps"]
        if ts is not None and not (isinstance(ts, list) and len(ts) > 0):
            errors.append("'testing_steps' must be null or a non-empty list")

    if "postman_references" in obj and not isinstance(obj["postman_references"], list):
        errors.append("'postman_references' must be a list")

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
