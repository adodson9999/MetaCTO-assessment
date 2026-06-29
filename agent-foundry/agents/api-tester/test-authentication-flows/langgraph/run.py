#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-test-authentication-flows.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import auth_harness  # noqa: E402
from auth_prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-authentication-flows.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    brief = auth_harness.scheme_brief()

    def generate() -> dict:
        return auth_harness.extract_json(invoke(brief)) or {}

    summary = auth_harness.run_auth_test(AGENT, generate)
    print(f"[{AGENT}] pass_rate={summary['auth_flow_pass_rate_pct']}% FAR={summary['false_acceptance_rate_pct']}% FRR={summary['false_rejection_rate_pct']}% executed={summary['executed_cases']}")


if __name__ == "__main__":
    main()
