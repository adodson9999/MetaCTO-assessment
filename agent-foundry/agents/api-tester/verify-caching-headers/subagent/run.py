#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-verify-caching-headers.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import caching  # noqa: E402
from caching_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-verify-caching-headers"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-verify-caching-headers.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = caching.collection_brief(cfg)
        return caching.extract_json(invoke(brief)) or {}

    summary = caching.run_caching_test(AGENT, generate)
    print(f"[{AGENT}] caching_header_compliance_rate_pct={summary['caching_header_compliance_rate_pct']}% caching_correctness_rate_pct={summary['caching_correctness_rate_pct']}%")


if __name__ == "__main__":
    main()
