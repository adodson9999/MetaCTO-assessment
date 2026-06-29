#!/usr/bin/env bash
# Forge Agents — one-command setup (macOS / Linux).
# Idempotent. Stands up the local, air-gapped stack. Cloud (Claude Haiku) is opt-in.
set -euo pipefail

say() { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# 1. Python + uv
say "Checking Python (3.11+ recommended) and uv"
command -v python3 >/dev/null || { warn "python3 not found"; exit 1; }
if ! command -v uv >/dev/null; then
  warn "uv not found — installing (https://docs.astral.sh/uv/)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. Python deps for the foundry helpers
say "Installing foundry Python deps"
uv venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install --quiet \
  langgraph langchain langchain-community langchain-anthropic \
  crewai litellm \
  claude-agent-sdk \
  sentence-transformers \
  pyyaml || warn "some optional deps failed; core foundry still works"

# 3. Local model backend (Ollama) — only nudge, never force
if command -v ollama >/dev/null; then
  say "Ollama present — pulling default local model (skip with CTRL-C)"
  ollama pull qwen2.5:14b-instruct || warn "model pull skipped"
else
  warn "Ollama not found. Install from https://ollama.com to run fully air-gapped."
  warn "Or set [backend].provider = \"claude-haiku\" in config.toml (cloud, opt-in)."
fi

# 4. LiteLLM proxy note (universal OpenAI-compat shim for Claude path)
say "If using claude-haiku for SkillClaw/EverOS OpenAI paths, run a LiteLLM proxy:"
echo "    litellm --model claude-haiku-4-5 --port 4000"

# 5. EverOS local memory server (after /scan-and-integrate vendors it)
if [ -d vendor/EverOS ]; then
  say "EverOS vendored — initialize + start it bound to 127.0.0.1"
  echo "    (cd vendor/EverOS && uv sync && everos init && everos server start)"
else
  warn "EverOS not vendored yet — run /scan-and-integrate first."
fi

say "Setup complete. Next: /scan-and-integrate, then /forge-agents."
