#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-validate-request-payloads.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import contract  # noqa: E402
from prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-validate-request-payloads"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-request-payloads.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(endpoint: dict) -> dict:
        brief = contract.endpoint_brief(endpoint)
        return contract.extract_json(invoke(brief)) or {}

    summary = contract.run_contract_test(AGENT, generate)
    # contract.run_contract_test returns coverage={"produced_cases": N} (no "covered"/"applicable").
    # Read defensively so a summary-shape change never crashes AFTER artifacts are written.
    coverage = summary.get("coverage", {})
    produced = coverage.get("produced_cases", summary.get("produced_cases", "?"))
    rejection = summary.get("payload_rejection_rate_pct", "?")
    print(f"[{AGENT}] payload_rejection_rate_pct={rejection}% produced_cases={produced}")


if __name__ == "__main__":
    main()
