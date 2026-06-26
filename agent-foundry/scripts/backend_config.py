#!/usr/bin/env python3
"""
Central backend switch for every component (agents, judge, debaters, evolvers).

One provider toggle drives the whole foundry. Swapping models is a one-line
change in config.toml ([backend].provider). Two first-class providers:

    - "ollama"        : local, OpenAI-compatible at http://127.0.0.1:11434/v1
    - "claude-haiku"  : Anthropic claude-haiku-4-5

Components that only speak the OpenAI protocol (SkillClaw, EverOS's OpenAI path)
reach Claude through a local LiteLLM proxy, so Claude stays interchangeable
everywhere. Ollama is natively OpenAI-compatible and needs no shim.

stdlib only. Reads config.toml if present (Py3.11+ tomllib), else env vars,
else sane local defaults.
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

DEFAULTS = {
    "provider": "ollama",
    "ollama_base_url": "http://127.0.0.1:11434/v1",
    "ollama_model": "qwen2.5:14b-instruct",
    "claude_model": "claude-haiku-4-5",
    "litellm_proxy_url": "http://127.0.0.1:4000/v1",  # universal OpenAI-compat shim
    "claude_cli_shim_url": "http://127.0.0.1:8787/v1",  # OpenAI-compat shim over `claude -p`
}


def _load_config(workspace: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    path = (workspace or Path(".")) / "config.toml"
    if tomllib and path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        cfg.update(data.get("backend", {}))
    # env overrides win (handy for quick experiments)
    for k in cfg:
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env
    return cfg


def resolve(workspace: Path | None = None) -> dict:
    """Return a uniform connection spec all components can consume.

    Always exposes an OpenAI-compatible (base_url, model, api_key_env) tuple,
    plus the native flavor when relevant, so each component can pick the path
    it supports without any component hardcoding a model.
    """
    cfg = _load_config(workspace)
    provider = cfg["provider"]

    if provider == "ollama":
        return {
            "provider": "ollama",
            "openai_compatible": True,
            "base_url": cfg["ollama_base_url"],
            "model": cfg["ollama_model"],
            "api_key_env": "OLLAMA_API_KEY",  # ollama ignores it; placeholder ok
            "native": {"kind": "ollama", "model": cfg["ollama_model"]},
            "air_gapped": True,
        }

    if provider == "claude-haiku":
        return {
            "provider": "claude-haiku",
            # OpenAI-compatible path = via the local LiteLLM proxy (for SkillClaw/EverOS)
            "openai_compatible": True,
            "base_url": cfg["litellm_proxy_url"],
            "model": cfg["claude_model"],
            "api_key_env": "ANTHROPIC_API_KEY",
            # native path = direct Anthropic (for LangGraph/CrewAI/SkillOpt/SDK)
            "native": {"kind": "anthropic", "model": cfg["claude_model"]},
            "air_gapped": False,  # cloud backend; opt-in only
        }

    if provider == "claude-cli":
        # Claude via the claude.ai subscription, exposed behind an OpenAI-compatible
        # shim over `claude -p` (scripts/claude_cli_shim.py). Used when ANTHROPIC_API_KEY
        # has no credits but the subscription works. Every framework reaches it through
        # its OpenAI-compatible code path. Native kind "openai-cli" tells the runners to
        # use the OpenAI client / a direct `claude -p` call rather than the SDK paths.
        return {
            "provider": "claude-cli",
            "openai_compatible": True,
            "base_url": cfg["claude_cli_shim_url"],
            "model": cfg["claude_model"],
            "api_key_env": "FORGE_SHIM_KEY",   # any non-empty string; the shim ignores it
            "native": {"kind": "openai-cli", "model": cfg["claude_model"]},
            "air_gapped": False,
        }

    raise ValueError(
        f"Unknown backend provider {provider!r}. "
        f"Use 'ollama', 'claude-haiku', or 'claude-cli' in config.toml [backend].provider."
    )


if __name__ == "__main__":
    import json
    print(json.dumps(resolve(), indent=2))
