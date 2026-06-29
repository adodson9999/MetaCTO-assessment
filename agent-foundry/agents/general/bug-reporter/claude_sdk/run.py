#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for general-bug-reporter.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import bugreport  # noqa: E402
from bugreport_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "general-bug-reporter.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return bugreport.extract_json(invoke(brief)) or {}

    s = bugreport.run_bugreport_test(AGENT, generate)
    m = s["metrics"]
    print(f"[{AGENT}] fidelity={s['bug_report_fidelity_pct']}%"
          f" bugs={s['bug_count']}" f" completeness={m['bug_report_completeness_rate_pct']}%"
          f" exit1={m['would_exit_code_1']}")


if __name__ == "__main__":
    main()
