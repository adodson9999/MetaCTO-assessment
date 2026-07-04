#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-create-postman-collection.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import postman  # noqa: E402
from postman_prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-create-postman-collection"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-create-postman-collection.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = postman.brief(cfg)
        return postman.extract_json(invoke(brief)) or {}

    summary = postman.run_postman_test(AGENT, generate)
    print(f"[{AGENT}] postman_coverage_rate_pct={summary['postman_coverage_rate_pct']}% newman_valid={summary['newman_valid']}")


if __name__ == "__main__":
    main()
