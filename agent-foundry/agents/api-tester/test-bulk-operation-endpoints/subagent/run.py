#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-test-bulk-operation-endpoints.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import bulk  # noqa: E402
from bulk_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-test-bulk-operation-endpoints"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-bulk-operation-endpoints.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = bulk.brief(cfg)
        return bulk.extract_json(invoke(brief)) or {}

    summary = bulk.run_bulk_test(AGENT, generate)
    print(f"[{AGENT}] bulk_operation_accuracy_pct={summary['bulk_operation_accuracy_pct']}% mixed_db_delta={summary['mixed_db_delta']}")


if __name__ == "__main__":
    main()
