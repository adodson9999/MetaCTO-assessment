#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-validate-query-parameter-handling.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import queryparam  # noqa: E402
from queryparam_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-query-parameter-handling.md"


TOTALS: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _add_usage(meta: dict | None) -> None:
    if not meta:
        return
    TOTALS["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
    TOTALS["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
    TOTALS["total_tokens"] += int(meta.get("total_tokens", 0) or 0)



def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message, on_usage=_add_usage)

    def generate(cfg: dict) -> dict:
        brief = queryparam.collection_brief(cfg)
        return queryparam.extract_json(invoke(brief)) or {}

    summary = queryparam.run_queryparam_test(AGENT, generate, usage=lambda: TOTALS)
    print(f"[{AGENT}] accuracy={summary['query_param_handling_accuracy_pct']}% scenarios={summary['scenarios_api_correct']}/{summary['scenarios_total']} tokens={summary['tokens']['total_tokens']}")


if __name__ == "__main__":
    main()
