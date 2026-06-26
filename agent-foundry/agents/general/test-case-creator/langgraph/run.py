#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for general-test-case-creator.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import testcase  # noqa: E402
from testcase_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "general-test-case-creator.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> list:
        brief = testcase.agent_brief(cfg)
        return testcase.extract_json_array(invoke(brief)) or []

    summary = testcase.run_testcase_test(AGENT, generate)
    print(f"[{AGENT}] coverage_rate={summary['test_case_coverage_rate_pct']}% field_accuracy={summary['test_case_field_accuracy_pct']}% cases={summary['present_tc']}/{summary['gold_tc']}")


if __name__ == "__main__":
    main()
