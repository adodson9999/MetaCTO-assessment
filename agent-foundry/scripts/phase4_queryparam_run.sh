#!/usr/bin/env bash
# Phase 4 — query-parameter-handling task: run the four agents against the local
# target (READ-ONLY), score fidelity vs gold, update the leaderboard.
#
# BACKEND = OLLAMA (local, air-gapped). Set via the FORGE_PROVIDER env override so it
# is explicit, though it also matches the foundry's global config.toml default. The
# Ollama model is config.toml [backend].ollama_model (qwen2.5:14b-instruct). langgraph
# uses ChatOllama; crewai uses ollama/<model>; claude_sdk + the subagent reach it
# through the OpenAI-compatible local endpoint (Ollama /v1). No cloud calls.
#
# This script does NOT start the Ollama server — start it yourself first
# (`ollama serve`) and ensure the model is pulled. The script only checks
# reachability and exits with guidance if Ollama is not up.
#
# Self-contained + re-runnable; each run appends to the leaderboard. DummyJSON is
# never modified — agents and gold only issue read-only GETs.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
OLLAMA_URL="${FORGE_OLLAMA_URL:-http://127.0.0.1:11434}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Ollama must already be running — this script will NOT start it.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_URL}. Start it first (\`ollama serve\`)" >&2
    echo "       and pull the model (\`ollama pull qwen2.5:14b-instruct\`). Not started here." >&2
    exit 2
  fi
fi

# 1. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (read-only target)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 3. Refresh gold from the live API (read-only) so fidelity scores against current truth
say "building gold (read-only GETs)"
BASE_URL="$BASE" python data/validate-query-parameter-handling/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel
say "running four query-parameter agents (parallel, ollama)"
python scripts/run_queryparam_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity + discriminator (conformance + efficiency), build the leaderboard.
#    score.py writes the discriminator-aware leaderboard itself (lexicographic:
#    fidelity > plan-conformance > tokens > elapsed), so the generic fidelity-only
#    judge_score.py is intentionally not called for this task.
say "scoring fidelity + discriminator (conformance, tokens, elapsed)"
python judge/validate-query-parameter-handling/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 6. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
