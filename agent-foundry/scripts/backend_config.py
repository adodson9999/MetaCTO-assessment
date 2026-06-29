#!/usr/bin/env python3
# Used by: shared infra — LLM backend resolution for EVERY phase4_* agent workflow + runners.
"""
Central backend switch for every component (agents, judge, debaters, evolvers).

One provider toggle drives the whole foundry. Swapping models is a one-line
change in config.toml ([backend].provider). Providers:

    - "ollama"        : local, OpenAI-compatible at http://127.0.0.1:11434/v1
    - "claude-haiku"  : Anthropic claude-haiku-4-5 (OpenAI path via LiteLLM proxy)
    - "claude-cli"    : Anthropic via the `claude -p` CLI shim (no API credits)
    - "auto"          : pick the first REACHABLE backend (see _auto_detect) —
                        prefers Claude inside a Claude Code session, always
                        falls back to local Ollama; never selects a backend
                        whose shim/proxy isn't actually listening.

Components that only speak the OpenAI protocol (SkillClaw, EverOS's OpenAI path)
reach Claude through a local LiteLLM proxy, so Claude stays interchangeable
everywhere. Ollama is natively OpenAI-compatible and needs no shim.

stdlib only. Reads config.toml if present (Py3.11+ tomllib), else env vars,
else sane local defaults.
"""
from __future__ import annotations
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

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
    # env overrides win (handy for quick experiments / CI)
    for k in cfg:
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env
    return cfg


def _is_claude_code_session() -> bool:
    """True when an Anthropic-backed Claude path is plausibly available: the
    ``claude`` CLI is on PATH AND ANTHROPIC_API_KEY is set. Used only to ORDER
    'auto' detection — never to force an unreachable backend (reachability is
    still probed before any provider is chosen)."""
    import shutil
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and shutil.which("claude") is not None


def _openai_base_for(provider: str, cfg: dict) -> str | None:
    """The OpenAI-compatible endpoint a runner actually dials for each provider.
    This is the right thing to probe for liveness because every framework runner
    reaches the backend through this path (claude-haiku => the LiteLLM proxy,
    claude-cli => the `claude -p` shim, ollama => ollama itself)."""
    return {
        "ollama": cfg["ollama_base_url"],
        "claude-haiku": cfg["litellm_proxy_url"],
        "claude-cli": cfg["claude_cli_shim_url"],
    }.get(provider)


def _reachable(base_url: str, timeout: float = 0.4) -> bool:
    """Cheap TCP liveness probe of an endpoint's host:port — no HTTP, no deps.
    Confirms something is listening so 'auto' never selects a backend whose
    server isn't running (e.g. claude-haiku when the LiteLLM proxy is down)."""
    try:
        u = urlparse(base_url)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _auto_detect(cfg: dict) -> str:
    """Resolve provider='auto' to the first REACHABLE concrete backend.

    Preference order favors Claude inside a Claude Code session and always falls
    back to local Ollama. Each candidate's OpenAI-compatible endpoint is probed
    first, so 'auto' degrades gracefully: it picks a running Claude shim/proxy
    when one is up, otherwise local Ollama, and finally Ollama as the air-gapped
    default (which surfaces a clear connect error if it too is down)."""
    order = (["claude-cli", "claude-haiku", "ollama"]
             if _is_claude_code_session() else ["ollama"])
    for prov in order:
        base = _openai_base_for(prov, cfg)
        if base and _reachable(base):
            return prov
    return "ollama"


def resolve(workspace: Path | None = None) -> dict:
    """Return a uniform connection spec all components can consume.

    Always exposes an OpenAI-compatible (base_url, model, api_key_env) tuple,
    plus the native flavor when relevant, so each component can pick the path
    it supports without any component hardcoding a model.
    """
    cfg = _load_config(workspace)
    provider = cfg["provider"]
    if provider == "auto":
        provider = _auto_detect(cfg)

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
        f"Use 'ollama', 'claude-haiku', 'claude-cli', or 'auto' in config.toml [backend].provider."
    )


if __name__ == "__main__":
    import json
    # use FORGE_WORKSPACE so the diagnostic reads the foundry's config.toml (provider="auto"),
    # not a missing project-root one (which would wrongly default to ollama).
    _ws = os.environ.get("FORGE_WORKSPACE")
    print(json.dumps(resolve(Path(_ws) if _ws else None), indent=2))
