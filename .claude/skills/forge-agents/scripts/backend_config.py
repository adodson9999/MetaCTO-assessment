#!/usr/bin/env python3
"""
Central backend switch for every component (agents, judge, debaters, evolvers).

One provider toggle drives the whole foundry. Three first-class providers:

    - "auto"          : detect at runtime — Claude Haiku when CLAUDE_CODE_ENTRYPOINT
                        is set (running inside a Claude Code session), else Ollama.
                        This is the DEFAULT. Set provider = "auto" in config.toml.
    - "ollama"        : force local, OpenAI-compatible at http://127.0.0.1:11434/v1
    - "claude-haiku"  : force Anthropic claude-haiku-4-5 (via LiteLLM proxy)

Detection signal: CLAUDE_CODE_ENTRYPOINT is set automatically by Claude Code on
every agent subprocess it spawns. It is the canonical "am I inside Claude Code?"
signal. Never hardcode a provider — always use "auto" and let this module decide.

stdlib only. Reads config.toml if present (Py3.11+ tomllib), else env vars,
else sane local defaults.
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    tomllib = None

DEFAULTS = {
    "provider": "auto",          # "auto" is the correct default; never "ollama"
    "ollama_base_url": "http://127.0.0.1:11434/v1",
    "ollama_model": "qwen2.5:14b-instruct",
    "claude_model": "claude-haiku-4-5",
    "litellm_proxy_url": "http://127.0.0.1:4000/v1",
}


def _is_claude_code_session() -> bool:
    """Return True when running inside a Claude Code agent session.

    CLAUDE_CODE_ENTRYPOINT is set automatically by Claude Code on every
    agent subprocess it spawns. That is the canonical detection signal.
    ANTHROPIC_API_KEY is a secondary check for raw `claude -p` invocations.
    """
    return bool(os.environ.get("CLAUDE_CODE_ENTRYPOINT")) or bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )


def _load_config(workspace: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    path = (workspace or Path(".")) / "config.toml"
    if tomllib and path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        cfg.update(data.get("backend", {}))
    # FORGE_PROVIDER env var wins over config.toml (explicit override for CI/one-offs)
    env_provider = os.environ.get("FORGE_PROVIDER", "").strip()
    if env_provider:
        cfg["provider"] = env_provider
    for k in list(cfg.keys()):
        if k == "provider":
            continue
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env
    return cfg


def resolve(workspace: Path | None = None) -> dict:
    """Return a uniform connection spec all components can consume.

    Priority (highest to lowest):
      1. FORGE_PROVIDER env var
      2. config.toml [backend].provider  (should be "auto")
      3. Auto-detect: CLAUDE_CODE_ENTRYPOINT set -> claude-haiku, else -> ollama
    """
    cfg = _load_config(workspace)
    provider = cfg["provider"]

    if provider == "auto":
        provider = "claude-haiku" if _is_claude_code_session() else "ollama"

    if provider == "ollama":
        return {
            "provider": "ollama",
            "openai_compatible": True,
            "base_url": cfg["ollama_base_url"],
            "model": cfg["ollama_model"],
            "api_key_env": "OLLAMA_API_KEY",
            "native": {"kind": "ollama", "model": cfg["ollama_model"]},
            "air_gapped": True,
        }

    if provider in ("claude-haiku", "claude"):
        return {
            "provider": "claude-haiku",
            "openai_compatible": True,
            "base_url": cfg["litellm_proxy_url"],
            "model": cfg["claude_model"],
            "api_key_env": "ANTHROPIC_API_KEY",
            "native": {"kind": "anthropic", "model": cfg["claude_model"]},
            "air_gapped": False,
        }

    raise ValueError(
        f"Unknown backend provider {provider!r}. "
        f"Valid values: auto, ollama, claude-haiku"
    )


if __name__ == "__main__":
    import json
    print(json.dumps(resolve(), indent=2))
