#!/usr/bin/env bash
# Phase 4 — versioning-behavior task: run the four agents against the local target
# (READ-ONLY), score fidelity vs gold, update the leaderboard.
#
# BACKEND = OLLAMA (air-gapped, local) per the updated build request. Set via the
# FORGE_PROVIDER env override; the foundry's global config.toml is left untouched.
# langgraph reaches Ollama via ChatOllama, crewai via the "ollama/<model>" LiteLLM
# string, and claude_sdk + the subagent POST the local Ollama /v1 OpenAI-compatible
# endpoint — no Anthropic key, no LiteLLM proxy, nothing leaves the machine.
#
# This script does NOT start the Ollama server; it only checks reachability and exits
# with guidance if Ollama is not already running on 127.0.0.1:11434.
#
# DummyJSON is NEVER modified — agents and gold only issue read-only GETs. DummyJSON
# ships no API versioning, so every /vN URL 404s; that is the recorded QA finding, not
# a harness fault. Self-contained + re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"
OLLAMA_HOST="${FORGE_OLLAMA_HOST:-http://127.0.0.1:11434}"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Reachability gate only — this script never STARTS Ollama. Start it yourself first
# (e.g. `ollama serve` and `ollama pull qwen2.5:14b-instruct`) if this check fails.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_HOST}. Start it first (this script does not)." >&2
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

# 2. Refresh gold from the live API (read-only) so fidelity scores against current truth
say "building gold (read-only GETs + ajv v8 validation)"
BASE_URL="$BASE" python data/validate-api-versioning-behavior/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four versioning agents (parallel, ollama)"
python scripts/run_versioning_agents__validate-api-versioning-behavior.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity + discriminator (conformance + efficiency), build the leaderboard.
#    score.py writes the discriminator-aware leaderboard itself (lexicographic:
#    fidelity > plan-conformance > tokens > elapsed), so the generic fidelity-only
#    judge_score.py is intentionally not called for this task.
say "scoring fidelity + discriminator (conformance, tokens, elapsed)"
python judge/validate-api-versioning-behavior/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
