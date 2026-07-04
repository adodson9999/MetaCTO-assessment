#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for api-tester-check-authorization-rules.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import authz_contract  # noqa: E402
from authz_prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-check-authorization-rules.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(spec: dict) -> dict:
        brief = authz_contract.surface_brief(spec)
        return authz_contract.extract_json(invoke(brief)) or {}

    summary = authz_contract.run_authz_test(AGENT, generate)
    print(f"[{AGENT}] access_control_accuracy_rate_pct={summary['access_control_accuracy_rate_pct']}% core_passed={summary['core_passed']}/{summary['core_sub_tests']}")


if __name__ == "__main__":
    main()
