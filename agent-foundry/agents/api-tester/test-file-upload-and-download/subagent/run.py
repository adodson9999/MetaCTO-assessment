#!/usr/bin/env python3
"""Thin dispatcher: subagent runner for api-tester-test-file-upload-and-download.

Delegates all framework boilerplate to common/runners/subagent_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import upload  # noqa: E402
from upload_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

AGENT = "api-tester-test-file-upload-and-download"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-file-upload-and-download.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD)
    invoke = build_invoker(WS, system, user_message)

    def generate(cfg: dict) -> dict:
        brief = upload.endpoint_brief(cfg)
        return upload.extract_json(invoke(brief)) or {}

    summary = upload.run_upload_test(AGENT, generate)
    print(f"[{AGENT}] file_integrity_rate_pct={summary['file_integrity_rate_pct']}% over_size_rejection_rate_pct={summary['over_size_rejection_rate_pct']}% invalid_mime_rejection_rate_pct={summary['invalid_mime_rejection_rate_pct']}%")


if __name__ == "__main__":
    main()
