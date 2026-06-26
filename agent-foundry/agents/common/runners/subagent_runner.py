"""Shared Claude Code subagent runner.

Drives elicitation via the ``claude`` CLI when available (Anthropic backend),
otherwise falls back to the local OpenAI-compatible endpoint (Ollama /v1).

Thin dispatchers call::

    from runners.subagent_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw model output)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by the Claude Code subagent.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
    """
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415

    spec = backend_config.resolve(ws)

    def _via_claude_cli(brief: str) -> str | None:
        if spec["native"]["kind"] != "anthropic" or not shutil.which("claude"):
            return None
        try:
            proc = subprocess.run(
                [
                    "claude",
                    "-p",
                    f"{system}\n\n{user_message_fn(brief)}",
                    "--output-format",
                    "text",
                ],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=180,
            )
            return proc.stdout if proc.returncode == 0 else None
        except Exception:  # noqa: BLE001
            return None

    def _via_local(brief: str) -> str:
        body = json.dumps(
            {
                "model": spec["model"],
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message_fn(brief)},
                ],
                "stream": False,
                "response_format": {"type": "json_object"},
            }
        ).encode()
        req = urllib.request.Request(
            spec["base_url"] + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]

    def invoke(brief: str) -> str:
        return _via_claude_cli(brief) or _via_local(brief)

    return invoke
