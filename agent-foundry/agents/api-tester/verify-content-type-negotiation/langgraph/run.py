#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-verify-content-type-negotiation.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import cn  # noqa: E402
from cn_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-content-type-negotiation.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message, multicaller=True)

    def generate(cfg: dict) -> dict:
        brief = cn.endpoint_brief(cfg)
        return cn.extract_json(invoke(brief)) or {}

    summary = cn.run_cn_test(AGENT, generate)
    print(f"[{AGENT}] content_type_negotiation_accuracy_pct={summary['content_type_negotiation_accuracy_pct']}%")


if __name__ == "__main__":
    main()
