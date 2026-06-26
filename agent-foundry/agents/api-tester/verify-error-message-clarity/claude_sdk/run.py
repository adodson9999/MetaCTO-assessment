#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for api-tester-verify-error-message-clarity.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import clarity_contract  # noqa: E402
from clarity_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-error-message-clarity.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(op: dict) -> dict:
        brief = clarity_contract.operation_brief(op)
        return clarity_contract.extract_json(invoke(brief)) or {}

    summary = clarity_contract.run_clarity_test(AGENT, generate)
    print(f"[{AGENT}] error_clarity_pass_rate_pct={summary['error_clarity_pass_rate_pct']}% p1_security_defects={summary['p1_security_defects']}")


if __name__ == "__main__":
    main()
