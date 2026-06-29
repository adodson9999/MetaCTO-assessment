#!/usr/bin/env bash
# Bring up the Claude Code session backend for the foundry: start the claude -p shim on
# :8787 so provider="auto" resolves to claude-cli (your subscription, no API credits).
# Ollama stays the fallback. Idempotent: no-op if the shim is already up.
#
# Usage:  agent-foundry/scripts/use-claude-session.sh [--model sonnet|opus|haiku|claude-haiku-4-5] [--port 8787]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS="$ROOT/agent-foundry"
PY="$WS/.venv/bin/python"
MODEL="sonnet"
PORT="8787"
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --port)  PORT="$2";  shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found — not in a Claude Code session; use Ollama (FORGE_PROVIDER=ollama)." >&2
  exit 1
fi

if curl -s -o /dev/null "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null; then
  echo "claude-cli shim already listening on :${PORT}"
else
  echo "starting claude-cli shim (model=${MODEL}) on :${PORT} ..."
  nohup "$PY" "$WS/scripts/claude_cli_shim.py" --port "$PORT" --model "$MODEL" \
    > "/tmp/claude_shim_${PORT}.log" 2>&1 &
  echo "$!" > "/tmp/claude_shim_${PORT}.pid"
  for i in 1 2 3 4 5 6 7 8; do
    sleep 1
    curl -s -o /dev/null "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null && break
  done
fi

if curl -s -o /dev/null "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null; then
  echo "shim OK on :${PORT}"
else
  echo "ERROR: shim did not come up — see /tmp/claude_shim_${PORT}.log" >&2
  exit 1
fi

echo "--- provider='auto' now resolves to: ---"
FORGE_WORKSPACE="$WS" "$PY" "$WS/scripts/backend_config.py" 2>/dev/null | grep -E '"provider"|"base_url"|"model"' || true
echo "Run drivers with provider=auto (picks claude-cli) or FORGE_PROVIDER=claude-cli."
