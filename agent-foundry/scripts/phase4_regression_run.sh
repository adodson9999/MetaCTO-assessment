#!/usr/bin/env bash
# Phase 4 — Run-Regression-Suite task: confirm the build-N deployment is healthy
# (read-only GET /health == 200 against the local target), run the four agents against
# the local build-pair fixtures, score Regression-Report Fidelity vs the deterministic
# gold, update the leaderboard.
#
# BACKEND = OLLAMA (local / air-gapped). Set via the FORGE_PROVIDER env override so the
# run is explicit regardless of the foundry's global config.toml. All four agents reach
# Ollama through its native OpenAI-compatible /v1 endpoint: langgraph (langchain
# ChatOllama), crewai (LiteLLM "ollama/" string), and both claude_sdk + the subagent via
# the OpenAI-compatible local endpoint. No LiteLLM proxy and no Anthropic key needed.
#
# This script does NOT start the Ollama server — Ollama must already be running locally
# (start it yourself with `ollama serve`). If it is unreachable the run exits with a
# clear message rather than launching anything.
#
# Self-contained + re-runnable; each run appends to the leaderboard. DummyJSON is never
# modified — the only call to it is a read-only GET /health (the deployment confirmation).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
OLLAMA_URL="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 1. Ollama must already be running (we do NOT start it). Read-only reachability check.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    say "Ollama reachable at ${OLLAMA_URL} (local, air-gapped)"
  else
    echo "FATAL: Ollama is not reachable at ${OLLAMA_URL}. Start it yourself with" >&2
    echo "       'ollama serve' (this script does not start the server), then re-run." >&2
    exit 2
  fi
fi

# 2. Target API up (the "deployed build N" test environment). Read-only /health gate.
#    Air-gapped: no Mongo. Only started if not already running. DummyJSON UNMODIFIED.
STARTED_DJ=0
if ! curl -fsS "$BASE/health" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (read-only target; the deployed build N)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/health" >/dev/null 2>&1 && break; sleep 1; done
fi
HCODE="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null || echo 000)"
say "deployment health: GET /health -> $HCODE"
[ "$HCODE" = "200" ] || { echo "FATAL: build N /health != 200 (got $HCODE)"; exit 2; }

# 3. Build the deterministic gold (parses the local fixtures; also records /health)
say "building gold (deterministic, from local build-pair fixtures)"
BASE_URL="$BASE" python data/run-regression-suite/build_gold.py >/dev/null

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel
say "running four regression-suite agents (parallel, ollama)"
python scripts/run_regression_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity (+ discriminators) vs gold, then build the leaderboard
say "scoring fidelity + discriminators"
python judge/run-regression-suite/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 6. Stop only what we started (the local target; Ollama is left running — we did not start it)
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
