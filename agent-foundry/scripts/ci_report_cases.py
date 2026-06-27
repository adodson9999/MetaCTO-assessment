#!/usr/bin/env python3
"""CI gate: report test-case-creator output for one agent and fail on ERROR sentinel.

Exit code 0: at least one valid test case was generated for the target agent.
Exit code 1: zero valid test cases, or an ERROR sentinel is present.

Env vars:
  FORGE_WORKSPACE       path to agent-foundry root (required)
  FORGE_TESTCASE_AGENT  when set, filters the registry to entries for this agent only.
                        Must match the "agent" field or "tc_id" prefix in the registry.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
TARGET    = os.environ.get("FORGE_TESTCASE_AGENT", "").strip()

registry_path = (
    WORKSPACE / "results" / "general" / "test-case-creator" / "test-case-registry.json"
)

if not registry_path.exists():
    print(
        f"[CI ERROR] test-case-registry.json not found at {registry_path}\n"
        "Check that FORGE_WORKSPACE is correct and the G1b step ran.",
        file=sys.stderr,
    )
    sys.exit(1)

data    = json.loads(registry_path.read_text())
entries: list[dict] = data if isinstance(data, list) else data.get("test_cases", [])

if TARGET:
    relevant = [
        e for e in entries
        if e.get("agent") == TARGET
        or str(e.get("tc_id", "")).startswith(f"TC-ERR-{TARGET}")
    ]
else:
    relevant = entries

errors = [
    e for e in relevant
    if e.get("outcome") == "ERROR"
    or str(e.get("tc_id", "")).startswith("TC-ERR-")
]
cases  = [e for e in relevant if e not in errors]
label  = TARGET or "all agents"

print(f"[CI] {label}: {len(cases)} test case(s) generated, {len(errors)} ERROR sentinel(s)")

if errors:
    for e in errors:
        print(
            f"  SENTINEL: {e.get('tc_id')} — {e.get('error', 'no detail')}",
            file=sys.stderr,
        )
    sys.exit(1)

if not cases:
    print(
        f"[CI ERROR] 0 test cases and 0 ERROR sentinels for {label}.\n"
        "Registry exists but contains no relevant entries.\n"
        "Check FORGE_TESTCASE_AGENT matches the manifest name exactly.",
        file=sys.stderr,
    )
    sys.exit(1)

sys.exit(0)
