#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for general-documentation-reviewer.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import docreview  # noqa: E402
from docreview_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "general-documentation-reviewer.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return docreview.extract_json(invoke(brief)) or {}

    s = docreview.run_docreview_test(AGENT, generate)
    print(f"[{AGENT}] verdict_accuracy={s['verdict_accuracy_pct']}%"
          f" reports={s['verdicts_total']}"
          f" source_of_truth_match={s['source_of_truth_match_pct']}%")


if __name__ == "__main__":
    main()
