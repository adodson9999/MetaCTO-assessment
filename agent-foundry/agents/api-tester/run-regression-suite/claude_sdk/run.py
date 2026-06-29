#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for api-tester-run-regression-suite.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import regression  # noqa: E402
from regression_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-run-regression-suite.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = regression.pair_brief(cfg)
        return regression.extract_json(invoke(brief)) or {}

    summary = regression.run_regression_test(AGENT, generate)
    print(f"[{AGENT}] regression_report_fidelity_pct={summary['regression_report_fidelity_pct']}% builds_that_must_block_deployment={summary['builds_that_must_block_deployment']}")


if __name__ == "__main__":
    main()
