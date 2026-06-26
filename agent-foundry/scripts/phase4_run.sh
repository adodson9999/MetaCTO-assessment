#!/usr/bin/env bash
# Phase 4 — run the four agents against the local target, score, leaderboard.
# Self-contained + air-gapped. Re-runnable; each run appends to the leaderboard.
set -uo pipefail

# Self-locating: the foundry is this script's parent dir; the target repo is the
# foundry's parent (the foundry lives inside the host repo). No hardcoded paths,
# so a plain `mv` of the foundry keeps this working.
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_MAX_ENDPOINTS="${FORGE_MAX_ENDPOINTS:-0}"   # 0 = all 22
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"   # so run_agents.py's "python" = venv python

cd "$FOUNDRY"

say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 1. Ollama up
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  say "starting ollama"; nohup ollama serve >/tmp/ollama.log 2>&1 &
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
fi

# 1b. EverOS shared-memory pool up (bound to loopback) so agent notes land in
#     the real pool, not just the local breadcrumb fallback.
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo)
say "starting DummyJSON on :$PORT"
( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
    PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
DJPID=$!
for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; kill $DJPID 2>/dev/null; exit 2; }

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four agents (parallel)"
python scripts/run_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 2
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 5. Stop target (+ EverOS if we started it)
kill $DJPID 2>/dev/null; sleep 1; kill -9 $DJPID 2>/dev/null
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
