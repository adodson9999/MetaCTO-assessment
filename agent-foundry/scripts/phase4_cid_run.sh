#!/usr/bin/env bash
# Phase 4 — correlation-ID-propagation task: run the four agents against the local
# target, grep the captured API + downstream logs, score fidelity vs gold, update the
# leaderboard.
#
# BACKEND = OLLAMA (local/air-gapped), per config.toml [backend].provider = "ollama"
# (updated 2026-06-25 at the user's request). Ollama is natively OpenAI-compatible, so
# NO LiteLLM proxy is needed: langgraph + crewai reach it via their native Ollama paths,
# and claude_sdk + the subagent reach the same local /v1 endpoint directly. This script
# does NOT start Ollama — start it yourself (`ollama serve` + pull the model) first.
#
# Self-contained + re-runnable; each run appends to the leaderboard. DummyJSON is never
# modified — the one POST is its simulated, non-persisting create (MONGODB_URI unset),
# auth login is read-only, and the API server log is captured to a workspace file so the
# harness can grep it for the correlation id.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"

DATA_DIR="$FOUNDRY/data/validate-correlation-id-propagation"
LOG_DIR="$DATA_DIR/logs"
DOWN_DIR="$DATA_DIR/downstream-logs"
API_LOG="$LOG_DIR/api_server.log"
mkdir -p "$LOG_DIR" "$DOWN_DIR"

export FORGE_TARGET_BASE_URL="$BASE"
# Backend inherits config.toml [backend].provider ("ollama"). No FORGE_PROVIDER override.
export FORGE_API_LOG_PATH="$API_LOG"
export FORGE_DOWNSTREAM_LOG_DIR="$DOWN_DIR"     # empty: DummyJSON calls no downstream services
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 1. Ollama must already be running — this script will NOT start it.
OLLAMA_BASE="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"
OLLAMA_ROOT="${OLLAMA_BASE%/v1}"
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${OLLAMA_ROOT}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_ROOT}. Start it separately" >&2
    echo "       (\`ollama serve\` and \`ollama pull qwen2.5:14b-instruct\`); this script" >&2
    echo "       does NOT start the Ollama server for you." >&2
    exit 2
  fi
fi

# 2. Target API up with request logging ON, captured to the workspace log file.
#    LOG_ENABLED=true + NODE_ENV=production => winston JSON line per request to stdout.
#    Fresh log file each run so the grep window is exactly this run.
: > "$API_LOG"
STARTED_DJ=0
if curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "NOTE: a server is already on :$PORT — it may not be logging to $API_LOG."
  say "      For a clean capture, stop it first; this script will reuse it as-is."
else
  say "starting DummyJSON on :$PORT (request logging ON -> $API_LOG)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=production \
      PORT="$PORT" LOG_ENABLED=true node index.js >>"$API_LOG" 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 3. Refresh gold from the live API + captured logs (read-only auth + the two requests)
say "building gold (auth login + the two requests + log grep)"
BASE_URL="$BASE" python data/validate-correlation-id-propagation/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel
say "running four correlation-id-propagation agents (parallel, ollama)"
python scripts/run_cid_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-correlation-id-propagation/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-correlation-id-propagation/metric.json \
  --out-prefix results/leaderboard-validate-correlation-id-propagation

# 6. Stop only the DummyJSON target we started (Ollama is never started/stopped here)
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
