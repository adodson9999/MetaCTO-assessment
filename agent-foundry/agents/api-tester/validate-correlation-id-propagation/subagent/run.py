#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-validate-correlation-id-propagation.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import cid  # noqa: E402
from cid_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-validate-correlation-id-propagation"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-correlation-id-propagation.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return cid.extract_json(invoke(brief)) or {}

    summary = cid.run_cid_test(AGENT, generate)
    print(f"[{AGENT}] propagation_rate={summary['correlation_id_propagation_rate_pct']}% propagated={summary['scenarios_propagated']}/{summary['scenarios_total']}")


if __name__ == "__main__":
    main()
