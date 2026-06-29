#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-validate-retry-after-header-compliance.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import retryafter  # noqa: E402
from retryafter_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-retry-after-header-compliance.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = retryafter.endpoint_brief(cfg)
        return retryafter.extract_json(invoke(brief)) or {}

    summary = retryafter.run_retryafter_test(AGENT, generate)
    print(f"[{AGENT}] retry_after_accuracy_pct={summary['retry_after_accuracy_pct']}% endpoints_honored={summary['endpoints_honored']} rate_limit_enforced={summary['rate_limit_enforced']}")


if __name__ == "__main__":
    main()
