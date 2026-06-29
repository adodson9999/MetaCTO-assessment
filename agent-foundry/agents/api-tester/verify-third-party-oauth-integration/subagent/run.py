#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-verify-third-party-oauth-integration.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import oauth  # noqa: E402
from oauth_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-verify-third-party-oauth-integration"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-third-party-oauth-integration.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = oauth.flow_brief(cfg)
        return oauth.extract_json(invoke(brief)) or {}

    summary = oauth.run_oauth_test(AGENT, generate)
    print(f"[{AGENT}] oauth_flow_completion_rate_pct={summary['oauth_flow_completion_rate_pct']}%")


if __name__ == "__main__":
    main()
