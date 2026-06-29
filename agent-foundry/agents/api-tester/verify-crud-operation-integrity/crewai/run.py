#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for api-tester-verify-crud-operation-integrity.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import crud_contract  # noqa: E402
from crud_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-crud-operation-integrity.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(resource: dict) -> dict:
        brief = crud_contract.resource_brief(resource)
        return crud_contract.extract_json(invoke(brief)) or {}

    summary = crud_contract.run_crud_test(AGENT, generate)
    print(f"[{AGENT}] crud_integrity_rate_pct={summary['crud_integrity_rate_pct']}%")


if __name__ == "__main__":
    main()
