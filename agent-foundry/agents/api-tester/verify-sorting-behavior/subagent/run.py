#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-verify-sorting-behavior.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import sorting  # noqa: E402
from sorting_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-verify-sorting-behavior"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-sorting-behavior.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = sorting.resource_brief(cfg)
        return sorting.extract_json(invoke(brief)) or {}

    summary = sorting.run_sorting_test(AGENT, generate)
    print(f"[{AGENT}] sorting_accuracy_rate_pct={summary['sorting_accuracy_rate_pct']}%")


if __name__ == "__main__":
    main()
