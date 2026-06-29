#!/usr/bin/env bash
# Phase 4 — test-bulk-operation-endpoints task: stand up the local spec-conformant
# bulk target, refresh gold, run the four agents, score fidelity vs gold, update the
# leaderboard.
#
# BACKEND = OLLAMA (air-gapped, local). Switched from claude-haiku to ollama per the
# user's instruction "update the llm to Ollama". Set via the FORGE_PROVIDER env override
# so the choice is explicit for this run. All four agents reach the local Ollama
# OpenAI-compatible endpoint (langgraph via ChatOllama, crewai via ollama/<model>,
# claude_sdk + the subagent via the OpenAI-compatible /chat/completions path).
#
# NOTE: this script does NOT start the Ollama server — start it yourself first
# (`ollama serve`, model "qwen2.5:14b-instruct" pulled) or the elicitation step fails.
#
# DummyJSON is NEVER started, contacted, or modified: it exposes no bulk endpoints, so
# the entire bulk test runs against the separate, local, air-gapped bulk target
# (tools/bulk_target/app.py). Self-contained + re-runnable; each run appends to the
# leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BULK_TARGET_PORT:-8924}"
BASE="http://127.0.0.1:${PORT}"
export FORGE_BULK_BASE_URL="$BASE"
export BULK_TARGET_PORT="$PORT"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Claude backend needs an API key; Ollama needs a running local server. Guard each.
if [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: ANTHROPIC_API_KEY is not set; the Claude backend cannot run." >&2
  exit 2
fi
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  OLLAMA_BASE="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
  if ! curl -fsS "${OLLAMA_BASE%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama server not reachable at ${OLLAMA_BASE%/v1}. This script does" >&2
    echo "       not start it — run 'ollama serve' (and pull the model) first." >&2
    exit 2
  fi
fi

# 1. Local bulk target up (air-gapped, loopback). Only started if not already running.
STARTED_TGT=0
if ! curl -fsS "$BASE/health" >/dev/null 2>&1; then
  say "starting local bulk target on :$PORT"
  ( BULK_TARGET_PORT="$PORT" python tools/bulk_target/app.py >/tmp/bulk_target.log 2>&1 ) &
  TGTPID=$!; STARTED_TGT=1
  for i in $(seq 1 20); do curl -fsS "$BASE/health" >/dev/null 2>&1 && break; sleep 0.5; done
fi
curl -fsS "$BASE/health" >/dev/null 2>&1 || { echo "FATAL: bulk target not up"; exit 2; }

# 2. Refresh gold from the live target so fidelity scores against current truth
say "building gold (local bulk target)"
FORGE_BULK_BASE_URL="$BASE" python data/test-bulk-operation-endpoints/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four bulk-operation agents (parallel, $FORGE_PROVIDER)"
python scripts/run_bulk_agents__test-bulk-operation-endpoints.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-bulk-operation-endpoints/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-bulk-operation-endpoints/metric.json \
  --out-prefix results/leaderboard-test-bulk-operation-endpoints

# 5. Stop only what we started
[ "$STARTED_TGT" = "1" ] && { kill ${TGTPID:-0} 2>/dev/null; sleep 1; kill -9 ${TGTPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
