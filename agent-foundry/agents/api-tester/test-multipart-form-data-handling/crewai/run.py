#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for api-tester-test-multipart-form-data-handling.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import multipart as mp  # noqa: E402
from multipart_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-multipart-form-data-handling.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = mp.endpoint_brief(cfg)
        return mp.extract_json(invoke(brief)) or {}

    summary = mp.run_multipart_test(AGENT, generate)
    print(f"[{AGENT}] multipart_handling_accuracy_pct={summary['multipart_handling_accuracy_pct']}%")


if __name__ == "__main__":
    main()
