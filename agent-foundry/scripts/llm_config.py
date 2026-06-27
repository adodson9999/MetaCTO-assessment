#!/usr/bin/env python3
"""
Forge LLM Config — single source of truth for provider resolution.

Priority (highest → lowest):
  1. FORGE_PROVIDER env var (explicit override, useful for CI or one-off runs)
  2. config.toml [backend].provider (if not "auto")
  3. Auto-detect: CLAUDE_CODE_ENTRYPOINT is set → claude-haiku
                  otherwise                     → ollama

Usage:
    python scripts/llm_config.py          # prints JSON to stdout
    python scripts/llm_config.py --export # prints eval-able bash exports
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

try:
    import tomllib          # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib   # pip install tomli
    except ImportError:
        sys.exit("llm_config.py requires tomllib (Python 3.11+) or tomli (pip install tomli)")

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = FOUNDRY_ROOT / "config.toml"


def _is_claude_code_session() -> bool:
    """
    Return True when this process is running inside a Claude Code agent session.

    Claude Code sets CLAUDE_CODE_ENTRYPOINT automatically when it spawns any
    agent subprocess (cli, vscode, sub-agent, etc.). That is the canonical signal.
    ANTHROPIC_API_KEY is a secondary check for cases where the key is present
    but the entrypoint var is not (e.g. raw `claude -p` invocations).
    """
    return bool(os.environ.get("CLAUDE_CODE_ENTRYPOINT")) or bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )


def resolve() -> dict:
    """
    Resolve the active LLM backend.

    Returns a dict with keys: provider, model, base_url, api_key_env
    """
    cfg = tomllib.loads(CONFIG_PATH.read_text())
    backend = cfg.get("backend", {})

    # Priority 1: explicit env override
    provider = os.environ.get("FORGE_PROVIDER", "").strip()

    # Priority 2: config.toml
    if not provider:
        provider = backend.get("provider", "auto")

    # Priority 3: auto-detect
    if provider == "auto":
        provider = "claude-haiku" if _is_claude_code_session() else "ollama"

    if provider == "ollama":
        return {
            "provider": "ollama",
            "model": backend.get("ollama_model", "qwen2.5:14b-instruct"),
            "base_url": backend.get("ollama_base_url", "http://127.0.0.1:11434/v1"),
            "api_key_env": None,
        }

    if provider in ("claude-haiku", "claude"):
        return {
            "provider": "claude-haiku",
            "model": backend.get("claude_model", "claude-haiku-4-5"),
            "base_url": backend.get("litellm_proxy_url", "http://127.0.0.1:4000/v1"),
            "api_key_env": "ANTHROPIC_API_KEY",
        }

    raise ValueError(
        f"Unknown provider {provider!r}. Valid values: ollama, claude-haiku, auto"
    )


def _bash_exports(cfg: dict) -> str:
    lines = [
        f'export FORGE_PROVIDER="{cfg["provider"]}"',
        f'export FORGE_MODEL="{cfg["model"]}"',
        f'export FORGE_BASE_URL="{cfg["base_url"]}"',
    ]
    if cfg["api_key_env"]:
        lines.append(f'# FORGE_API_KEY_ENV="{cfg["api_key_env"]}"')
    return "\n".join(lines)


if __name__ == "__main__":
    cfg = resolve()
    if "--export" in sys.argv:
        print(_bash_exports(cfg))
    else:
        print(json.dumps(cfg, indent=2))
