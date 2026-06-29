#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for api-tester-test-ssl-tls-enforcement.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import tls  # noqa: E402
from tls_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-ssl-tls-enforcement.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = tls.target_brief(cfg)
        return tls.extract_json(invoke(brief)) or {}

    summary = tls.run_tls_test(AGENT, generate)
    print(f"[{AGENT}] tls_enforcement_rate_pct={summary['tls_enforcement_rate_pct']}%")


if __name__ == "__main__":
    main()
