#!/usr/bin/env python3
"""Thin dispatcher: crewai runner for code-review-memory-resource.

Delegates all framework boilerplate to common/runners/crewai_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import memresource  # noqa: E402
from memresource_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.crewai_runner import build_invoker  # noqa: E402

AGENT = "crewai"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "code-review-memory-resource.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return memresource.extract_json(invoke(brief)) or {}

    s = memresource.run_memresource_test(AGENT, generate)
    print(f"[{AGENT}] rating_band_accuracy={s['rating_band_accuracy']}"
          f" cases={s['cases_total']}"
          f" schema_pass={s['schema_pass_pct']}% band_pass={s['band_pass_pct']}%")


if __name__ == "__main__":
    main()
