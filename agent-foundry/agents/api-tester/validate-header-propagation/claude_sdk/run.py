#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for api-tester-validate-header-propagation.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import header  # noqa: E402
from header_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-header-propagation.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(endpoint: dict) -> dict:
        brief = header.endpoint_brief(endpoint)
        return header.extract_json(invoke(brief)) or {}

    summary = header.run_header_test(AGENT, generate)
    print(f"[{AGENT}] header_propagation_rate_pct={summary['header_propagation_rate_pct']}%")


if __name__ == "__main__":
    main()
