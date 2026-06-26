#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for api-tester-validate-null-empty-fields.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import null_contract  # noqa: E402
from null_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-null-empty-fields.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(ep: dict) -> dict:
        brief = null_contract.endpoint_brief(ep)
        return null_contract.extract_json(invoke(brief)) or {}

    summary = null_contract.run_null_test(AGENT, generate)
    print(f"[{AGENT}] accuracy={summary['null_empty_validation_accuracy_pct']}% cases={summary['total_cases']}")


if __name__ == "__main__":
    main()
