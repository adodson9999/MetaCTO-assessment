#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-test-ip-allowlist-enforcement.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import ip_allowlist  # noqa: E402
from ip_allowlist_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-ip-allowlist-enforcement.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = ip_allowlist.endpoint_brief(cfg)
        return ip_allowlist.extract_json(invoke(brief)) or {}

    summary = ip_allowlist.run_ip_allowlist_test(AGENT, generate)
    print(f"[{AGENT}] ip_allowlist_enforcement_rate_pct={summary['ip_allowlist_enforcement_rate_pct']}% any_nonallowlisted_200_bypass={summary['any_nonallowlisted_200_bypass']}")


if __name__ == "__main__":
    main()
