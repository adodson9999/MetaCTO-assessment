#!/usr/bin/env bash
# Phase 4 (CRUD task) — run the four CRUD-integrity-testing agents against the local
# target, score fidelity vs gold, update the leaderboard. Self-contained.
# Re-runnable; each run appends to the leaderboard.
#
# Backend: this workflow runs on OLLAMA (local, air-gapped) by default. Set
# build-scoped via FORGE_PROVIDER so the foundry-wide config.toml default is untouched.
# This script does NOT start the Ollama server — it must already be running (start it
# yourself with `ollama serve`). Override with FORGE_PROVIDER=claude-haiku to run on
# Claude instead (needs ANTHROPIC_API_KEY exported).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend preflight: Claude needs a key; Ollama needs the daemon ALREADY running
#    (this script never starts it, per the build's "do not start the server" rule).
if [ "$FORGE_PROVIDER" = "claude-haiku" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "FATAL: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is not set." >&2
    echo "       export ANTHROPIC_API_KEY=... (or run with FORGE_PROVIDER=ollama)." >&2
    exit 3
  fi
elif [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "FATAL: FORGE_PROVIDER=ollama but the Ollama server is not reachable at" >&2
    echo "       http://127.0.0.1:11434. Start it yourself ('ollama serve') and re-run." >&2
    echo "       This script intentionally does not start the server." >&2
    exit 3
  fi
fi

# 1. EverOS shared-memory pool up (loopback) so agent notes land in the real pool.
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only start if not already serving.
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; [ -n "${DJPID:-}" ] && kill $DJPID 2>/dev/null; exit 2; }

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend=$FORGE_PROVIDER)"

# 3. (Re)build gold so fidelity is scored against fresh observed behavior.
say "rebuilding gold (data/crud/)"
BASE_URL="$BASE" python data/crud/build_gold.py >/dev/null

# 4. Run the four agents. Claude handles concurrency fine; default 4.
CONC="${FORGE_CONCURRENCY:-1}"
say "running four agents (concurrency=$CONC)"
python scripts/run_crud_agents__verify-crud-operation-integrity.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "$CONC"
RC=$?

# 5. Score fidelity vs gold + leaderboard
say "scoring fidelity + leaderboard"
python judge/crud/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 6. Stop target (+ EverOS) if we started them
[ -n "${DJPID:-}" ] && { kill $DJPID 2>/dev/null; sleep 1; kill -9 $DJPID 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_crud_agents rc=$RC)"
