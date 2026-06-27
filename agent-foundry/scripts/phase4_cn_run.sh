#!/usr/bin/env bash
# Phase 4 — content-type-negotiation task: run the four agents against the local
# target, score fidelity vs gold, update the leaderboard.
#
# Backend: CLAUDE (claude-haiku) per the user's instruction — Ollama is NOT used or
# started for this task. Requires ANTHROPIC_API_KEY in the environment (or the
# `claude` CLI for the subagent). Re-runnable; each run appends to the leaderboard.
# DummyJSON is never modified — accept probes are read-only GETs; consumes probes use
# its non-persistent simulated write routes.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
SHIM_PORT="${FORGE_SHIM_PORT:-8787}"
export FORGE_TARGET_BASE_URL="$BASE"
# Backend = the central config default (config.toml -> ollama, local/air-gapped).
# Switched off Claude after the ANTHROPIC_API_KEY credit balance was exhausted; the
# four agents now elicit plans from the local Ollama endpoint. This script NEVER starts
# a model server — start Ollama yourself (`ollama serve`) before running.
# Optional: FORGE_PROVIDER=claude-cli (subscription shim) or claude-haiku (funded key).
export FORGE_CLAUDE_CLI_SHIM_URL="http://127.0.0.1:${SHIM_PORT}/v1"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Backend reachability. We do NOT start any model server here.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || {
    echo "FATAL: ollama backend selected but the Ollama server is not running on :11434."
    echo "       Start it yourself: 'ollama serve' (this script does not start it)."; exit 3; }
elif [ "$FORGE_PROVIDER" = "claude-cli" ]; then
  command -v claude >/dev/null 2>&1 || { echo "FATAL: claude CLI not on PATH"; exit 3; }
fi

# 0. Claude-CLI shim up (only for the claude-cli provider; skipped under ollama).
STARTED_SHIM=0
if [ "$FORGE_PROVIDER" = "claude-cli" ]; then
  if ! curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1; then
    say "starting claude-cli shim on 127.0.0.1:${SHIM_PORT} (wraps \`claude -p\` subscription)"
    ( python scripts/claude_cli_shim.py --port "$SHIM_PORT" --model claude-haiku-4-5 \
        >/tmp/claude_shim.log 2>&1 ) &
    SHIMPID=$!; STARTED_SHIM=1
    for i in $(seq 1 20); do curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1 && break; sleep 1; done
  fi
  curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1 || { echo "FATAL: shim not up"; exit 4; }
fi

# 1. EverOS shared-memory pool up (loopback). Best-effort; the harness degrades gracefully.
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (target)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth.
say "building gold"
BASE_URL="$BASE" python data/verify-content-type-negotiation/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend: $FORGE_PROVIDER)"

# 3. Run the four agents. Default concurrency 1: the target rate-limits 100 req/10s
#    per IP, and four agents sharing localhost would contend and trip 429s that have
#    nothing to do with content negotiation. Each agent alone, paced + 429-backed-off
#    by the harness, stays under the limit. Override with FORGE_CONCURRENCY if the
#    target's limiter is disabled.
say "running four content-type-negotiation agents (sequential, claude backend)"
python scripts/run_cn_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "${FORGE_CONCURRENCY:-1}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/verify-content-type-negotiation/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/verify-content-type-negotiation/metric.json \
  --out-prefix results/leaderboard-verify-content-type-negotiation

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
[ "$STARTED_SHIM" = "1" ] && { kill ${SHIMPID:-0} 2>/dev/null; sleep 1; kill -9 ${SHIMPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
