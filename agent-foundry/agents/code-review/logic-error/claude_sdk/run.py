#!/usr/bin/env python3
"""Thin dispatcher: claude_sdk runner for code-review-logic-error.

Delegates all framework boilerplate to common/runners/claude_sdk_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import logicerror  # noqa: E402
from logicerror_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.claude_sdk_runner import build_invoker  # noqa: E402

AGENT = "claude_sdk"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "code-review-logic-error.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return logicerror.extract_json(invoke(brief)) or {}

    s = logicerror.run_logicerror_test(AGENT, generate)
    print(f"[{AGENT}] rating_band_accuracy={s['rating_band_accuracy']}"
          f" cases={s['cases_total']}"
          f" schema_valid={s['schema_valid_pct']}%")


if __name__ == "__main__":
    main()
