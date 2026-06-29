#!/usr/bin/env bash
# Phase 4 — validate-header-propagation: run the four agents against the local target,
# score fidelity vs gold, update the leaderboard. Self-contained + air-gapped.
# Re-runnable; each run appends to the leaderboard. DummyJSON is never modified.
#
# Backend: Ollama (FORGE_PROVIDER=ollama), local + air-gapped. This script does NOT
# start the Ollama server — bring it up yourself (`ollama serve`) before running.
# The "API server log" the harness greps = DummyJSON's own winston Console output,
# captured to $SERVER_LOG (LOG_ENABLED=true, NODE_ENV=production JSON format).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
SERVER_LOG="${FORGE_SERVER_LOG:-/tmp/forge-hp-dummyjson-${PORT}.log}"
export FORGE_TARGET_BASE_URL="$BASE"
export FORGE_SERVER_LOG="$SERVER_LOG"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend reachability NOTE — never starts the server (per build policy).
#    For Ollama, ensure it is already running (`ollama serve`). For claude-haiku,
#    ensure ANTHROPIC_API_KEY is set. This is a warning only; it does not exit.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
    || say "WARN: Ollama not reachable at 127.0.0.1:11434 — start it yourself ('ollama serve'); this script will NOT start it."
elif [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  say "WARN: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is unset."
fi

# 1. EverOS shared-memory pool up (loopback)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up with request logging captured to $SERVER_LOG (the grep-able API log).
#    Always start a FRESH instance so the captured log is clean for this run.
say "starting DummyJSON on :$PORT with request logging -> $SERVER_LOG"
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1
: > "$SERVER_LOG"
( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=production \
    PORT="$PORT" LOG_ENABLED=true node index.js >"$SERVER_LOG" 2>&1 ) &
DJPID=$!; STARTED_DJ=1
for i in $(seq 1 30); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth.
say "building gold (live target + captured server log)"
python data/validate-header-propagation/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel (Claude backend; cloud handles concurrency)
say "running four header-propagation agents (parallel, Claude backend)"
python scripts/run_header_agents__validate-header-propagation.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-header-propagation/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-header-propagation/metric.json \
  --out-prefix results/leaderboard-validate-header-propagation

# 5. Stop only what we started
[ "${STARTED_DJ:-0}" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
