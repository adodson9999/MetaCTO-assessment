"""Shared Claude Agent SDK runner.

Native Claude SDK when the backend is Anthropic; falls back to the local
OpenAI-compatible endpoint (Ollama /v1) when air-gapped.

Thin dispatchers call::

    from runners.claude_sdk_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw model output)
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from typing import Callable


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by the Claude Agent SDK.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
    """
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415

    spec = backend_config.resolve(ws)

    async def _native(brief: str) -> str:
        from claude_agent_sdk import query, ClaudeAgentOptions  # type: ignore[import]

        opts = ClaudeAgentOptions(
            system_prompt=system,
            model=spec["native"]["model"],
        )
        chunks: list[str] = []
        async for msg in query(prompt=user_message_fn(brief), options=opts):
            chunks.append(getattr(msg, "content", str(msg)))
        return "".join(map(str, chunks))

    def _openai_compat(brief: str) -> str:
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
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]

    def invoke(brief: str) -> str:
        if spec["native"]["kind"] == "anthropic":
            try:
                return asyncio.run(_native(brief))
            except Exception:  # noqa: BLE001 — cloud path unavailable air-gapped
                pass
        return _openai_compat(brief)

    return invoke
