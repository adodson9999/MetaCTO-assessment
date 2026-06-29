#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for api-tester-validate-api-versioning-behavior.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import versioning  # noqa: E402
from versioning_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-api-versioning-behavior.md"


TOTALS: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _add_usage(meta: dict | None) -> None:
    if not meta:
        return
    TOTALS["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
    TOTALS["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
    TOTALS["total_tokens"] += int(meta.get("total_tokens", 0) or 0)



def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = versioning.endpoint_brief(cfg)
        return versioning.extract_json(invoke(brief)) or {}

    summary = versioning.run_versioning_test(AGENT, generate, usage=lambda: TOTALS)
    print(f"[{AGENT}] version_routing_accuracy_pct={summary['version_routing_accuracy_pct']}% tokens={summary['tokens']['total_tokens']}")


if __name__ == "__main__":
    main()
