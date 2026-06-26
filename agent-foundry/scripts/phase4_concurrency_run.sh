#!/usr/bin/env bash
# Phase 4 — concurrent-request-handling task: run the four agents against the local
# targets, score fidelity vs gold, update the leaderboard. Self-contained.
#
# Backend = OLLAMA (qwen2.5:14b-instruct) — the Claude account had no API credit, so
# per the user this workflow runs on Ollama. Set via FORGE_PROVIDER (config.toml is
# already provider=ollama). This script does NOT start the ollama server — start it
# yourself (`ollama serve`) before running, or set FORGE_PROVIDER=claude-haiku to use
# Claude once it has credit. Override the model in config.toml [backend].ollama_model.
#
# Targets:
#   READ  = DummyJSON on :8899 (LEFT UNTOUCHED, read-only GET /products/1)
#   WRITE = local SQLite-backed endpoint on :8910 (tools/concurrency_target/app.py)
#           — exists only because DummyJSON never persists; this is where the
#           count-delta / dedup assertions are verified for real.
# Re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"

READ_PORT="${FORGE_TARGET_PORT:-8899}"
WRITE_PORT="${CONCURRENCY_TARGET_PORT:-8910}"
READ_BASE="http://localhost:${READ_PORT}"
WRITE_BASE="http://127.0.0.1:${WRITE_PORT}"
DB_PATH="$FOUNDRY/data/test-concurrent-request-handling/records.db"

export FORGE_PROVIDER="${FORGE_PROVIDER:-ollama}"   # Ollama backend (Claude had no credit)
export FORGE_READ_BASE_URL="$READ_BASE"
export FORGE_WRITE_BASE_URL="$WRITE_BASE"
export CONCURRENCY_TARGET_PORT="$WRITE_PORT"
export CONCURRENCY_DB_PATH="$DB_PATH"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

if [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is not set."; exit 3
fi

# 1. EverOS shared-memory pool up (loopback, best-effort)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2a. WRITE target up (local SQLite-backed endpoint). Only started if not already running.
STARTED_WT=0
if ! curl -fsS "$WRITE_BASE/health" >/dev/null 2>&1; then
  say "starting local SQLite write target on :$WRITE_PORT (db=$DB_PATH)"
  python tools/concurrency_target/app.py >/tmp/concurrency_target.log 2>&1 &
  WTPID=$!; STARTED_WT=1
  for i in $(seq 1 20); do curl -fsS "$WRITE_BASE/health" >/dev/null 2>&1 && break; sleep 0.5; done
fi
curl -fsS "$WRITE_BASE/health" >/dev/null 2>&1 || { echo "FATAL: write target not up"; exit 2; }

# 2b. READ target (DummyJSON) up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$READ_BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$READ_PORT (read-only target, untouched)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$READ_PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$READ_BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$READ_BASE/test" >/dev/null 2>&1 || { echo "FATAL: read target not up"; exit 2; }

# 2c. Refresh gold from the live targets so fidelity scores against current truth
say "building gold (50 concurrent GETs read-only + 50 concurrent POSTs + direct DB query)"
python data/test-concurrent-request-handling/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  ·  backend: $FORGE_PROVIDER"

# 3. Run the four in parallel
say "running four concurrency agents (parallel)"
python scripts/run_concurrency_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-1}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-concurrent-request-handling/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-concurrent-request-handling/metric.json \
  --out-prefix results/leaderboard-test-concurrent-request-handling

# 5. Stop only what we started
[ "$STARTED_WT" = "1" ] && { kill ${WTPID:-0} 2>/dev/null; sleep 1; kill -9 ${WTPID:-0} 2>/dev/null; }
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
