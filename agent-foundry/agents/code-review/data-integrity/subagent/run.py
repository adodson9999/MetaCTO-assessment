#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for code-review-data-integrity.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import dataintegrity  # noqa: E402
from dataintegrity_prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "code-review-data-integrity"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "code-review-data-integrity.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(brief: str) -> dict:
        return dataintegrity.extract_json(invoke(brief)) or {}

    s = dataintegrity.run_dataintegrity_test(AGENT, generate)
    print(f"[{AGENT}] rating_band_accuracy={s['rating_band_accuracy']}"
          f" cases={s['cases_total']}"
          f" schema_valid={s['schema_valid_pct']}%")


if __name__ == "__main__":
    main()
