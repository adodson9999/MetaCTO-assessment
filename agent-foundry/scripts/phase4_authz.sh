#!/usr/bin/env bash
# Phase 4 (authorization workflow) — boot the local target, rebuild gold, run the
# four agents against it, score authorization fidelity, update the leaderboard.
# Self-contained + air-gapped. Re-runnable; each run appends to the leaderboard.
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

# 1. Ollama up
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    say "starting ollama"; nohup ollama serve >/tmp/ollama.log 2>&1 &
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 1b. EverOS shared-memory pool up (loopback)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). DummyJSON unmodified.
say "starting DummyJSON on :$PORT"
( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
    PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson_authz.log 2>&1 ) &
DJPID=$!
for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; kill $DJPID 2>/dev/null; exit 2; }

# 2b. Rebuild gold against the live target (records the API's real authz behavior)
say "rebuilding authz gold"
python data/authz/build_gold.py >/tmp/authz_gold.log 2>&1 \
  && grep -E "Access Control Accuracy" /tmp/authz_gold.log || { echo "gold build failed"; cat /tmp/authz_gold.log; }

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four authz agents (parallel)"
python scripts/run_agents_authz.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 2
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring authorization fidelity"
python judge/score_authz.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_leaderboard_authz.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 5. Stop target (+ EverOS if we started it)
kill $DJPID 2>/dev/null; sleep 1; kill -9 $DJPID 2>/dev/null
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
