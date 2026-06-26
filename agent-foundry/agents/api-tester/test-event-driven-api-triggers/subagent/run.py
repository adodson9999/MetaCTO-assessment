#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-test-event-driven-api-triggers.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import eventdriven  # noqa: E402
from eventdriven_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-test-event-driven-api-triggers"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-event-driven-api-triggers.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = eventdriven.topic_brief(cfg)
        return eventdriven.extract_json(invoke(brief)) or {}

    summary = eventdriven.run_eventdriven_test(AGENT, generate)
    print(f"[{AGENT}] event_processing_success_rate_pct={summary['event_processing_success_rate_pct']}% dead_letter_queue_delivery_rate_pct={summary['dead_letter_queue_delivery_rate_pct']}%")


if __name__ == "__main__":
    main()
